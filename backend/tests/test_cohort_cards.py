import pandas as pd
import pytest
from scoop.cohort_cards import build_cards


def test_district_cards_share_value_instead_of_duplicating_it():
    def leaf(key, districts, path):
        return {'id':key,'districts':districts,'tag_path':path,'skus':['A'],
                'split_p_values':[.01],'posterior_mean':.2,'interval_80':[.1,.3]}
    units=[{'sku':'A','district':d,'leaf_id':d,'expected_recent':v,'recent_A':v*1.2,'recent_E':v}
           for d,v in [('north',30),('south',70)]]
    fit={'leaves':[leaf(d,[d],[{'id':'district:north','included':d=='north'}]) for d in ['north','south']],
         'units':units,'sku_factors':{'A':{'f10':1.1,'f50':1.2,'f90':1.3}},'method':{}}
    orders=pd.DataFrame([{'sku':'A','final_cases':10,'demand_p10':80,'demand_p50':100,'demand_p90':120,'inventory_position':0,'projected_pallets':1}])
    orders.attrs.update(capacity_pallets=.5,inherited_peak_pallets=.8)
    baseline=orders.copy();baseline['final_cases']=0
    products=pd.DataFrame([{'sku':'A','units_per_case':10,'cases_per_pallet':10,'price_hkd':10,'cost_hkd':5}])
    split=build_cards(fit,orders,baseline,products,{}, {'A':'A'})
    fit['leaves']=[leaf('all',['north','south'],[])]
    fit['units']=[{**u,'leaf_id':'all'} for u in units]
    combined=build_cards(fit,orders,baseline,products,{}, {'A':'A'})[0]
    assert combined['inherited_peak_pallets']==.8
    assert combined['physical_capacity_excess_pallets']==.5
    assert combined['fits_physical_capacity'] is False
    assert sum(c['expected_lost_margin_avoided'] for c in split)==pytest.approx(combined['expected_lost_margin_avoided'])
    assert sum(c['case_change'] for c in split)==combined['case_change']
    assert sum(c['pallet_change'] for c in split)==pytest.approx(combined['pallet_change'])
    assert sorted(c['case_change'] for c in split)==[3,7]
