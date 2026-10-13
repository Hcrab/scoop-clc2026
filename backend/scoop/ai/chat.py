"""Plan-scoped assistant with a live provider and an explicit demo fallback."""
import re
import os
from uuid import uuid4
from typing import Protocol
from fastapi import HTTPException
from sqlalchemy import select
from ..models import DirectionItem, Finding, Product, Tag, Store, PurchaseSuggestion
from ..config import settings

class ChatProvider(Protocol):
    """Common boundary for deterministic fallback implementations."""
    name: str
    def respond(self, session, plan, message: str, stage: str) -> tuple[str,list]: ...

class ScriptedProvider:
    name='scripted'
    def respond(self, session, plan, message, stage, context=None):
        try:return scripted_response(session,plan,message,stage,context)
        except ValueError as exc:raise HTTPException(422,str(exc)) from None

provider: ChatProvider=ScriptedProvider()

def provider_info():
    requested=settings.llm_provider
    live=requested in {'gemini','auto'} and bool(os.getenv('GEMINI_API_KEY'))
    return {'provider':'gemini' if live else 'scripted','label':'Scoop assistant' if live else 'Demo assistant','live':live,'available':True}


def respond(s,p,message,stage,context=None,progress=None):
    from .gemini import ChatReply,ProviderUnavailable
    if provider_info()['live']:
        from .gemini import respond as live_respond
        try:return live_respond(s,p,message,stage,context,progress)
        except ProviderUnavailable as exc:
            reply,actions=provider.respond(s,p,message,stage,context)
            prefix='实时助手暂时不可用，以下是演示助手的回答。\n\n' if re.search('[\u4e00-\u9fff]',message) else 'The live assistant is unavailable. Here is the demo assistant’s response.\n\n'
            return ChatReply(prefix+reply,actions,'scripted',fallback_reason=str(exc))
    reply,actions=provider.respond(s,p,message,stage,context)
    return ChatReply(reply,actions,'scripted')

def scripted_response(s, p, message, stage, context=None):
    from ..api.service import objects, plan_for, decision, recompute, add_watch, WatchEdit
    from .gemini import _may_mutate
    text=message.lower().strip(); actions=[]
    chinese=bool(re.search('[\u4e00-\u9fff]',message))
    mutable=_may_mutate(message)
    for original,alias in [('水基','water-based'),('水果','fruit'),('港岛','HK Island'),('香港岛','HK Island'),('九龙','Kowloon'),('新界东','NT East'),('新界西','NT West')]:
        text=text.replace(original,alias.lower())
    findings=objects(s,Finding,p.id); orders=objects(s,PurchaseSuggestion,p.id)
    temperature = re.search(r'(-?\d+(?:\.\d+)?)\s*(?:°\s*c|℃|celsius|度|c\b)', text)
    if temperature and any(word in text for word in ['what if','if ','scenario','假设','如果']):
        from .scenarios import temperature_scenario
        try:
            result=temperature_scenario(s,p,float(temperature.group(1)),7 if any(w in text for w in ['next week','下周']) else 0)
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc
        if chinese:
            return (f"把 {result['start_date']} 至 {result['end_date']} 的每日最高温度设为 {result['temperature_c']:g}℃ 后，建议采购量从 {result['baseline_cases']:,} 箱变为 {result['scenario_cases']:,} 箱（{result['delta_cases']:+,} 箱）。这是保留其他假设的温度情景估算，尚未更改计划或订单。",[{'type':'scenario','result':result}])
        return (f"Temperature scenario: set daily maximum temperature to {result['temperature_c']:g} C from {result['start_date']} to {result['end_date']}. "
                f"The current plan's recommended purchases change from {result['baseline_cases']:,} to {result['scenario_cases']:,} cases ({result['delta_cases']:+,}). "
                f"Protection-period p50 demand changes from {result['baseline_p50_units']:,.0f} to {result['scenario_p50_units']:,.0f} units. "
                +result['assumptions']+' '+result['limitation']+' No plan or order was changed.',
                [{'type':'scenario','result':result}])
    focused=next((f for f in findings if f.id==(context or {}).get('finding_id')),None)
    matches=[f for f in findings if (f.evidence.get('display','').lower() in text or f.tag_id.split(':')[-1].replace('_',' ') in text)]
    selected=focused or (matches[0] if len(matches)==1 else None)
    interpretation=next((value for words,value in [(['persistent','持续趋势','持续变化'],'persistent'),(['one-off','one off','一次性'],'one_off'),(['data issue','数据问题'],'data_issue'),(['weather','天气'],'weather'),(['unsure','不确定'],'unsure')] if any(w in text for w in words)),None)
    if mutable and interpretation and selected:
        from .tools import execute
        result,action=execute('classify_finding',{'finding_id':selected.id,'interpretation':interpretation},s,p,stage)
        labels={'persistent':'持续变化','one_off':'一次性变化','data_issue':'数据问题','weather':'天气影响','unsure':'继续观察'}
        return (f"已将这条发现记为“{labels[interpretation]}”，相关建议已更新。" if chinese else f"Recorded as {interpretation.replace('_',' ')} and updated the related recommendations.",[action])
    if any(word in text for word in ['why','explain','reason','cause','为什么','解释','原因']):
        matches=[f for f in findings if (f.evidence.get('display','').lower() in text or f.tag_id.split(':')[-1].replace('_',' ') in text)]
        f=selected or ((matches or findings)[0] if findings else None)
        if f:
            if chinese:
                return (f"这类商品的需求占比是 {f.share_now:.1%}，模型原先预期为 {f.share_before:.1%}。记录截至 {p.week_start.isoformat()} 之前；占比变化能提醒我们进一步核实原因，本身不能证明顾客偏好已经改变。可以展开该发现的证据，查看门店覆盖、促销及天气检查。",actions)
            return (f"{f.explanation} Observed share is {f.share_now:.1%}, against a {f.share_before:.1%} baseline. Evidence is from before {p.week_start.isoformat()}; the interpretation remains a working explanation.",actions)
        return (f"Scripted explanation: {len(orders)} SKU suggestions use protection-period forecasts, inventory position, MOQ and cold-store capacity. There are no findings on this plan yet.",actions)
    goal=next((value for token,value in [('fill rate','fill_rate'),('fill_rate','fill_rate'),('service','fill_rate'),('sales','sales'),('margin','margin'),('profit','margin'),('满足率','fill_rate'),('利润','margin'),('销量','sales')] if token in text),None)
    goal_request=mutable and goal and any(word in text for word in ['set','change','goal','maximize','optimise','optimize','target','prioriti','设为','设置','改为','改成','目标'])
    if goal_request:
        from .tools import execute
        percentage=re.search(r'(\d+(?:\.\d+)?)\s*%',text)
        service=float(percentage.group(1))/100 if percentage else None
        result,action=execute('set_goal',{'goal':goal,'service_level':service},s,p,stage)
        if chinese:
            name={'margin':'利润','sales':'销量','fill_rate':'门店满足率'}[goal]
            return (f'已将本周目标设为{name}'+(f'，满足率目标 {service:.1%}。' if service else '。')+'采购建议已重新计算。',[action])
        return (f'The buying objective is now {goal.replace("_"," ")}' +(f', with a {service:.1%} service target.' if service else ', using the default service target.')+' Purchase recommendations were recalculated.',[action])
    bucket=next((b for b in ['more','less','hold','clear'] if re.search(r'\b'+b+r'\b',text)),None)
    bucket=bucket or next((b for token,b in [('多备','more'),('少备','less'),('增加','more'),('减少','less'),('清货','clear'),('保持','hold')] if token in text),None)
    watching=any(word in text for word in ['watch','monitor','keep an eye','盯','监控','观察'])
    if mutable and (bucket or watching):
        candidates=[]
        for f in findings:
            name=f.evidence.get('display','')
            if name and name.lower().replace('-',' ') in text.replace('-',' '): candidates.append(('tag',f.tag_id,name))
        for tag in s.scalars(select(Tag)):
            token=tag.id.split(':')[-1].replace('_',' ')
            if ':' in tag.id and (token in text or tag.name.lower() in text): candidates.append(('tag',tag.id,tag.name))
        for product in s.scalars(select(Product)):
            if product.sku.lower() in text or product.name.lower() in text: candidates.append(('sku',product.sku,product.name))
        # Prefer the longest literal match; identical category aliases stay ambiguous.
        candidates=list({(kind,key): (kind,key,name) for kind,key,name in candidates}.values())
        if len(candidates)>1:
            length=max(len(c[2]) for c in candidates); candidates=[c for c in candidates if len(c[2])==length]
        district_names=sorted(set(s.scalars(select(Store.district))))
        requested_districts=[d for d in district_names if d.lower() in text or (d=='HK Island' and 'hong kong island' in text)]
        metric=next((k for phrase,k in [('fill rate','fill_rate'),('capacity','capacity'),('pallet','capacity'),('cover','days_cover'),('stockout','fill_rate'),('delay','po_delay'),('缺货','fill_rate'),('满足率','fill_rate'),('库容','capacity'),('延迟','po_delay')] if phrase in text),None)
        if len(candidates)>1:
            return ('请指定一个品类或商品，我还没有修改计划。' if chinese else 'Please name one category or product. I have made no changes.',actions)
        if watching and metric:
            plan_for(s,p.id,[p.stage])
            if stage!=p.stage: raise HTTPException(409,'The requested stage is read-only')
            scope={'districts':requested_districts} if requested_districts else {}
            title='Chat watch: '+metric.replace('_',' ')
            if len(candidates)==1:
                kind,key,name=candidates[0];scope['tag_id' if kind=='tag' else 'sku']=key;title+=' · '+name
            if requested_districts: title+=' · '+', '.join(requested_districts)
            from .tools import execute
            saved,_=execute('add_watch',{'kind':metric,'title':title,'assumption':message,**scope},s,p,stage)
            wid=saved['id']
            if chinese:return ('已加入关注清单。可以在清单里查看这个范围的历史表现，以及接下来需要核实的变化。',[{'type':'watch','id':wid}])
            return ('Scripted action: saved '+title+'. Values come from historical orders and inventory through the plan’s as-of date.',[{'type':'watch','id':wid}])
        if len(candidates)!=1:
            return ('Scripted response: name one exact category or SKU, for example “more fruit”, “hold cones”, or “watch IC001”. For goals use “set goal to fill rate 97%”. I have made no changes.',actions)
        kind,key,name=candidates[0]; scope={'tag_id':key} if kind=='tag' else {'sku':key}
        if requested_districts: scope['districts']=requested_districts
        if watching:
            plan_for(s,p.id,[p.stage])
            if stage!=p.stage: raise HTTPException(409,'The requested stage is read-only')
            from .tools import execute
            saved,_=execute('add_watch',{'kind':'tag_share','title':f'Chat watch: {name}','assumption':message,**scope},s,p,stage)
            wid=saved['id']
            return (f'Scripted action: saved a demand-share watch for {name}, calculated from actual store orders.',[{'type':'watch','id':wid}])
        from .tools import execute
        percent=re.search(r'(\d+(?:\.\d+)?)\s*%',text)
        factor={'more':1.1,'less':.9,'hold':1.,'clear':0.}[bucket]
        if percent and bucket in {'more','less'}:factor=1+(1 if bucket=='more' else -1)*float(percent.group(1))/100
        districts=requested_districts or district_names
        result,action=execute('set_direction',{'bucket':bucket,'factor':factor,'districts':districts,'tag_id' if kind=='tag' else 'sku':key},s,p,stage)
        change=f'{(factor-1)*100:+.0f}%'
        return (f'已记录{name}的采购方向：相对原预期调整 {change}，适用于{", ".join(districts)}。采购建议已重新计算。' if chinese else f'{name}: planned demand adjusted by {change} in {", ".join(districts)}. Purchase recommendations were recalculated.',[action])
    positive=[o for o in orders if (o.final_cases if o.final_cases is not None else o.suggested_cases-o.capacity_cut_cases)>0]
    if chinese:return (f"当前有 {len(findings)} 条发现，{len(positive)} 款商品有采购建议。演示助手能解释发现、计算温度情景、记录购买方向或添加关注项；这条消息没有修改计划。",actions)
    return (f"Scripted summary: {len(findings)} findings, {len(positive)} SKUs with positive purchase suggestions, and {sum(o.demand_p50 for o in orders):,.0f} forecast units across protection periods. Ask why a finding changed, set a margin/fill-rate/sales goal, edit more/less/hold/clear for one category during Direction, or request a watch.",actions)
