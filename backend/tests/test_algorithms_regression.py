from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from scoop.algorithms.forecast import forecast_weather, issued_daily_weather
from scoop.algorithms.replenish import SkuInput, plan_orders
from scoop.algorithms import cusum


def test_future_weather_cannot_change_issued_fallback():
    static = SimpleNamespace(
        forecasts=pd.DataFrame(columns=['issued_date','target_date','tmax_fc','rain_fc']),
        weather=pd.DataFrame({'date':pd.to_datetime(['2025-01-01','2025-07-01','2026-07-01']),
                              'tmax':[16.,30.,80.], 'rain_mm':[2.,4.,100.]}))
    target = pd.date_range('2026-07-02', periods=1)
    first = forecast_weather(static,date(2025,12,31),target)
    static.weather.loc[2,'tmax']=-1000
    pd.testing.assert_frame_equal(first,forecast_weather(static,date(2025,12,31),target))


def test_daily_weather_uses_previous_issue():
    static=SimpleNamespace(forecasts=pd.DataFrame({
        'issued_date':pd.to_datetime(['2026-01-01','2026-01-02']),
        'target_date':pd.to_datetime(['2026-01-02','2026-01-02']),
        'tmax_fc':[22.,99.], 'rain_fc':[3.,9.]}))
    assert issued_daily_weather(static,pd.date_range('2026-01-02',periods=1)).tmax.iloc[0]==22


def item(sku='A',moq=3,on_hand=0,on_order=0):
    return SkuInput(sku,100,14,10,6,10,10,moq,on_hand,on_order,7)


def test_infeasible_moq_can_be_zeroed():
    plan=plan_orders([item()],np.ones(20),.2)
    assert plan.final_cases.iloc[0]==0
    assert plan.projected_pallets.iloc[0]<=.2


def test_capacity_accounts_pipeline_and_reports_inherited_excess():
    plan=plan_orders([item(on_hand=100,on_order=100)],np.ones(20),1)
    assert plan.final_cases.iloc[0]==0
    assert plan.inherited_overcapacity_pallets.iloc[0]==1


def test_remaining_order_respects_moq():
    plan=plan_orders([item('A'),item('B')],np.ones(20),1.3)
    assert all((plan.final_cases==0)|(plan.final_cases>=3))
    assert plan.projected_pallets.iloc[0]<=1.3


def test_monitor_unknown_chart_does_not_estimate_scale_from_future():
    cal=cusum.Calibration(pd.Series(dtype=float),pd.Series(dtype=float),5,np.array([0.]))
    base=pd.DataFrame({'date':pd.date_range('2026-01-01',periods=3),'group':['g']*3,
                       'district':['d']*3,'resid':[.001,.002,.003]})
    expected=cusum.monitor(base,cal).z.iloc[0]
    base.loc[2,'resid']=1000
    assert cusum.monitor(base,cal).z.iloc[0]==expected


def test_bootstrap_handles_exact_one_block():
    assert cusum._bootstrap_paths([np.ones(7)],2,10,np.random.default_rng(1)).shape==(2,10)


def test_calendar_protection_starts_at_inventory_cutoff(monkeypatch):
    from scoop.algorithms import forecast
    static=SimpleNamespace(products=pd.DataFrame({'sku':['A'],'lead_time_days':[2],
        'review_days':[7],'order_weekday':[2]}))
    monkeypatch.setattr(forecast,'forecast_weather',lambda *args: None)
    monkeypatch.setattr(forecast,'build_features',lambda st, dates, weather: pd.DataFrame(
        {'date':dates,'sku':['A']*len(dates),'store_id':['S1']*len(dates)}))
    class Model:
        def predict(self,features,**kwargs):
            return features.assign(mean=10.)
    fc,_=forecast.protection_forecast(Model(),static,date(2026,7,12),order_calendar=True)
    # Inventory is Sunday close; Monday starts demand, Wednesday is order day.
    assert fc.pdays.iloc[0]==11
    assert fc['mean'].iloc[0]==110


def test_detection_does_not_credit_preexisting_alarm_to_new_event():
    from scoop.evaluate import _first_alarm
    series=pd.DataFrame({'date':pd.date_range('2026-06-01',periods=5),
        'group':['g']*5,'district':['d']*5,'s_up':[6.,7.,8.,0.,6.]})
    assert _first_alarm(series,'g','d','up',5,pd.Timestamp('2026-06-02'))==pd.Timestamp('2026-06-05')


def test_only_significant_persistent_directions_adjust_orders():
    from scoop.planning import default_directions
    base={'share_now':.3,'share_expected':.2,'direction':'up','group':'g',
          'districts':['d'],'display':'Group'}
    rows=default_directions([{**base,'kind':'weak','classification':'persistent'},
                            {**base,'kind':'significant','classification':'one_off'},
                            {**base,'kind':'significant','classification':'persistent'}])
    assert len(rows)==2
    assert rows[0]['bucket']=='hold' and rows[0]['factor']==1
    assert rows[1]['bucket']=='more' and rows[1]['factor']==1.5


def test_replay_orders_from_start_of_day_stock_and_records_arrival_peak(monkeypatch):
    from scoop import evaluate
    products=pd.DataFrame({'sku':['A'],'order_weekday':[0],'lead_time_days':[2],
        'review_days':[7],'units_per_case':[10],'cases_per_pallet':[10],
        'price_hkd':[10.],'cost_hkd':[6.],'moq_cases':[3]})
    monkeypatch.setattr(evaluate,'artifacts',lambda: SimpleNamespace(static=SimpleNamespace(products=products)))
    def sql(query,**kwargs):
        if 'SUM(ordered_units)' in query:
            dates=pd.date_range('2026-05-04','2026-06-01')
            return pd.DataFrame({'date':dates,'sku':['A']*len(dates),'u':[10]*len(dates)})
        if 'node_inventory' in query:
            return pd.DataFrame({'sku':['A'],'on_hand_units':[90]})
        if 'purchase_orders' in query:
            return pd.DataFrame(columns=['sku','units','received_date'])
        return pd.DataFrame({'capacity_pallets':[1.]})
    monkeypatch.setattr(evaluate,'read_sql',sql)
    seen=[]
    def suggest(as_of,dirs,**kwargs):
        seen.append(kwargs['position'].on_hand_units.iloc[0])
        return pd.DataFrame({'sku':['A'],'final_cases':[0]})
    monkeypatch.setattr(evaluate,'suggest_orders',suggest)
    result=evaluate.replay('scoop_forecast',start=date(2026,6,1),end=date(2026,6,1))
    assert seen==[90]
    assert result['peak_pallets_before_shipping']==.9
    assert result['max_pallets']==.8


def test_dated_capacity_allows_order_after_forecast_depletion():
    plan=plan_orders([item(on_hand=90)],np.ones(20),1,
        capacity_baseline=np.array([[90.],[20.]]),arrival_mask=np.array([[False],[True]]))
    assert plan.final_cases.iloc[0]==3
    assert plan.projected_pallets.iloc[0]==.9


def test_dated_capacity_does_not_use_other_day_inherited_excess_as_free_space():
    plan=plan_orders([item()],np.ones(20),1,
        capacity_baseline=np.array([[150.],[80.]]),arrival_mask=np.array([[False],[True]]))
    assert plan.final_cases.iloc[0]==0
    assert plan.inherited_overcapacity_pallets.iloc[0]==.5


def test_sku_only_direction_changes_only_target_sku(monkeypatch):
    from scoop import planning
    monkeypatch.setattr(planning,'monitoring',lambda:SimpleNamespace(
        store_district=pd.Series({'S1':'d'}),group_by_id={}))
    split=pd.DataFrame({'sku':['A','B'],'store_id':['S1','S1'],'mean':[100.,100.]})
    adjusted=planning.sku_adjustments([{'bucket':'more','sku':'A','tag_id':None,
        'districts':['d'],'factor':1.5}],split)
    assert adjusted['A']==1.5 and adjusted['B']==1.
