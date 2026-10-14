"""Bounded, read-only investigations over catalog intersections and issued forecasts.

Queries use fixed ORM statements and prepared monthly model outputs. They never
train a model, classify a finding, inspect synthetic answer keys, or save a plan.
"""
from dataclasses import asdict
from datetime import timedelta
import json
import math

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ..algorithms import cusum, groups, runs
from ..algorithms.shiftshare import decompose
from ..models import DirectionItem, Node, Product, Promotion, PurchaseOrder, Store, StoreOrder


class Parameters(BaseModel):
    model_config=ConfigDict(extra='forbid')


class Scope(Parameters):
    group_ids:list[str]=Field(min_length=1,max_length=3)
    districts:list[str]=Field(default_factory=list,max_length=8)


class Historical(Scope):
    window_days:int=Field(default=14,ge=7,le=28,strict=True)


class GroupQuery(Historical):
    denominator_group_id:str|None=None


class Preview(Scope):
    factor:float=Field(ge=.5,le=1.5,allow_inf_nan=False)


TOOLS={
    'catalog_groups':(Parameters,'List available catalog tags and numeric bands, their members and districts. No event hints.'),
    'query_group':(GroupQuery,'Investigate the AND intersection of 1-3 catalog groups using requested units and shared monthly expected demand through the day before the plan. Compare recent/before periods, parents, contributors, shift-share and exploratory past-calibrated CUSUM. An optional denominator must encompass every selected product. Ad hoc checks do not have family-wide FDR significance.'),
    'query_operations':(Historical,'Check promotions, observed fulfillment and supplier receipt delays for the same intersection through the plan cutoff, plus expected open-order arrivals known then. Future actual receipts are never revealed.'),
    'preview_group_orders':(Preview,'Read-only order-up-to and capacity preview for an AND intersection. Replace affected district buying factors with 0.5-1.5 without compounding overlapping groups. Compare with the existing plan directions; does not apply buying changes or confirm purchases.'),
}


def declarations():
    return [{'name':name,'description':description,'parametersJsonSchema':model.model_json_schema()}
            for name,(model,description) in TOOLS.items()]


def _groups(session):
    # Reuse the planner's frozen group definitions and band cut points.
    catalog={g.id:g for g in groups.load_groups()}
    products=list(session.scalars(select(Product).order_by(Product.sku)))
    if products:
        prices=np.round([p.price_hkd/p.size_ml*100 for p in products],2)
        bands=np.digitize(prices,np.quantile(prices,[1/3,2/3]),right=True)
        for band,label in enumerate(('Lower price / 100 ml','Mid price / 100 ml','Higher price / 100 ml')):
            skus=tuple(p.sku for p,b in zip(products,bands) if b==band)
            if len(skus)>=groups.MIN_SKUS:
                identifier=f'band:price_100ml:{band}'
                catalog[identifier]=groups.Group(identifier,label,'price_100ml',skus)
    return catalog


def _scope(session,args):
    catalog=_groups(session)
    if any(g not in catalog for g in args.group_ids):raise ValueError('Choose group IDs from catalog_groups.')
    ids=sorted(set(args.group_ids))
    products={p.sku:p for p in session.scalars(select(Product).order_by(Product.sku))}
    stores={s.id:s for s in session.scalars(select(Store).order_by(Store.id))}
    available=sorted({s.district for s in stores.values()})
    if set(args.districts)-set(available):raise ValueError('Choose districts from catalog_groups.')
    districts=sorted(set(args.districts)) or available
    selected=set.intersection(*(set(catalog[g].skus) for g in ids)) & set(products)
    return catalog,products,stores,ids,districts,selected


def _expectations(session):
    if runs._ARTIFACTS is not None:
        return runs._ARTIFACTS.expectations.copy()
    from ..db import get_setting
    path=runs.CACHE / f"seed{get_setting('seed','42')}-{runs.LOGIC_VERSION}" / 'expectations-Apr-Aug.pkl'
    if not path.is_file():raise ValueError('Prepared monthly demand expectations are unavailable. Prepare this simulation before investigating it.')
    return pd.read_pickle(path)


def _frames(session,plan,stores,days):
    cutoff=plan.week_start-timedelta(days=1)
    start=cutoff-timedelta(days=days-1)
    columns=('date','store_id','sku','ordered_units','shipped_units')
    actual=pd.DataFrame([dict(zip(columns,r)) for r in session.execute(
        select(*(getattr(StoreOrder,c) for c in columns)).where(StoreOrder.date.between(start,cutoff)))],columns=columns)
    expected=_expectations(session)
    actual['date']=pd.to_datetime(actual.date)
    expected=expected.copy();expected['date']=pd.to_datetime(expected.date)
    expected=expected[expected.date.between(pd.Timestamp(start),pd.Timestamp(cutoff))].copy()
    mapping={key:value.district for key,value in stores.items()}
    for frame in (actual,expected):frame['district']=frame.store_id.map(mapping)
    return actual,expected,cutoff


def _filter(frame,start,end,districts,skus=None):
    mask=frame.date.between(pd.Timestamp(start),pd.Timestamp(end)) & frame.district.isin(districts)
    if skus is not None:mask &= frame.sku.isin(skus)
    return frame[mask].copy()


def _ratio(a,b):
    return float(a/b) if a is not None and b is not None and b>0 else None


def _stats(actual,expected,skus,denominator):
    ordered=float(actual[actual.sku.isin(skus)].ordered_units.sum())
    selected_expected=expected[expected.sku.isin(skus)]
    forecast=float(selected_expected['mean'].sum()) if len(selected_expected) or not skus else None
    total=float(actual[actual.sku.isin(denominator)].ordered_units.sum())
    denominator_expected=expected[expected.sku.isin(denominator)]
    expected_total=float(denominator_expected['mean'].sum()) if len(denominator_expected) else None
    return {'requested_units':ordered,'expected_units':forecast,'excess_units':ordered-forecast if forecast is not None else None,
            'denominator_requested_units':total,'denominator_expected_units':expected_total,
            'actual_share':_ratio(ordered,total),'expected_share':_ratio(forecast,expected_total),
            'observed_days':int(actual.date.nunique()),'expected_days':int(expected.date.nunique())}


def _daily(actual,expected,skus,denominator,start,end,districts):
    rows=[]
    for day in pd.date_range(start,end):
        stats=_stats(_filter(actual,day,day,districts),_filter(expected,day,day,districts),skus,denominator)
        rows.append({'date':day.date().isoformat(),**stats})
    return rows


def _contributors(actual,expected,key,products,stores):
    a=actual.groupby(key).ordered_units.sum()
    e=expected.groupby(key)['mean'].sum()
    frame=pd.concat([a.rename('requested_units'),e.rename('expected_units')],axis=1)
    frame['requested_units']=frame.requested_units.fillna(0)
    frame['excess_units']=frame.requested_units-frame.expected_units
    frame=frame.assign(_rank=frame.excess_units.abs().fillna(0)).sort_values(['_rank',key],ascending=[False,True]).head(10)
    return [{key:str(k),'name':products[k].name if key=='sku' and k in products else stores[k].name if k in stores else str(k),
             'requested_units':float(r.requested_units),'expected_units':float(r.expected_units),'excess_units':float(r.excess_units)}
            for k,r in frame.iterrows()]


def _cusum(actual,expected,skus,denominator,districts,start,end):
    calib_start=pd.Timestamp(start)-pd.Timedelta(days=28)
    calib_end=pd.Timestamp(start)-pd.Timedelta(days=1)
    calibration=[];recent=[];skipped=[]
    for district in districts:
        def residual_rows(a,b):
            rows=_daily(actual,expected,skus,denominator,a,b,[district])
            return [{'date':pd.Timestamp(r['date']),'group':'intersection','district':district,
                     'resid':r['actual_share']-r['expected_share']} for r in rows
                    if r['actual_share'] is not None and r['expected_share'] is not None]
        prior=residual_rows(calib_start,calib_end);live=residual_rows(start,end)
        if len(prior)<14 or len(live)<7:
            skipped.append(district);continue
        calibration.extend(prior);recent.extend(live)
    info={'exploratory':True,'family_fdr_significant':False,'calibration_start':calib_start.date().isoformat(),
          'calibration_end':calib_end.date().isoformat(),'calibration_is_verified_in_control':False,
          'skipped_districts':skipped,'series':[],'checks':[]}
    if not calibration:return {**info,'status':'insufficient_history'}
    calibration=pd.DataFrame(calibration)
    cal=cusum.calibrate(calibration)
    series=cusum.monitor(pd.DataFrame(recent),cal)
    checks=[]
    for district,part in series.groupby('district'):
        last=part.sort_values('date').iloc[-1]
        checks.append({'district':district,'up':float(last.s_up),'down':float(last.s_down),'threshold':float(cal.h),
                       'crossed':bool(max(last.s_up,last.s_down)>=cal.h),
                       'approximate_bootstrap_p':cal.p_value(float(max(last.s_up,last.s_down)))})
    return {**info,'status':'computed','checks':checks[:8],
            'series':[{'date':r.date.date().isoformat(),'district':r.district,'up':float(r.s_up),'down':float(r.s_down)}
                      for r in series.itertuples()][:224]}


def _query_group(session,plan,args):
    catalog,products,stores,ids,districts,skus=_scope(session,args)
    denominator=set(products)
    if args.denominator_group_id:
        if args.denominator_group_id not in catalog:raise ValueError('Choose a denominator from catalog_groups.')
        denominator=set(catalog[args.denominator_group_id].skus)&set(products)
        if not skus<=denominator:raise ValueError('The denominator must encompass all selected products.')
    actual,expected,cutoff=_frames(session,plan,stores,args.window_days*2+28)
    start=cutoff-timedelta(days=args.window_days-1)
    before_start=start-timedelta(days=args.window_days)
    a=_filter(actual,start,cutoff,districts);e=_filter(expected,start,cutoff,districts)
    ba=_filter(actual,before_start,start-timedelta(days=1),districts)
    be=_filter(expected,before_start,start-timedelta(days=1),districts)
    recent=_stats(a,e,skus,denominator);before=_stats(ba,be,skus,denominator)
    decomposition=decompose(before['denominator_requested_units'],before['requested_units'],
                            recent['denominator_requested_units'],recent['requested_units'])
    members=a[a.sku.isin(skus)];predicted=e[e.sku.isin(skus)]
    actual_keys=set(members[['date','store_id','sku']].itertuples(index=False,name=None))
    expected_keys=set(predicted[['date','store_id','sku']].itertuples(index=False,name=None))
    coverage=_ratio(len(actual_keys&expected_keys),len(actual_keys))
    adequate=bool(len(skus)>=groups.MIN_SKUS and recent['observed_days']>=7 and recent['requested_units']>=100
                  and coverage is not None and coverage>=.95 and recent['expected_share'] is not None)
    return {'scope':{'group_ids':ids,'districts':districts,'skus':sorted(skus),'sku_count':len(skus),
                     'denominator_group_id':args.denominator_group_id},'evidence_through':cutoff.isoformat(),
            'window_start':start.isoformat(),'before_start':before_start.isoformat(),'window_days':args.window_days,
            'exploratory':True,'family_fdr_significant':False,'recent':recent,'before':before,
            'sample':{'adequate':adequate,'sku_count':len(skus),'store_count':int(members.store_id.nunique()),
                      'expected_row_coverage':coverage,'rule':'At least 3 products, 7 observed days, 100 requested units and 95% expected-row coverage; this is an adequacy heuristic.'},
            'daily':_daily(actual,expected,skus,denominator,start,cutoff,districts),
            'parents':[{'group_id':g,'name':catalog[g].name,'denominator':'all_catalog',
                        **_stats(a,e,set(catalog[g].skus),set(products))} for g in ids],
            'sku_contributors':_contributors(members,predicted,'sku',products,stores),
            'store_contributors':_contributors(members,predicted,'store_id',products,stores),
            'shift_share':{**asdict(decomposition),'change':decomposition.change,
                           'basis':'Equal-length requested-unit windows; arithmetic decomposition, not evidence of individual customer switching.'},
            'cusum':_cusum(actual,expected,skus,denominator,districts,start,cutoff) if skus else {'status':'empty_group','exploratory':True,'family_fdr_significant':False,'checks':[],'series':[]},
            'model_versions':sorted(set(expected.model_version.dropna().astype(str))) if 'model_version' in expected else [],
            'applied':False}


def _operations(session,plan,args):
    _,products,stores,ids,districts,skus=_scope(session,args)
    cutoff=plan.week_start-timedelta(days=1);start=cutoff-timedelta(days=args.window_days-1)
    chosen_stores=[key for key,value in stores.items() if value.district in districts]
    orders=list(session.scalars(select(StoreOrder).where(StoreOrder.date.between(start,cutoff),
                                                        StoreOrder.sku.in_(skus),StoreOrder.store_id.in_(chosen_stores))))
    requested=sum(o.ordered_units for o in orders);shipped=sum(o.shipped_units for o in orders)
    promotions=list(session.scalars(select(Promotion).where(Promotion.sku.in_(skus),Promotion.start_date<=cutoff,Promotion.end_date>=start).order_by(Promotion.start_date,Promotion.id)))
    purchase=list(session.scalars(select(PurchaseOrder).where(PurchaseOrder.sku.in_(skus),PurchaseOrder.order_date<=cutoff).order_by(PurchaseOrder.expected_date,PurchaseOrder.id)))
    received=[p for p in purchase if p.received_date is not None and start<=p.received_date<=cutoff]
    open_orders=[p for p in purchase if p.received_date is None or p.received_date>cutoff]
    return {'scope':{'group_ids':ids,'districts':districts,'skus':sorted(skus)},'evidence_through':cutoff.isoformat(),'window_start':start.isoformat(),
            'fulfillment':{'requested_units':requested,'shipped_units':shipped,'fill_rate':_ratio(shipped,requested),
                           'unfilled_units':max(0,requested-shipped),'store_count':len({o.store_id for o in orders})},
            'promotions':{'overlap_count':len(promotions),'items':[{'sku':p.sku,'start_date':max(start,p.start_date).isoformat(),
                          'end_date':min(cutoff,p.end_date).isoformat(),'discount_pct':p.discount_pct} for p in promotions[:20]]},
            'observed_receipts':{'count':len(received),'late_count':sum(p.received_date>p.expected_date for p in received),
                                 'mean_delay_days':float(np.mean([(p.received_date-p.expected_date).days for p in received])) if received else None,
                                 'items':[{'sku':p.sku,'supplier_id':p.supplier_id,'expected_date':p.expected_date.isoformat(),
                                           'received_date':p.received_date.isoformat(),'delay_days':(p.received_date-p.expected_date).days} for p in received[:20]]},
            'known_open_arrivals':{'count':len(open_orders),'items':[{'sku':p.sku,'supplier_id':p.supplier_id,'ordered_date':p.order_date.isoformat(),
                                   'expected_date':p.expected_date.isoformat(),'cases':p.cases,'overdue_at_cutoff':p.expected_date<cutoff} for p in open_orders[:20]]},
            'warehouse_scope':'Supplier receipts and expected arrivals cover shared warehouse products; they are not district-specific stock.',
            'applied':False}


def _preview_ready(plan):
    # suggest_orders may otherwise lazily train/write models. Require a prepared run.
    art=runs._ARTIFACTS
    if art is None or runs.version_for(plan.week_start) not in art.monthly_runs:
        raise ValueError('Prepared monthly purchasing artifacts are unavailable. Prepare this simulation before previewing orders.')


def _forecast_split(plan):
    from ..planning import protection_forecast
    art=runs._ARTIFACTS
    model=art.monthly_runs[runs.version_for(plan.week_start)].model
    _,split=protection_forecast(model,art.static,plan.week_start-timedelta(days=1),order_calendar=True)
    return split


def _preview(session,plan,args):
    from ..planning import suggest_orders
    catalog,_,stores,ids,districts,skus=_scope(session,args)
    _preview_ready(plan)
    directions=[{'bucket':d.bucket,'tag_id':d.tag_id,'sku':d.sku,'districts':list(d.districts),'factor':d.factor}
                for d in session.scalars(select(DirectionItem).where(DirectionItem.plan_id==plan.id).order_by(DirectionItem.id))]
    changed=[];affected={sku:{s.district:1. for s in stores.values()} for sku in skus}
    for direction in directions:
        members={direction['sku']} if direction.get('sku') else set(catalog[direction['tag_id']].skus) if direction.get('tag_id') in catalog else set()
        if not members&skus:
            changed.append(dict(direction));continue
        for sku in sorted(members):
            if sku not in skus:
                changed.append({**direction,'sku':sku,'tag_id':None});continue
            if direction['bucket'] in {'more','less','clear'}:
                for district in direction['districts']:
                    if district in affected[sku]:affected[sku][district]*=0 if direction['bucket']=='clear' else direction['factor']
    effective={}
    if skus:
        split=_forecast_split(plan).copy()
        split['district']=split.store_id.map({key:s.district for key,s in stores.items()})
        for sku in sorted(skus):
            policy=affected[sku]
            for district in districts:policy[district]=args.factor
            weights=split[split.sku==sku].groupby('district')['mean'].sum()
            factor=float(sum(float(units)*policy.get(district,1.) for district,units in weights.items())/weights.sum()) if weights.sum()>0 else 1.
            effective[sku]=factor
            # One weighted override across all stores avoids multiplying two
            # disjoint district contributions as if they were overlapping edits.
            changed.append({'sku':sku,'tag_id':None,'districts':sorted(set(s.district for s in stores.values())),
                            'factor':factor,'bucket':'more' if factor>1 else 'less' if factor<1 else 'hold'})
    kwargs={'service_level':plan.service_level,'goal':plan.goal}
    base=suggest_orders(plan.week_start,directions,**kwargs)
    after=suggest_orders(plan.week_start,changed,**kwargs) if skus else base.copy()
    b=base.set_index('sku');c=after.set_index('sku')
    rows=[]
    for sku in sorted(set(b.index)|set(c.index)):
        before_cases=int(b.loc[sku,'final_cases']) if sku in b.index else 0
        after_cases=int(c.loc[sku,'final_cases']) if sku in c.index else 0
        if before_cases!=after_cases or sku in skus:
            rows.append({'sku':sku,'selected':sku in skus,'baseline_cases':before_cases,'preview_cases':after_cases,
                         'delta_cases':after_cases-before_cases,
                         'baseline_p50_units':float(b.loc[sku,'demand_p50']) if sku in b.index else 0,
                         'preview_p50_units':float(c.loc[sku,'demand_p50']) if sku in c.index else 0})
    rows.sort(key=lambda r:(-abs(r['delta_cases']),r['sku']))
    node=session.get(Node,'DC1')
    capacity=float(node.capacity_pallets) if node else None
    def summary(frame):
        peak=float(frame.projected_pallets.max()) if 'projected_pallets' in frame and len(frame) else None
        return {'cases':int(frame.final_cases.sum()),'p50_units':float(frame.demand_p50.sum()),
                'capacity_cut_cases':int(frame.capacity_cut_cases.sum()),
                'capacity_pallets':capacity,'projected_peak_pallets':peak,
                'above_physical_capacity_pallets':max(0.,peak-capacity) if peak is not None and capacity is not None else None}
    return {'scope':{'group_ids':ids,'districts':districts,'skus':sorted(skus)},'factor':args.factor,
            'forecast_issued':(plan.week_start-timedelta(days=1)).isoformat(),'baseline':summary(base),'preview':summary(after),
            'delta_cases':int(after.final_cases.sum()-base.final_cases.sum()),'changed_product_count':sum(r['delta_cases']!=0 for r in rows),
            'products':rows[:20],'effective_sku_factors':[{'sku':sku,'factor':factor} for sku,factor in sorted(effective.items())][:20],'applied':False,
            'assumptions':'The preview replaces demand factors relative to the forecast, not relative to current purchase quantities. Other products and districts retain existing directions. Forecast protection periods, minimum orders and dated cold-store capacity use the existing purchasing algorithm. Shared capacity can affect other products. The allocator does not worsen inherited overcapacity on a date, but existing arrivals can still exceed physical capacity. Compare projected peak with capacity_pallets before claiming that orders fit.'}


def _json(value):
    if isinstance(value,dict):return {str(k):_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [_json(v) for v in value]
    if isinstance(value,np.generic):value=value.item()
    if isinstance(value,float) and not math.isfinite(value):return None
    return value


def execute(name,args,session,plan):
    if name not in TOOLS:raise ValueError('This exploratory tool is not supported.')
    arguments=TOOLS[name][0].model_validate(args)
    with session.no_autoflush:
        if name=='catalog_groups':
            catalog=_groups(session)
            products={p.sku:p.name for p in session.scalars(select(Product).order_by(Product.sku))}
            result={'groups':[{'id':g.id,'name':g.name,'dimension':g.dimension,'sku_count':len(g.skus),
                               'skus':list(g.skus),'members':[{'sku':sku,'name':products.get(sku,sku)} for sku in g.skus]} for g in sorted(catalog.values(),key=lambda g:g.id)],
                    'districts':sorted(set(session.scalars(select(Store.district)))),
                    'group_rule':'Catalog groups use the existing tag and frozen numeric-band definitions; intersections are AND.'}
        elif name=='query_group':result=_query_group(session,plan,arguments)
        elif name=='query_operations':result=_operations(session,plan,arguments)
        else:result=_preview(session,plan,arguments)
    result=_json(result)
    json.dumps(result,allow_nan=False)
    return result
