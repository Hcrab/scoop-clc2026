from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd

from scoop.algorithms import cusum, forecast, runs
from scoop import monitoring as monitor_module, planning
from scoop.ai.investigator import investigate, review_near_misses


def test_monthly_version_cutoffs_and_immutable_historical_selection(monkeypatch):
    monkeypatch.setattr(runs,'get_setting',lambda *args:'42')
    monkeypatch.setattr(runs,'_MODELS',{})
    loaded=[]
    def load(version):
        loaded.append(version)
        effective=pd.Timestamp(version[1:5]+'-'+version[5:7]+'-01').date()
        return SimpleNamespace(version=version,trained_through=effective-pd.Timedelta(days=1))
    monkeypatch.setattr(runs,'_load',load)
    @contextmanager
    def session():
        yield SimpleNamespace(get=lambda *args:True)
    monkeypatch.setattr(runs,'session_scope',session)
    june=runs.monthly_model(date(2026,6,1),None)
    assert june.trained_through==date(2026,5,31)
    assert runs.monthly_model(date(2026,6,30),None) is june
    assert runs.monthly_model(date(2026,7,1),None).trained_through==date(2026,6,30)
    assert runs.monthly_model(date(2026,8,1),None).trained_through==date(2026,7,31)
    assert runs.monthly_model(date(2026,6,15),None) is june
    assert len(loaded)==3
    meta=runs.model_metadata(date(2026,7,13))
    assert meta['calibration_end']=='2026-06-30'
    assert meta['calibration_source_version']=='M202606-v2-s42'


def test_monitoring_resets_at_each_model_boundary(monkeypatch,tmp_path):
    monkeypatch.setattr(runs,'get_setting',lambda *args:'42')
    group=SimpleNamespace(id='g',name='Group',skus=('A',))
    dates=pd.date_range('2026-05-01','2026-08-31')
    residual=pd.DataFrame({'date':dates,'group':['g']*len(dates),'district':['d']*len(dates),'resid':[2.]*len(dates)})
    static=SimpleNamespace(products=pd.DataFrame({'sku':['A']}),stores=pd.DataFrame({'store_id':['S'],'district':['d']}))
    def run_for(day):
        return SimpleNamespace(model=SimpleNamespace(version=runs.version_for(day)),metadata=runs.model_metadata(day))
    monkeypatch.setattr(monitor_module,'artifacts',lambda:SimpleNamespace(static=static,run_for=run_for,expectations=pd.DataFrame()))
    monkeypatch.setattr(monitor_module,'load_groups',lambda:[group])
    monkeypatch.setattr(monitor_module,'membership',lambda *args:pd.DataFrame([[1]],index=['A'],columns=['g']))
    monkeypatch.setattr(monitor_module,'_actual_units',lambda:pd.DataFrame())
    monkeypatch.setattr(monitor_module,'_cache_dir',lambda:tmp_path)
    monkeypatch.setattr(cusum,'residuals',lambda *args:residual)
    cal=cusum.Calibration(pd.Series({('g','d'):1.}),pd.Series({('g','d'):0.}),5.,np.array([0.,1.]))
    monkeypatch.setattr(cusum,'calibrate',lambda *args:cal)
    monitored=monitor_module.build()
    series=monitored.series.set_index('date')
    assert series.loc['2026-06-30','s_up']>50
    assert series.loc['2026-07-01','s_up']==1.75
    assert series.loc['2026-08-01','s_up']==1.75
    assert monitored.series_for(date(2026,7,1),through=date(2026,6,30)).empty
    assert monitored.calibration_frames['M202607-v2-s42'].date.max()==pd.Timestamp('2026-06-30')


def test_old_multiplier_retires_after_training_and_future_evidence_is_rejected():
    model=SimpleNamespace(version='July',trained_through=date(2026,6,30))
    old={'bucket':'more','factor':1.4,'origin_model_version':'June','evidence_through':'2026-06-28'}
    current={**old,'origin_model_version':'July','evidence_through':'2026-07-12'}
    future={**old,'origin_model_version':'August','evidence_through':'2026-08-05'}
    original=old.copy()
    assert planning.active_directions(date(2026,7,13),[old,current,future],model)==[current]
    assert old==original
    june=SimpleNamespace(version='June',trained_through=date(2026,5,31))
    assert planning.active_directions(date(2026,6,29),[old],june)==[old]


def test_training_frame_never_reads_future_labels(monkeypatch):
    monkeypatch.setattr(forecast,'issued_daily_weather',lambda *args:None)
    def features(static,dates,weather):
        return pd.DataFrame({'date':dates,'store_id':['S']*len(dates),'sku':['A']*len(dates),
            'district':['d']*len(dates),'format':['cup']*len(dates),'family':['fruit']*len(dates)})
    monkeypatch.setattr(forecast,'build_features',features)
    orders=pd.DataFrame({'date':pd.to_datetime(['2026-05-31','2026-06-01']),'store_id':['S','S'],
                        'sku':['A','A'],'ordered_units':[10,999999]})
    first=forecast.training_frame(None,date(2026,5,31),date(2026,5,31),orders=orders)
    orders.loc[1,'ordered_units']=-1000
    pd.testing.assert_frame_equal(first,forecast.training_frame(None,date(2026,5,31),date(2026,5,31),orders=orders))
    assert first.ordered_units.tolist()==[10]


def test_bottom_up_mean_is_coherent_for_two_stores(monkeypatch):
    forecast._PROTECTION_CACHE.clear()
    forecast._DAILY_MEAN_CACHE.clear()
    static=SimpleNamespace(products=pd.DataFrame({'sku':['A'],'lead_time_days':[2],'review_days':[7],'order_weekday':[2]}))
    monkeypatch.setattr(forecast,'forecast_weather',lambda *args:None)
    def features(static,dates,weather):
        return pd.MultiIndex.from_product([dates,['S1','S2'],['A']],names=['date','store_id','sku']).to_frame(index=False)
    monkeypatch.setattr(forecast,'build_features',features)
    class Model:
        def predict(self,frame,**kwargs):
            return frame.assign(mean=frame.store_id.map({'S1':10.,'S2':20.}))
    total,stores=forecast.protection_forecast(Model(),static,date(2026,7,12),order_calendar=True)
    assert total['mean'].iloc[0]==330
    assert stores['mean'].sum()==total['mean'].sum()


def test_promotion_on_other_sku_does_not_explain_group_excess():
    dates=pd.date_range('2026-06-01',periods=14)
    grid=pd.MultiIndex.from_product([dates,['S1','S2','S3'],['A','B']],names=['date','store_id','sku']).to_frame(index=False)
    actual=grid.assign(ordered_units=np.where(grid.sku=='A',30.,10.),shipped_units=10.)
    expected=grid.assign(mean=10.)
    promos=pd.DataFrame({'sku':['B'],'start_date':[date(2026,6,1)],'end_date':[date(2026,6,14)],'note':['B only']})
    verdict=investigate(skus=['A','B'],districts=['d'],direction='up',start=dates.min(),as_of=dates.max(),
        actual=actual,expected=expected,store_district=pd.Series({'S1':'d','S2':'d','S3':'d'}),
        promotions=promos,weather=pd.DataFrame({'date':dates,'tmax':[25.]*len(dates)}),training_tmax=30.)
    promo=next(check for check in verdict.checks if check.name=='promotion')
    assert not promo.passed
    assert promo.data['share']==0
    assert verdict.label=='persistent'


def test_weak_review_budget_and_each_result_has_scope():
    dates=pd.date_range('2026-06-01',periods=14)
    series=pd.MultiIndex.from_product([dates,['d1','d2'],['g1','g2']],names=['date','district','group']).to_frame(index=False).assign(z=1.)
    alarms=pd.DataFrame({'group':['g1','g2'],'direction':['up','up'],'statistic':[4.,3.],'near_miss':[True,True]})
    cal=cusum.Calibration(pd.Series(dtype=float),pd.Series(dtype=float),5.,np.arange(10))
    reviews=review_near_misses(alarms,series,cal,dates.max(),budget=4)
    assert len(reviews)==4
    assert {r['method'] for r in reviews}=={'network_pool','recent_week','district_split'}
    assert all(r['status']=='exploratory' and r['districts'] and r['window_end']=='2026-06-14' for r in reviews)


def test_new_direction_factor_does_not_reuse_old_model_residuals(monkeypatch):
    dates=pd.date_range('2026-06-20','2026-07-12')
    series=pd.DataFrame({'date':dates,'group':['g']*len(dates),'district':['d']*len(dates),
        'actual_share':[.2]*len(dates),'expected_share':np.where(dates.month==6,.1,.2)})
    monkeypatch.setattr(planning,'monitoring',lambda:SimpleNamespace(series=series))
    stats=planning._share_stats('g',['d'],pd.Timestamp('2026-07-01'),pd.Timestamp('2026-07-12'))
    assert stats['share_now']/stats['share_expected']==1


def test_received_arrival_is_not_counted_twice_in_replay_capacity(monkeypatch):
    from scoop import evaluate
    products=pd.DataFrame({'sku':['A'],'order_weekday':[0],'lead_time_days':[2],'review_days':[7],
        'units_per_case':[10],'cases_per_pallet':[10],'price_hkd':[10.],'cost_hkd':[6.],'moq_cases':[3]})
    monkeypatch.setattr(evaluate,'artifacts',lambda:SimpleNamespace(static=SimpleNamespace(products=products)))
    def sql(query,**kwargs):
        if 'SUM(ordered_units)' in query:
            dates=pd.date_range('2026-05-04','2026-06-01')
            return pd.DataFrame({'date':dates,'sku':['A']*len(dates),'u':[10]*len(dates)})
        if 'node_inventory' in query:
            return pd.DataFrame({'sku':['A'],'on_hand_units':[90]})
        if 'purchase_orders' in query:
            return pd.DataFrame({'sku':['A'],'units':[20],'received_date':[date(2026,6,1)]})
        return pd.DataFrame({'capacity_pallets':[1.]})
    monkeypatch.setattr(evaluate,'read_sql',sql)
    checked=[]
    def suggest(as_of,directions,**kwargs):
        checked.append(kwargs['position'].on_hand_units.iloc[0])
        assert as_of not in kwargs['pending_arrivals']
        assert kwargs['position'].on_order.iloc[0]==0
        return pd.DataFrame({'sku':['A'],'final_cases':[0]})
    monkeypatch.setattr(evaluate,'suggest_orders',suggest)
    result=evaluate.replay('scoop_forecast',start=date(2026,6,1),end=date(2026,6,1))
    assert checked==[110]
    assert result['peak_pallets_before_shipping']==1.1
