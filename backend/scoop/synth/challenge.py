"""Offline seed91 interventions and answer key; never imported by app read tools.

Two district-specific checkerboards preserve each format's total and each
normalised-price bucket's total exactly. Only their intersections move. This
module contains evaluator truth, not operational product descriptions.
"""
from datetime import date
import json
import numpy as np
import pandas as pd

SEED=91
DEFAULT_WEEK='2026-07-27'
MAX_RATE=.28

def cells(products):
    price=(products.price_hkd/products.size_ml*100).round(2).to_numpy()
    band=np.digitize(price,np.quantile(price,[1/3,2/3]),right=True)
    fmt=products['format'].to_numpy()
    return {
        'stick_low':np.flatnonzero((fmt=='stick')&(band==1)),
        'stick_high':np.flatnonzero((fmt=='stick')&(band==2)),
        'cup_low':np.flatnonzero((fmt=='cup')&(band==1)),
        'cup_high':np.flatnonzero((fmt=='cup')&(band==2)),
    }

def answer_key(products,stores):
    """Offline scorer input only. Do not pass this result into assistant context."""
    groups=cells(products)
    if any(len(indices)<3 for indices in groups.values()): raise ValueError('Challenge requires at least three products in every intersection.')
    memberships={name:products.sku.iloc[indices].tolist() for name,indices in groups.items()}
    comparisons={name:{'skus':skus,'districts':['NT East','NT West']} for name,skus in memberships.items()}
    relationships=[]
    for identifier,district,start,full,sign in [
        ('HX91A','Kowloon',date(2026,7,6),date(2026,7,13),1),
        ('HX91B','HK Island',date(2026,7,13),date(2026,7,20),-1),
    ]:
        relationships.append(dict(id=identifier,district=district,store_ids=stores.loc[stores.district==district,'id'].tolist(),start_date=start.isoformat(),full_effect_date=full.isoformat(),end_date='2026-08-31',direction_by_cell={name:('up' if coefficient*sign>0 else 'down') for name,coefficient in [('stick_low',1),('stick_high',-1),('cup_low',-1),('cup_high',1)]},memberships=memberships,dimensions={'format':['stick','cup'],'price_100ml':{'bands':['middle tercile','upper tercile'],'group_ids':['band:price_100ml:1','band:price_100ml:2']}},effect={'maximum_fraction_of_smallest_cell':MAX_RATE,'ramp':'linear','units_rule':'One identical integer transfer per cell, bounded by 28% of the smallest of the four cell totals on each store-day. Each individual cell changes by at most 28%; larger cells change less.'},negative_controls=comparisons,masking=['stick total','cup total','combined low-price total within stick/cup','combined high-price total within stick/cup','district total']))
    return dict(seed=SEED,default_week=DEFAULT_WEEK,relationships=relationships,unaffected_formats=['cone','tub','sandwich','mochi','multipack'],provenance='Offline synthetic intervention key; not available through operational app tools.')

def apportion(values,amount):
    """Integer allocation, summing exactly to amount, proportional to the row."""
    total=int(values.sum())
    if not total or not amount: return np.zeros(len(values),dtype=np.int64)
    ideal=values.astype(float)*(amount/total)
    allocation=np.floor(ideal).astype(np.int64)
    remainder=amount-int(allocation.sum())
    ranking=np.argsort(-(ideal-allocation),kind='stable')
    allocation[ranking[:remainder]]+=1
    return allocation

def inject(orders,days,stores,products):
    """Mutate ordered demand before DC simulation; return private event rows.

    No RNG draws or extra product attributes are introduced. All single-axis
    marginals named in the key remain exactly unchanged for every store-day.
    """
    key=answer_key(products,stores);groups=cells(products)
    if orders.shape!=(len(days),len(stores),len(products)): raise ValueError('Order cube does not match the catalog and calendar.')
    events=[]
    for relationship in key['relationships']:
        start=date.fromisoformat(relationship['start_date']);full=date.fromisoformat(relationship['full_effect_date']);end=date.fromisoformat(relationship['end_date'])
        store_indices=np.flatnonzero(stores.district.to_numpy()==relationship['district'])
        for di,day in enumerate(days):
            if day<start or day>end: continue
            strength=MAX_RATE*min(1.,(day-start).days/max(1,(full-start).days))
            for si in store_indices:
                row=orders[di,si]
                totals=[int(row[indices].sum()) for indices in groups.values()]
                transfer=int(np.floor(strength*min(totals)))
                if not transfer: continue
                # All allocations use the pre-intervention row, then apply together.
                allocations={name:apportion(row[indices],transfer) for name,indices in groups.items()}
                for name,indices in groups.items():
                    sign=1 if relationship['direction_by_cell'][name]=='up' else -1
                    row[indices]+=sign*allocations[name]
        events.append(dict(id=relationship['id'],kind='intersection',tag_id=None,sku=None,districts=[relationship['district']],start_date=start,end_date=end,expected_label='persistent',note=json.dumps(relationship,sort_keys=True)))
    return pd.DataFrame(events)
