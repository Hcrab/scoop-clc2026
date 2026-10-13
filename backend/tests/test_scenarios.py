from datetime import date
from types import SimpleNamespace
import pandas as pd
import pytest
from scoop.algorithms import forecast


def test_temperature_scenario_changes_only_selected_days_and_preserves_baseline(monkeypatch):
    days = pd.date_range('2026-07-13', periods=14)
    weather = pd.DataFrame({'date':days,'tmax':28.,'rain_mm':3.})
    monkeypatch.setattr(forecast,'forecast_weather',lambda *args:weather.copy())
    monkeypatch.setattr(forecast,'build_features',lambda static,targets,weather:weather)
    class Model:
        def predict(self,features,mean_only=True):
            return features[['date']].assign(sku='A',store_id='S',mean=features.tmax+features.rain_mm)
    model=Model();static=object();issued=date(2026,7,12)
    forecast._DAILY_MEAN_CACHE.clear()
    baseline=forecast.daily_mean(model,static,issued,days)
    scenario=forecast.daily_mean(model,static,issued,days,(date(2026,7,20),date(2026,7,26),35.))
    assert (scenario['mean'].iloc[:7] == baseline['mean'].iloc[:7]).all()
    assert (scenario['mean'].iloc[7:] == 38).all()
    assert forecast.daily_mean(model,static,issued,days).equals(baseline)
    assert (weather.tmax == 28).all()


def test_clear_direction_respects_district_share(monkeypatch):
    from scoop import planning
    monkeypatch.setattr(planning,'monitoring',lambda:SimpleNamespace(store_district={'A':'Kowloon','B':'HK Island'},group_by_id={}))
    split=pd.DataFrame({'sku':['X','X','Y','Y'],'store_id':['A','B','A','B'],'mean':[30,70,20,80]})
    adjustment=planning.sku_adjustments([{'bucket':'clear','sku':'X','districts':['Kowloon'],'factor':0}],split)
    assert adjustment['X']==pytest.approx(.7)
    assert adjustment['Y']==1
