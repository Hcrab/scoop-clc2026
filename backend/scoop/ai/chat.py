"""Explicit scripted intents over persisted plan context; no model is invoked."""
import re
from uuid import uuid4
from typing import Protocol
from fastapi import HTTPException
from sqlalchemy import select
from ..models import DirectionItem, Finding, Product, Tag, Store, PurchaseSuggestion

class ChatProvider(Protocol):
    """Reserved provider boundary. Only scripted is implemented in this demo."""
    name: str
    def respond(self, session, plan, message: str, stage: str) -> tuple[str,list]: ...

class ScriptedProvider:
    name='scripted'
    def respond(self, session, plan, message, stage): return scripted_response(session,plan,message,stage)

provider: ChatProvider=ScriptedProvider()

def respond(s,p,message,stage): return provider.respond(s,p,message,stage)

def scripted_response(s, p, message, stage):
    from ..api.service import objects, plan_for, decision, recompute, add_watch, WatchEdit
    text=message.lower().strip(); actions=[]
    findings=objects(s,Finding,p.id); orders=objects(s,PurchaseSuggestion,p.id)
    temperature = re.search(r'(-?\d+(?:\.\d+)?)\s*(?:°\s*c|℃|celsius|度|c\b)', text)
    if temperature and any(word in text for word in ['what if','if ','scenario','假设','如果']):
        from .scenarios import temperature_scenario
        try:
            result=temperature_scenario(s,p,float(temperature.group(1)),7 if any(w in text for w in ['next week','下周']) else 0)
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc
        return (f"Scripted model scenario: set daily maximum temperature to {result['temperature_c']:g} C from {result['start_date']} to {result['end_date']}. "
                f"The current plan's recommended purchases change from {result['baseline_cases']:,} to {result['scenario_cases']:,} cases ({result['delta_cases']:+,}). "
                f"Protection-period p50 demand changes from {result['baseline_p50_units']:,.0f} to {result['scenario_p50_units']:,.0f} units. "
                +result['assumptions']+' '+result['limitation']+' No plan or order was changed.',
                [{'type':'scenario','result':result}])
    if any(word in text for word in ['why','explain','reason','cause']):
        matches=[f for f in findings if (f.evidence.get('display','').lower() in text or f.tag_id.split(':')[-1].replace('_',' ') in text)]
        f=(matches or findings)[0] if findings else None
        if f:
            return (f"Scripted explanation: {f.explanation} Current interpretation: {f.classification}. Observed share {f.share_now:.1%}, baseline {f.share_before:.1%}; CUSUM {f.statistic:.2f} against {f.threshold:.2f}. These are observed facts before {p.week_start.isoformat()}.",actions)
        return (f"Scripted explanation: {len(orders)} SKU suggestions use protection-period forecasts, inventory position, MOQ and cold-store capacity. There are no findings on this plan yet.",actions)
    goal=next((value for token,value in [('fill rate','fill_rate'),('fill_rate','fill_rate'),('service','fill_rate'),('sales','sales'),('margin','margin'),('profit','margin')] if token in text),None)
    goal_request=goal and any(word in text for word in ['set','change','goal','maximize','optimise','optimize','target','prioriti'])
    if goal_request:
        plan_for(s,p.id,['discover','direction'])
        if stage!=p.stage: raise HTTPException(409,'The requested stage is read-only')
        percentage=re.search(r'(\d+(?:\.\d+)?)\s*%',text)
        service=float(percentage.group(1))/100 if percentage else None
        if service is not None and not .5<=service<=.995: raise HTTPException(422,'Service target must be 50% through 99.5%')
        if p.goal!=goal or p.service_level!=service:
            p.goal=goal;p.service_level=service
            decision(s,p,'goal',{'goal':goal,'service_level':service},'chat');recompute(s,p)
            actions.append({'type':'goal','goal':goal,'service_level':service})
        return (f"Scripted action: goal is {goal.replace('_',' ')}"+(f", service target {service:.1%}." if service else ', using the goal’s default service point.')+' Purchase suggestions were recomputed from forecasts.' if actions else 'Scripted response: that goal and service target are already applied.',actions)
    bucket=next((b for b in ['more','less','hold','clear'] if re.search(r'\b'+b+r'\b',text)),None)
    watching=any(word in text for word in ['watch','monitor','keep an eye'])
    if bucket or watching:
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
        metric=next((k for phrase,k in [('fill rate','fill_rate'),('capacity','capacity'),('pallet','capacity'),('cover','days_cover'),('stockout','fill_rate'),('delay','po_delay')] if phrase in text),None)
        if watching and metric:
            plan_for(s,p.id,[p.stage])
            if stage!=p.stage: raise HTTPException(409,'The requested stage is read-only')
            scope={'districts':requested_districts} if requested_districts else {}
            title='Chat watch: '+metric.replace('_',' ')
            if len(candidates)==1:
                kind,key,name=candidates[0];scope['tag_id' if kind=='tag' else 'sku']=key;title+=' · '+name
            if requested_districts: title+=' · '+', '.join(requested_districts)
            wid=add_watch(s,p,WatchEdit(kind=metric,title=title,assumption=message,scope=scope),origin='chat')
            return ('Scripted action: saved '+title+'. Values come from historical orders and inventory through the plan’s as-of date.',[{'type':'watch','id':wid}])
        if len(candidates)!=1:
            return ('Scripted response: name one exact category or SKU, for example “more fruit”, “hold cones”, or “watch IC001”. For goals use “set goal to fill rate 97%”. I have made no changes.',actions)
        kind,key,name=candidates[0]; scope={'tag_id':key} if kind=='tag' else {'sku':key}
        if requested_districts: scope['districts']=requested_districts
        if watching:
            plan_for(s,p.id,[p.stage])
            if stage!=p.stage: raise HTTPException(409,'The requested stage is read-only')
            wid=add_watch(s,p,WatchEdit(kind='tag_share',title=f'Chat watch: {name}',assumption=message,scope=scope),origin='chat')
            return (f'Scripted action: saved a demand-share watch for {name}, calculated from actual store orders.',[{'type':'watch','id':wid}])
        plan_for(s,p.id,['direction'])
        if stage!=p.stage: raise HTTPException(409,'The requested stage is read-only')
        percent=re.search(r'(\d+(?:\.\d+)?)\s*%',text)
        factor=(1+float(percent.group(1))/100 if bucket=='more' else 1-float(percent.group(1))/100) if percent else {'more':1.1,'less':.9,'hold':1.,'clear':0.}[bucket]
        if factor<0: raise HTTPException(422,'Unsupported adjustment; factor cannot be negative')
        column=DirectionItem.tag_id if kind=='tag' else DirectionItem.sku
        d=s.scalar(select(DirectionItem).where(DirectionItem.plan_id==p.id,column==key))
        districts=requested_districts or district_names
        if not d:
            d=DirectionItem(id=p.id+'-D'+uuid4().hex[:16],plan_id=p.id,tag_id=key if kind=='tag' else None,sku=key if kind=='sku' else None,bucket=bucket,factor=factor,districts=districts,note='Scripted chat: '+message);s.add(d);s.flush()
        elif d.bucket==bucket and d.factor==factor and d.districts==districts:
            return (f'Scripted response: {name} already has this direction; no extra changes.',actions)
        else: d.bucket=bucket;d.factor=factor;d.districts=districts
        decision(s,p,d.id,{'bucket':bucket,'factor':factor,'districts':districts},'chat');recompute(s,p)
        return (f'Scripted action: {name} set to {bucket}, multiplier {factor:.2f}, in {", ".join(districts)}. Forecast-based suggestions were recomputed.',[{'type':'direction','id':d.id,'bucket':bucket,'factor':factor}])
    positive=[o for o in orders if (o.final_cases if o.final_cases is not None else o.suggested_cases-o.capacity_cut_cases)>0]
    return (f"Scripted summary: {len(findings)} findings, {len(positive)} SKUs with positive purchase suggestions, and {sum(o.demand_p50 for o in orders):,.0f} forecast units across protection periods. Ask why a finding changed, set a margin/fill-rate/sales goal, edit more/less/hold/clear for one category during Direction, or request a watch.",actions)
