import pandas as pd
import pytest
from types import SimpleNamespace
from scoop.cohort_cards import build_cards, build_observations, cohort_name
from test_api_state import api


def test_district_cards_share_value_instead_of_duplicating_it():
    def leaf(key, districts, path):
        return {'id':key,'districts':districts,'tag_path':path,'skus':['A'],
                'split_p_values':[.01],'posterior_mean':.2,'interval_80':[.1,.3]}
    units=[{'sku':'A','district':d,'leaf_id':d,'expected_recent':v,'recent_A':v*1.2,'recent_E':v}
           for d,v in [('north',30),('south',70)]]
    family={'id':'family:all','included':True}
    fit={'leaves':[leaf(d,[d],[family,{'id':'district:north','included':d=='north'}]) for d in ['north','south']],
         'units':units,'sku_factors':{'A':{'f10':1.1,'f50':1.2,'f90':1.3}},'method':{}}
    orders=pd.DataFrame([{'sku':'A','final_cases':10,'demand_p10':80,'demand_p50':100,'demand_p90':120,'inventory_position':0,'projected_pallets':1}])
    orders.attrs.update(capacity_pallets=.5,inherited_peak_pallets=.8)
    baseline=orders.copy();baseline['final_cases']=0
    products=pd.DataFrame([{'sku':'A','units_per_case':10,'cases_per_pallet':10,'price_hkd':10,'cost_hkd':5}])
    split=build_cards(fit,orders,baseline,products,{'family:all':SimpleNamespace(name='All products',dimension='family')}, {'A':'A'})
    fit['leaves']=[leaf('all',['north','south'],[family])]
    fit['units']=[{**u,'leaf_id':'all'} for u in units]
    combined=build_cards(fit,orders,baseline,products,{'family:all':SimpleNamespace(name='All products',dimension='family')}, {'A':'A'})[0]
    assert combined['inherited_peak_pallets']==.8
    assert combined['physical_capacity_excess_pallets']==.5
    assert combined['fits_physical_capacity'] is False
    assert sum(c['expected_lost_margin_avoided'] for c in split)==pytest.approx(combined['expected_lost_margin_avoided'])
    assert sum(c['case_change'] for c in split)==combined['case_change']
    assert sum(c['pallet_change'] for c in split)==pytest.approx(combined['pallet_change'])
    assert sorted(c['case_change'] for c in split)==[3,7]


def test_positive_parent_exclusions_name_other_without_inventing_format():
    groups={'water':SimpleNamespace(name='Water-based',dimension='family'),
            'calorie':SimpleNamespace(name='Mid calorie',dimension='nutrition'),
            'choc':SimpleNamespace(name='Chocolate',dimension='flavour')}
    leaf={'tag_path':[{'id':'water','included':False},{'id':'calorie','included':True},
                      {'id':'choc','included':False},{'id':'district:Kowloon','included':True}],
          'districts':['Kowloon']}
    assert cohort_name(leaf,groups)=='Other mid calorie · Kowloon'


def test_all_negative_leaf_is_observed_but_has_no_adjustment_card():
    leaf={'id':'excluded','districts':['South'],'tag_path':[{'id':'family:water','included':False}],
          'skus':['A'],'split_p_values':[.01],'posterior_mean':.2,'interval_80':[.1,.3]}
    result={'leaves':[leaf],'units':[],'sku_factors':{'A':{}},'method':{}}
    orders=pd.DataFrame([{'sku':'A','final_cases':10,'demand_p10':80,'demand_p50':100,
                          'demand_p90':120,'inventory_position':0,'projected_pallets':1}])
    orders.attrs.update(capacity_pallets=2)
    baseline=orders.copy();baseline['final_cases']=0
    products=pd.DataFrame([{'sku':'A','units_per_case':10,'cases_per_pallet':10,'price_hkd':10,'cost_hkd':5}])
    cards=build_cards(result,orders,baseline,products,{}, {'A':'A'})
    observations=build_observations(result,cards,{})
    assert cards==[]
    assert observations[0]['name']=='Other products'
    assert observations[0]['in_card'] is False and observations[0]['card_id'] is None


def test_detail_and_cohort_endpoint_share_saved_leaf_observations(api):
    from scoop.models import Plan
    client,scope,_,_=api
    positive={'id':'leaf-0','tag_path':[{'id':'family:fruit','included':True}],
              'districts':['Kowloon'],'skus':['IC001'],'posterior_mean':.2,'interval_80':[.1,.3]}
    negative={**positive,'id':'leaf-1','tag_path':[{'id':'family:fruit','included':False}]}
    with scope() as session:
        plan=session.get(Plan,'TESTAPI')
        plan.summary={'cohort_model':{'leaves':[positive,negative],'method':{}},
                      'cohort_cards':[{'id':'leaf-0','name':'Fruit','skus':['IC001'],'districts':['Kowloon'],
                                       'effect_pct':20,'interval_pct':[10,30], 'case_change':4,'pallet_change':.4}]}
    detail=client.get('/api/plans/TESTAPI').json()
    cohorts=client.get('/api/plans/TESTAPI/cohorts').json()
    assert [item['id'] for item in detail['cohort_observations']]==['leaf-0','leaf-1']
    assert cohorts['observations']==detail['cohort_observations']
    assert detail['cohort_cards']==cohorts['cards']
    assert detail['cohort_observations'][0]['card_id']=='leaf-0'
    assert detail['cohort_observations'][1]['card_id'] is None
    with scope() as session:
        assert 'cohort_observations' not in session.get(Plan,'TESTAPI').summary
