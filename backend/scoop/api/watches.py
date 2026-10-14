"""Request-scoped watch aggregation. No cross-request cache can outlive fact edits."""
from collections import defaultdict
from datetime import timedelta, date
import math
from sqlalchemy import text
from .. import workflow

PROVENANCE='Observed synthetic warehouse history. Recorded demo purchases do not change this historical stock.'

class WatchData:
    def __init__(self,s,cutoff,expected_reader):
        self.s=s;self.cutoff=cutoff;self.expected_reader=expected_reader
        self.start=cutoff-timedelta(days=28);self.warmup=self.start-timedelta(days=7)
        self.orders=list(s.execute(text('SELECT o.date,o.sku,st.district,SUM(o.ordered_units) AS ordered_units,SUM(o.shipped_units) AS shipped_units FROM store_orders o JOIN stores st ON st.id=o.store_id WHERE o.date>=:start AND o.date<:end GROUP BY o.date,o.sku,st.district'),{'start':self.warmup,'end':cutoff}).mappings())
        self.network_units=defaultdict(lambda:defaultdict(float))
        for r in self.orders: self.network_units[r['date']][r['sku']]+=r['ordered_units']
        self.order_days={r['date'] for r in self.orders}
        self.products={r['sku']:dict(r) for r in s.execute(text('SELECT p.sku,p.name,p.units_per_case,p.cases_per_pallet,s.lead_time_days,s.review_days FROM products p JOIN suppliers s ON s.id=p.supplier_id')).mappings()}
        self.inventory=defaultdict(dict)
        for r in s.execute(text('SELECT date,sku,on_hand_units FROM node_inventory WHERE date>=:start AND date<:end'),{'start':self.start,'end':cutoff}).mappings(): self.inventory[r['date']][r['sku']]=r['on_hand_units']
        self.po=list(s.execute(text("SELECT sku,expected_date,received_date,order_date FROM purchase_orders WHERE source='history' AND order_date<:end"),{'end':cutoff}).mappings())
        self.tags=defaultdict(set);self.values=defaultdict(list)
        for r in s.execute(text('SELECT sku,tag_id,value_num FROM product_tags')).mappings(): self.tags[r['tag_id']].add(r['sku']);self.values[r['tag_id']].append((r['sku'],r['value_num']))
        self.districts=sorted(set(s.execute(text('SELECT DISTINCT district FROM stores')).scalars()))
        self.days=sorted({r['date'] for r in self.orders if r['date']>=self.start}|set(self.inventory))
        self.scopes={};self.expected={}
        self.capacity=s.execute(text('SELECT capacity_pallets FROM nodes ORDER BY id LIMIT 1')).scalar()

    def members(self,scope):
        tag=scope.get('tag_id',scope.get('group')); explicit=set(scope.get('skus',[]))
        if scope.get('sku'): explicit.add(scope['sku'])
        if tag and tag.startswith('band:'):
            _,dim,band=tag.split(':');values=sorted(self.values.get(dim,[]),key=lambda r:r[1])
            def edge(q):
                index=(len(values)-1)*q;lo=math.floor(index);hi=math.ceil(index)
                return values[lo][1]+(values[hi][1]-values[lo][1])*(index-lo)
            members={sku for sku,value in values if (0 if value<=edge(1/3) else 1 if value<=edge(2/3) else 2)==int(band)} if values else set()
        elif tag: members=set(self.tags.get(tag,set()))
        else: members=set(self.products)
        return members&explicit if explicit else members

    def scoped(self,scope):
        members=self.members(scope);districts=set(scope.get('districts') or self.districts)
        key=(tuple(sorted(members)),tuple(sorted(districts)))
        if key not in self.scopes:
            units=defaultdict(lambda:defaultdict(float));totals=defaultdict(lambda:[0,0]);denominator=defaultdict(float)
            for r in self.orders:
                if r['district'] not in districts: continue
                denominator[r['date']]+=r['ordered_units']
                if r['sku'] in members:
                    units[r['date']][r['sku']]+=r['ordered_units'];totals[r['date']][0]+=r['ordered_units'];totals[r['date']][1]+=r['shipped_units']
            self.scopes[key]=(units,totals,denominator)
        return members,self.scopes[key]

    def view(self,w,plan,projection=None,recap=False):
        result={c.name:getattr(w,c.name) for c in w.__table__.columns}
        meta=workflow.state(plan).get('items',{}).get(w.id,{})
        result.update(carried_from=meta.get('carried_from'),expected_low=None,expected_high=None,deviation=None,action_hint=None,provenance=PROVENANCE)
        if w.scope.get('districts') and w.kind in {'days_cover','po_delay','capacity'}: result['provenance']+=' Warehouse stock and suppliers serve all districts; district filters identify the demand being followed, not a reserved district stock allocation.'
        if w.kind=='capacity' and w.scope.get('mode')=='projected':
            points=(projection or {}).get('series',[])
            if recap: points=[point for point in points if date.fromisoformat(str(point['date'])[:10])<self.cutoff]
            limit=(projection or {}).get('capacity_pallets')
            value=max((point['value'] for point in points),default=0)
            result.update(value=value,unit='pallets',series=points,state='review',expected_high=limit,provenance='Frozen plan-date occupancy forecast; future dates are projections, never observed stock.')
            if not projection or not points:
                result.update(deviation='The original approved occupancy snapshot is unavailable.',action_hint='Review occupancy before placing a new order; historical approvals are not recalculated.')
            elif limit is not None:
                result.update(state='warning' if value>limit else 'review',deviation=f'Projected peak {value:.1f} pallets; cold-store limit {limit:.1f}. An occupancy uncertainty interval is not calibrated.',action_hint='Reduce or reschedule arrivals.' if value>limit else 'Follow the arrival schedule and review actual stock; forecast uncertainty remains.')
            return result
        members,(units,totals,denominator)=self.scoped(w.scope)
        points=[];last_details=[];threshold=plan.service_level or .97
        for day in self.days:
            ordered,shipped=totals.get(day,[0,0]);inv=self.inventory.get(day,{})
            if w.kind=='fill_rate':
                if not ordered: continue
                value=shipped/ordered;unit='ratio'
            elif w.kind=='tag_share':
                if not denominator.get(day): continue
                value=ordered/denominator[day];unit='ratio'
            elif w.kind=='capacity':
                if not inv: continue
                value=sum(inv.get(sku,0)/(self.products[sku]['units_per_case']*self.products[sku]['cases_per_pallet']) for sku in members);unit='pallets'
            elif w.kind=='po_delay':
                value=sum(p['sku'] in members and p['expected_date']<day and (p['received_date'] is None or p['received_date']>day) and p['order_date']<=day for p in self.po);unit='orders'
            else:
                if not inv: continue
                details=[];excess=w.scope.get('mode')=='excess'
                complete=all(day-timedelta(days=i) in self.order_days for i in range(7))
                for sku in members&set(inv):
                    p=self.products[sku]
                    if w.scope.get('districts') and not any(units.get(day-timedelta(days=i),{}).get(sku,0)>0 for i in range(7)): continue
                    mean=sum(self.network_units.get(day-timedelta(days=i),{}).get(sku,0) for i in range(7))/7
                    if not mean:
                        flagged=excess and complete and inv[sku]>0;cover=None
                    else:
                        cover=inv[sku]/mean
                        flagged=complete and cover>2*(p['lead_time_days']+p['review_days']) if excess else cover<p['lead_time_days']
                    if flagged: details.append({'sku':sku,'name':p['name'],'on_hand_units':inv[sku],'days_cover':cover,'lead_time_days':p['lead_time_days']})
                value=len(details);unit='SKUs';last_details=details
            points.append({'date':day.isoformat(),'value':value})
        value=points[-1]['value'] if points else 0
        state='review';deviation='No observed measurements are available at this date.';hint='Review this assumption when observed data becomes available.'
        if points:
            if w.kind=='fill_rate': state='warning' if value<threshold else 'normal';deviation=f'Latest fill rate {value:.1%}; target {threshold:.1%}.';hint='Review unfilled orders and supplier arrivals.' if state=='warning' else 'Continue monitoring store service.';result['expected_low']=threshold;result['expected_high']=1
            elif w.kind=='capacity':
                limit=self.capacity;state='warning' if limit is not None and value>limit else 'normal' if limit is not None else 'review';result['expected_high']=limit;deviation=f'Observed cold-store stock uses {value:.1f} pallets.';hint='Review dated arrivals separately from observed stock.'
            elif w.kind=='po_delay': state='warning' if value else 'normal';deviation=f'{value} historical purchase orders overdue.';hint='Ask the supplier for a delivery update.' if value else 'Keep checking promised delivery dates.'
            elif w.kind=='days_cover':
                state='warning' if value else 'normal' if complete else 'review'
                deviation=f'{value} SKUs have '+('excess stock cover.' if w.scope.get('mode')=='excess' else 'stock cover below supplier lead time.') if complete or value else 'Seven days of observed demand are not available; stock-cover risk needs review.'
                hint='Review excess quantities and clearance options.' if w.scope.get('mode')=='excess' else 'Review stock and expedite the affected SKUs.';result['affected_skus']=last_details;result['expected_high']=0
            else:
                tag=w.scope.get('tag_id',w.scope.get('group'));districts=w.scope.get('districts') or self.districts
                if tag and not w.scope.get('sku') and not w.scope.get('skus'):
                    key=(tag,tuple(sorted(districts)))
                    if key not in self.expected:
                        try: self.expected[key]=self.expected_reader(tag,districts,self.start,self.cutoff)
                        except (ValueError,KeyError,FileNotFoundError): self.expected[key]=[]
                    expected={str(p['date'])[:10]:p['expected_share'] for p in self.expected[key] if str(p['date'])[:10]<self.cutoff.isoformat()}
                    for point in points:
                        if point['date'] in expected: point['expected']=expected[point['date']]
                deviation='Observed share is available; a calibrated share interval is not available for this scope.'
                hint='Review the share chart and supporting evidence before changing quantities.'
        result.update(value=value,unit=unit if points else 'n/a',series=points,state=state,deviation=deviation,action_hint=hint)
        return result

def recap(session,plan,cutoff,expected_reader):
    from ..models import Plan, PurchaseSuggestion
    from sqlalchemy import select
    previous=session.scalar(select(Plan).where(Plan.week_start<plan.week_start).order_by(Plan.week_start.desc()).limit(1))
    if not previous: return None
    end=min(cutoff,previous.week_start+timedelta(days=7),plan.week_start)
    if end<=previous.week_start: return None
    totals=session.execute(text('SELECT COALESCE(SUM(ordered_units),0) AS ordered,COALESCE(SUM(shipped_units),0) AS shipped FROM store_orders WHERE date>=:start AND date<:end'),{'start':previous.week_start,'end':end}).one()
    confirmed=list(session.scalars(select(PurchaseSuggestion).where(PurchaseSuggestion.plan_id==previous.id,PurchaseSuggestion.status=='confirmed',PurchaseSuggestion.order_date<end)))
    info=workflow.state(previous);review=info.get('approved_review',info.get('review',{}));selected=review.get('selection')
    if review.get('items') is not None:
        from ..models import WatchItem
        watches=[WatchItem(**snapshot) for snapshot in review['items']]
    else: watches=[w for w in workflow.watches(session,previous.id) if (w.id in selected if selected is not None else w.status=='active')]
    from .service import plan_series
    data=WatchData(session,end,lambda tag,districts,start,cutoff:plan_series(previous,tag,districts,start,cutoff));projection=info.get('approved_projection')
    views=[data.view(w,previous,projection,recap=True) for w in watches]
    return {'plan_id':previous.id,'week_start':previous.week_start.isoformat(),'facts_through':(end-timedelta(days=1)).isoformat(),'ordered_units':int(totals.ordered),'shipped_units':int(totals.shipped),'fill_rate':float(totals.shipped/totals.ordered) if totals.ordered else 0,'confirmed_orders':len(confirmed),'confirmed_cases':sum(w.final_cases or 0 for w in confirmed),'watch_total':len(views),'watch_warning':sum(w['state']=='warning' for w in views),'items':[{'title':w['title'],'state':w['state'],'value':w['value'],'unit':w['unit'],'scope':w['scope']} for w in views],'provenance':'Observed synthetic prior-week service and recorded purchase choices; no causal improvement from demo purchases is asserted.'}
