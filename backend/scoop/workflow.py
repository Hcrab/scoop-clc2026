"""Weekly watch lifecycle, stored in existing plan JSON without a schema migration.

Non-HTTP builders should call initialize_plan(session, plan) after persisting a new
plan, in the same transaction. Approved snapshots and prior-week rows are never
rewritten by carryover. Explicit edits create decisions through the API.
"""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from sqlalchemy import select
from .models import Plan, WatchItem, Finding, DirectionItem,Tag,Product

VERSION=2
KEY='watch_workflow'

def state(plan): return deepcopy((plan.summary or {}).get(KEY,{}))
def save(plan,value): plan.summary={**(plan.summary or {}),KEY:value}
def watches(session,pid): return list(session.scalars(select(WatchItem).where(WatchItem.plan_id==pid).order_by(WatchItem.id)))
def fingerprint(session,plan):
    rows=[{'id':w.id,'kind':w.kind,'title':w.title,'assumption':w.assumption,'scope':w.scope} for w in watches(session,plan.id) if w.status=='active']
    dirs=[{'id':d.id,'bucket':d.bucket,'factor':d.factor,'districts':d.districts,'sku':d.sku,'tag_id':d.tag_id} for d in session.scalars(select(DirectionItem).where(DirectionItem.plan_id==plan.id).order_by(DirectionItem.id))]
    return sha256(json.dumps({'items':rows,'directions':dirs,'goal':plan.goal,'service':plan.service_level},sort_keys=True,default=str).encode()).hexdigest()

def candidates(session,plan):
    baseline=[
        ('baseline:fill_rate',dict(kind='fill_rate',title='Fill rate to stores',assumption=f'Store orders should be filled at {(plan.service_level or .97):.1%} or better.',scope={})),
        ('baseline:shortage',dict(kind='days_cover',title='Stockout risk: cover below lead time',assumption='Each SKU should have enough warehouse stock for its supplier lead time.',scope={'mode':'below_lead'})),
        ('baseline:excess',dict(kind='days_cover',title='Excess stock cover',assumption='Review stock beyond twice the supplier lead time plus the weekly review period.',scope={'mode':'excess'})),
        ('baseline:capacity',dict(kind='capacity',title='Plan arrival projection',assumption='Frozen dated arrivals and forecast consumption should fit the cold store. This is a projection, not observed stock.',scope={'mode':'projected'})),
        ('baseline:po_delay',dict(kind='po_delay',title='Late purchase orders',assumption='Historical supplier deliveries should arrive by the promised date.',scope={})),
    ]
    result=[(key,{**value,'origin':'baseline'}) for key,value in baseline]
    findings={f.id:f for f in session.scalars(select(Finding).where(Finding.plan_id==plan.id))}
    for d in session.scalars(select(DirectionItem).where(DirectionItem.plan_id==plan.id).order_by(DirectionItem.id)):
        if not d.tag_id and not d.sku: continue
        f=findings.get(d.finding_id)
        name=(f.evidence or {}).get('display') if f else None
        product=session.get(Product,d.sku) if d.sku else None
        tag=session.get(Tag,d.tag_id) if d.tag_id else None
        name=(name or (product.name if product else None) or (tag.name if tag else None) or d.note or d.tag_id or d.sku)[:100]
        scope={'districts':d.districts,**({'group':d.tag_id} if d.tag_id else {'sku':d.sku})}
        assumptions={'more':'The higher demand share continues after increasing orders.', 'less':'Demand share stays lower; reduced orders should not cause shortages.', 'hold':'Check whether demand returns toward its expected share before changing baseline orders.', 'clear':'Remaining stock should decline without replenishing this category.'}
        result.append(('direction:'+d.id+':share',dict(kind='tag_share',title=f'{name}: compare with expected share',assumption=assumptions[d.bucket],scope=scope,origin='decision')))
        if d.bucket in {'more','less','clear'}:
            excess=d.bucket=='clear'
            result.append(('direction:'+d.id+':stock',dict(kind='days_cover',title=f'{name}: '+('remaining stock' if excess else 'shortage risk'),assumption=assumptions[d.bucket],scope={**scope,'mode':'excess' if excess else 'below_lead'},origin='decision')))
    for f in findings.values():
        if f.kind=='weak':
            name=(f.evidence or {}).get('display',f.tag_id)
            result.append(('weak:'+f.id,dict(kind='tag_share',title=f'{name}: weak signal',assumption='Review this uncertain signal; no confirmed change is assumed.',scope={'group':f.tag_id,'districts':(f.evidence or {}).get('districts',f.district.split(', '))},origin='decision')))
    return result

def _legacy_match(w,key,values):
    if w.origin not in {'baseline','decision'}: return False
    if w.title==values['title']: return True
    if key.startswith('baseline:') and w.origin=='baseline':
        if values['kind']!=w.kind: return False
        if w.kind!='days_cover': return True
        return w.scope.get('mode','below_lead')==values['scope'].get('mode')
    return w.kind==values['kind'] and w.scope==values['scope']

def refresh_generated(session,plan):
    info=state(plan); metadata=info.setdefault('items',{}); existing=watches(session,plan.id)
    desired=candidates(session,plan); wanted={key for key,_ in desired}
    for w in existing:
        meta=metadata.get(w.id,{})
        if meta.get('managed') and meta.get('source_key') not in wanted and not meta.get('customized') and w.status=='active':
            w.status='archived';meta['archive_reason']='superseded';metadata[w.id]=meta
    for key,values in desired:
        w=next((x for x in existing if metadata.get(x.id,{}).get('source_key')==key),None)
        if w is None:
            w=next((x for x in existing if x.id not in metadata and _legacy_match(x,key,values)),None)
        if w is None:
            wid=plan.id+'-W'+sha256(key.encode()).hexdigest()[:16]
            title=values['title']
            if any(x.title==title for x in existing): title+=' · '+sha256(key.encode()).hexdigest()[:4]
            w=WatchItem(id=wid,plan_id=plan.id,status='active',**{**values,'title':title});session.add(w);existing.append(w)
        meta=metadata.setdefault(w.id,{'source_key':key,'root_watch_id':w.id,'managed':True,'customized':False,'carried_from':None})
        if not meta.get('customized'):
            # Archived user choices stay archived. System-superseded cards may return.
            if w.status=='archived' and meta.get('archive_reason')=='superseded': w.status='active';meta.pop('archive_reason',None)
            if w.status=='active':
                for field,value in values.items():
                    if field=='title' and any(x.id!=w.id and x.title==value for x in existing): continue
                    setattr(w,field,value)
        if w.status=='archived' and not meta.get('archive_reason'): meta['archive_reason']='user'
    save(plan,info);session.flush()

def initialize_plan(session,plan):
    if state(plan).get('version')==VERSION: return
    # Serialize upgrading old plans and concurrent first opens.
    plan=session.scalar(select(Plan).where(Plan.id==plan.id).with_for_update().execution_options(populate_existing=True))
    if state(plan).get('version')==VERSION: return
    refresh_generated(session,plan)
    info=state(plan); metadata=info.setdefault('items',{})
    previous=session.scalar(select(Plan).where(Plan.week_start<plan.week_start).order_by(Plan.week_start.desc()).limit(1))
    existing=watches(session,plan.id)
    if previous:
        previous_meta=state(previous).get('items',{})
        for source in watches(session,previous.id):
            if source.status!='active' or source.origin=='baseline': continue
            source_meta=previous_meta.get(source.id,{})
            root_id=source_meta.get('root_watch_id',source.id)
            # An identical generated assumption can continue under its current card.
            match=next((w for w in existing if w.kind==source.kind and w.scope==source.scope and w.assumption==source.assumption and w.title==source.title and w.status=='active'),None)
            if match:
                metadata.setdefault(match.id,{}).update(carried_from=previous.id,source_watch_id=source.id,root_watch_id=root_id)
                continue
            wid=plan.id+'-W'+sha256(('carry:'+root_id).encode()).hexdigest()[:16]
            if any(w.id==wid for w in existing): continue
            title=source.title
            if any(w.title==title for w in existing): title=title[:140]+' · continued '+sha256(root_id.encode()).hexdigest()[:4]
            row=WatchItem(id=wid,plan_id=plan.id,kind=source.kind,title=title,assumption=source.assumption,scope=deepcopy(source.scope),origin=source.origin,status='active')
            session.add(row);existing.append(row)
            metadata[wid]={'source_key':'carry:'+root_id,'root_watch_id':root_id,'managed':False,'customized':False,'carried_from':previous.id,'source_watch_id':source.id}
    info['version']=VERSION;info['initialized_at']=datetime.now().isoformat()
    info.setdefault('review',{'confirmed':False,'confirmed_at':None})
    save(plan,info);session.flush()

def mark_watch_edit(plan,watch,archived=False):
    info=state(plan); meta=info.setdefault('items',{}).setdefault(watch.id,{'root_watch_id':watch.id,'managed':False,'carried_from':None})
    if archived: meta['archive_reason']='user'
    else: meta['customized']=True;meta.pop('archive_reason',None)
    save(plan,info)

def invalidate_review(plan):
    info=state(plan)
    if info.get('review',{}).get('confirmed'):
        info['review']={**info['review'],'confirmed':False,'changed_at':datetime.now().isoformat()};save(plan,info)

def review_state(session,plan):
    saved=state(plan).get('review',{})
    return {'confirmed':bool(saved.get('confirmed') and saved.get('fingerprint')==fingerprint(session,plan)),'confirmed_at':saved.get('confirmed_at')}

def confirm_review(session,plan,projection=None):
    current=review_state(session,plan)
    if current['confirmed']: return False
    info=state(plan)
    active=[w for w in watches(session,plan.id) if w.status=='active']
    info['review']={'confirmed':True,'confirmed_at':datetime.now().isoformat(),'fingerprint':fingerprint(session,plan),'selection':[w.id for w in active],'items':[{key:deepcopy(getattr(w,key)) for key in ['id','plan_id','kind','title','assumption','scope','origin','status']} for w in active]}
    if projection is not None and plan.stage in {'discover','direction'}: info['approved_projection']=deepcopy(projection)
    save(plan,info);return True

def freeze_approval(session,plan,projection):
    """Call before setting Direction to Execute. Subsequent watch edits are separate."""
    info=state(plan)
    if 'approved_review' in info: return
    info['approved_review']=deepcopy(info.get('review',{}))
    info['approved_projection']=deepcopy(projection)
    save(plan,info)
