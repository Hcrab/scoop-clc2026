"""Plan-scoped assistant with a live provider and an explicit demo fallback."""
import re
import os
from typing import Protocol
from fastapi import HTTPException
from sqlalchemy import select
from ..models import Finding, Product, Tag, Store, PurchaseSuggestion
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
    from ..api.service import objects, plan_for
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
    if mutable:
        undo=re.search(r'(?:undo|revert|撤销|恢复).{0,30}?(\d+)',text)
        if undo:
            from .tools import execute
            result,action=execute('undo_edit',{'edit_id':int(undo.group(1))},s,p,stage)
            return ('已撤销这次调整，采购建议恢复到修改前。' if chinese else 'The context edit was undone and the prior orders were restored.',[action])
        month_names={'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}
        iso=re.search(r'\b(20\d\d)-(\d{1,2})-(\d{1,2})\b',text)
        natural=re.search(r'\b(\d{1,2})\s+(jan\w*|feb\w*|mar\w*|apr\w*|may\w*|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|nov\w*|dec\w*)(?:\s+(20\d\d))?\b',text)
        chinese_date=re.search(r'(?:(20\d\d)年)?(\d{1,2})月(\d{1,2})日?',text)
        end_date=None
        if iso:end_date=f'{int(iso.group(1)):04d}-{int(iso.group(2)):02d}-{int(iso.group(3)):02d}'
        elif natural:end_date=f'{int(natural.group(3) or p.week_start.year):04d}-{month_names[natural.group(2)[:3]]:02d}-{int(natural.group(1)):02d}'
        elif chinese_date:end_date=f'{int(chinese_date.group(1) or p.week_start.year):04d}-{int(chinese_date.group(2)):02d}-{int(chinese_date.group(3)):02d}'
        if end_date and re.search(r'ends?\b|until\b|through\b|结束|截止|到期',text):
            cards=(p.summary or {}).get('cohort_cards',[])
            leaves=(p.summary or {}).get('cohort_model',{}).get('leaves',[])
            candidates=[]
            def mentions(alias):
                return bool(alias and re.search(r'(?<!\w)'+re.escape(alias.lower())+r'(?!\w)',text))
            for card in cards+leaves:
                aliases=[card.get('name','')]+[t.get('id','').split(':')[-1].replace('_',' ') for t in card.get('tag_path',[]) if t.get('included')]
                if any(mentions(a) for a in aliases):candidates.append(card)
            if selected and not candidates:
                candidates=[c for c in cards+leaves if selected.tag_id in [t.get('id') for t in c.get('tag_path',[])]]
            unique={c['id']:c for c in candidates}
            if len(unique)==1:
                from .tools import execute
                cohort=next(iter(unique.values()))
                _,action=execute('set_override',{'cohort':cohort['id'],'type':'ends_on','value':end_date,'note':message},s,p,stage)
                return (f"已把{cohort.get('name') or '这组商品'}的结束日期记为 {end_date}，采购建议已重算。" if chinese else f"Recorded {cohort.get('name') or 'the cohort'} as ending on {end_date}; purchase recommendations were recalculated.",[action])
            if not unique:
                from .exploration_tools import _groups
                catalog_matches=[]
                for group in _groups(s).values():
                    aliases=[group.name,group.id.split(':')[-1].replace('_',' ')]
                    hits=[a for a in aliases if mentions(a)]
                    if hits and group.skus:
                        catalog_matches.append((max(map(len,hits)),group))
                if catalog_matches:
                    longest=max(length for length,_ in catalog_matches)
                    exact={g.id:g for length,g in catalog_matches if length==longest}
                    if len(exact)==1:
                        group=next(iter(exact.values()))
                        from .tools import execute
                        _,action=execute('set_override',{'tag_path':[{'id':group.id,'included':True}],
                            'districts':[],'type':'ends_on','value':end_date,'note':message},s,p,stage)
                        return (f'已把{group.name}的结束日期记为 {end_date}，采购建议已重算。' if chinese else
                                f'Recorded {group.name} as ending on {end_date}; purchase recommendations were recalculated.',[action])
            return ('请指定一张变化卡片对应的商品组；目前没有修改计划。' if chinese else 'Please name one cohort from the current plan. No change was made.',actions)
        capacity=re.search(r'(?:fit|keep|limit|控制|限制).{0,30}(?:capacity|space|peak|容量|库容|峰值).{0,30}?(\d+(?:\.\d+)?)\s*%',text)
        if capacity:
            from .tools import execute
            pct=float(capacity.group(1))
            result,action=execute('bulk_edit_orders',{'filter':{},'change':{'type':'fit_capacity','value':pct/100}},s,p,stage)
            met=result['capacity'].get('target_met',False)
            return ((f'已按仓库容量的 {pct:g}% 重算并保存整箱订单。' if met else f'已重算并保存整箱订单，但预计峰值仍高于 {pct:g}%。') if chinese else
                    (f'Orders were recalculated to fit {pct:g}% of warehouse capacity.' if met else f'Orders were recalculated, but projected peak remains above {pct:g}% of warehouse capacity.'),[action])
        direction=next((sign for term,sign in [('more',1),('increase',1),('extra',1),('多订',1),('增加',1),('多备',1),('less',-1),('reduce',-1),('fewer',-1),('少订',-1),('减少',-1),('少备',-1)] if term in text),None)
        signed_amount=re.search(r'(?<!\w)([+\-−–])\s*(\d+(?:\.\d+)?)\s*%',text)
        if signed_amount and direction is None:direction=-1 if signed_amount.group(1) in '-−–' else 1
        if direction and (signed_amount or re.search(r'\border\b|\bordering\b|订|采购|备货',text)):
            amount=re.search(r'(\d+(?:\.\d+)?)\s*%',text)
            if not amount:return ('请说出增减百分比；目前没有修改订单。' if chinese else 'Please give the percentage to change; no orders were edited.',actions)
            from .exploration_tools import _groups
            groups=_groups(s)
            scopes=[]
            for group in groups.values():
                aliases=[group.name.lower()]
                value_name=group.id.split(':')[-1].replace('_',' ').lower()
                if not value_name.isdigit():aliases.append(value_name)
                normalized=re.sub(r'[-\s]+',' ',text)
                if any(alias and re.search(r'(?<!\w)'+re.escape(re.sub(r'[-\s]+',' ',alias))+r'(?!\w)',normalized) for alias in aliases):
                    scopes.append((len(group.name),'group',group.id))
            for product in s.scalars(select(Product)):
                if product.name.lower() in text or product.sku.lower() in text:
                    scopes.append((len(product.name),'sku',product.sku))
            brands={product.brand for product in s.scalars(select(Product))}
            for brand in brands:
                if brand.lower() in text:scopes.append((len(brand),'brand',brand))
            if not scopes:return ('请指定商品或目录分组；目前没有修改订单。' if chinese else 'Please name a catalog group or product; no orders were edited.',actions)
            scopes.sort(reverse=True)
            best=[scope for scope in scopes if scope[0]==scopes[0][0]]
            if len({(x[1],x[2]) for x in best})!=1:
                return ('商品范围不明确；目前没有修改订单。' if chinese else 'The product scope is ambiguous; no orders were edited.',actions)
            _,kind,key=best[0]
            order_filter={'skus':[key]} if kind=='sku' else {kind:key}
            from .tools import execute
            _,action=execute('bulk_edit_orders',{'filter':order_filter,'change':{'type':'percent','value':direction*float(amount.group(1))}},s,p,stage)
            return (f'已把所选商品的整箱采购量调整 {direction*float(amount.group(1)):+g}%，并重新计算仓库容量。' if chinese else f'Adjusted the selected order quantities by {direction*float(amount.group(1)):+g}% and recalculated capacity.',[action])
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
    watching=any(word in text for word in ['watch','monitor','keep an eye','盯','监控','观察'])
    removing=any(word in text for word in ['remove','delete','stop watching','unwatch','移除','删除','取消关注','不再关注'])
    if mutable and removing and watching:
        from ..dashboard import view as dashboard_view
        from .tools import execute
        widgets=dashboard_view(s,p)['widgets']
        hits=[w for w in widgets if w['id'].lower() in text or w['title'].lower() in text]
        if not hits:
            # Resolve names from the saved scope option, not from a guessed ID.
            options={(o['kind'],o['key']):o['label'] for o in dashboard_view(s,p)['options']}
            hits=[w for w in widgets if (label:=options.get((w['scope']['kind'],w['scope']['key']))) and label.lower() in text]
        if len(hits)!=1:
            return ('请指出要移除的具体看板项。' if chinese else 'Please name the dashboard widget to remove.',actions)
        result,action=execute('remove_widget',{'id':hits[0]['id']},s,p,stage)
        return ('已从看板移除，可以撤销。' if chinese else 'Removed the widget from the dashboard. This edit can be undone.',[action])
    if mutable and watching:
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
        metric=next((k for phrase,k in [('fill rate','fill_rate'),('pallet','pallets'),('capacity','pallets'),('cover','days_cover'),('stockout','lost_units'),('on hand','on_hand'),('demand','demand'),('缺货','lost_units'),('满足率','fill_rate'),('库容','pallets'),('库存','on_hand'),('需求','demand')] if phrase in text),None)
        if len(candidates)>1:
            return ('请指定一个品类或商品，我还没有修改计划。' if chinese else 'Please name one category or product. I have made no changes.',actions)
        if watching and metric:
            plan_for(s,p.id,[p.stage])
            if stage!=p.stage: raise HTTPException(409,'The requested stage is read-only')
            scope={'kind':'warehouse','key':''}
            title='Dashboard: '+metric.replace('_',' ')
            if len(candidates)==1:
                kind,key,name=candidates[0];scope={'kind':kind,'key':key};title+=' · '+name
            if requested_districts:return ('地区级指标尚未在看板范围中提供。' if chinese else 'District scope is not available on the dashboard.',actions)
            from .tools import execute
            saved,action=execute('add_widget',{'spec':{'title':title,'scope':scope,'metric':metric}},s,p,stage)
            if chinese:return ('已加入看板，可以查看历史表现，也可以撤销。',[action])
            return ('Saved '+title+' to the dashboard. The edit can be undone.',[action])
        if len(candidates)!=1:
            return ('Please name one exact category or product to watch. I have made no changes.',actions)
        kind,key,name=candidates[0]; scope={'kind':kind,'key':key}
        if requested_districts:return ('地区级指标尚未在看板范围中提供。' if chinese else 'District scope is not available on the dashboard.',actions)
        if watching:
            plan_for(s,p.id,[p.stage])
            if stage!=p.stage: raise HTTPException(409,'The requested stage is read-only')
            from .tools import execute
            saved,action=execute('add_widget',{'spec':{'title':f'Dashboard: {name} demand','scope':scope,'metric':'demand'}},s,p,stage)
            return (f'Saved a demand widget for {name}, calculated from actual store orders.',[action])
    positive=[o for o in orders if (o.final_cases if o.final_cases is not None else o.suggested_cases-o.capacity_cut_cases)>0]
    if chinese:return (f"当前有 {len(findings)} 条发现，{len(positive)} 款商品有采购建议。演示助手能解释发现、计算温度情景、记录商品组结束日期或添加关注项；这条消息没有修改计划。",actions)
    return (f"Scripted summary: {len(findings)} findings and {len(positive)} products with positive purchase suggestions. Ask about a finding, a temperature scenario, or an explicit cohort end date.",actions)
