"""Offline challenge checks: operational tables never carry the answer key."""
from datetime import date,timedelta
import json
import numpy as np
import pandas as pd
import pytest
from scoop.synth import generate as generator
from scoop.synth.challenge import answer_key,cells,inject,apportion

@pytest.fixture
def sample():
    stores,_,products,*_=generator.build_catalog(np.random.default_rng(91))
    days=[date(2026,6,29)+timedelta(days=i) for i in range(35)]
    # Stable operational baseline makes modest intervention contrast directly visible.
    orders=np.random.default_rng(123).poisson(24,(len(days),len(stores),len(products))).astype(np.int64)
    return stores,products,days,orders

def test_reproducible_balanced_intersections_and_controls(sample):
    stores,products,days,baseline=sample
    a=baseline.copy();b=baseline.copy()
    events=inject(a,days,stores,products);other=inject(b,days,stores,products)
    np.testing.assert_array_equal(a,b);pd.testing.assert_frame_equal(events,other)
    assert a.min()>=0 and a.dtype==np.int64
    groups=cells(products);key=answer_key(products,stores)
    assert all(len(v)>=3 for v in groups.values())
    for indices in [np.r_[groups['stick_low'],groups['stick_high']],np.r_[groups['cup_low'],groups['cup_high']],np.r_[groups['stick_low'],groups['cup_low']],np.r_[groups['stick_high'],groups['cup_high']]]:
        np.testing.assert_array_equal(a[:,:,indices].sum(axis=2),baseline[:,:,indices].sum(axis=2))
    np.testing.assert_array_equal(a.sum(axis=2),baseline.sum(axis=2))
    heldout=np.flatnonzero(stores.district.isin(['NT East','NT West']).to_numpy())
    np.testing.assert_array_equal(a[:,heldout,:],baseline[:,heldout,:])
    unaffected=np.flatnonzero(~products['format'].isin(['stick','cup']).to_numpy())
    np.testing.assert_array_equal(a[:,:,unaffected],baseline[:,:,unaffected])
    for relationship in key['relationships']:
        si=np.flatnonzero(stores.district.to_numpy()==relationship['district'])
        di=np.flatnonzero(np.array([day>=date.fromisoformat(relationship['full_effect_date']) for day in days]))
        for name,indices in groups.items():
            old=baseline[np.ix_(di,si,indices)].sum();new=a[np.ix_(di,si,indices)].sum()
            assert .04<abs(new/old-1)<.285
            assert (new>old)==(relationship['direction_by_cell'][name]=='up')
    assert {json.loads(note)['district'] for note in events.note}=={'Kowloon','HK Island'}

def test_no_answer_key_in_catalog_and_no_early_injection(sample):
    stores,products,days,baseline=sample
    catalog=products.copy(deep=True);store_copy=stores.copy(deep=True)
    changed=baseline.copy();inject(changed,days,stores,products)
    pd.testing.assert_frame_equal(products,catalog);pd.testing.assert_frame_equal(stores,store_copy)
    early=[i for i,day in enumerate(days) if day<date(2026,7,6)]
    np.testing.assert_array_equal(changed[early],baseline[early])
    assert not products.description.str.contains('HX91|checkerboard|intersection',case=False).any()

@pytest.mark.parametrize('seed',[42,73])
def test_normal_seeds_follow_original_demand_path(seed,monkeypatch):
    import scoop.synth.challenge as challenge
    monkeypatch.setattr(challenge,'inject',lambda *args:pytest.fail('Normal worlds must not invoke the challenge helper'))
    captured={};original=generator.simulate_dc
    def checked(rng,days,stores,products,suppliers,orders):
        # Independently reproduce the pre-existing RNG path, including weather draws.
        expected_rng=np.random.default_rng(seed)
        st,_,pr,_,_,_,tags=generator.build_catalog(expected_rng)
        weather,_,_=generator.build_weather(expected_rng,days)
        expected,_,_=generator.build_demand(expected_rng,days,st,pr,tags,weather)
        np.testing.assert_array_equal(orders,expected)
        captured['checked']=True
        return original(rng,days,stores,products,suppliers,orders)
    monkeypatch.setattr(generator,'simulate_dc',checked)
    world=generator.generate(seed)
    assert captured['checked']
    assert len(world.events)==6
    assert (world.store_orders.shipped_units<=world.store_orders.ordered_units).all()

def test_apportion_exact_and_never_overdraws():
    for amount in range(9):
        result=apportion(np.array([1,2,5]),amount)
        assert result.sum()==amount
        assert (result<=np.array([1,2,5])).all()


def test_hidden_intersections_are_queryable_without_answer_key(sample,monkeypatch):
    from types import SimpleNamespace
    from scoop.ai import exploration_tools
    _,products,_,_=sample
    monkeypatch.setattr(exploration_tools.groups,'load_groups',lambda:[])
    # This price/format fixture has products but no nutrition rows.
    session=SimpleNamespace(scalars=lambda statement: list(products.itertuples())
                            if statement.column_descriptions[0]['entity'] is exploration_tools.Product else [])
    catalog=exploration_tools._groups(session)
    hidden=cells(products)
    for fmt in ('stick','cup'):
        members=set(products.loc[products['format']==fmt,'sku'])
        for suffix,band in [('low',1),('high',2)]:
            queried=members & set(catalog[f'band:price_100ml:{band}'].skus)
            assert queried==set(products.sku.iloc[hidden[f'{fmt}_{suffix}']])

def test_seed91_injected_before_fulfillment_and_inventory_balances(monkeypatch):
    captured={};original=generator.simulate_dc
    def checked(rng,days,stores,products,suppliers,orders):
        expected_rng=np.random.default_rng(91)
        st,_,pr,_,_,_,tags=generator.build_catalog(expected_rng)
        weather,_,_=generator.build_weather(expected_rng,days)
        baseline,_,_=generator.build_demand(expected_rng,days,st,pr,tags,weather)
        np.testing.assert_array_equal(orders.sum(axis=2),baseline.sum(axis=2))
        assert not np.array_equal(orders,baseline)
        captured['opening']=(orders[:28].sum(axis=1).mean(axis=0)*14).astype(np.int64)
        return original(rng,days,stores,products,suppliers,orders)
    monkeypatch.setattr(generator,'simulate_dc',checked)
    world=generator.generate(91)
    assert len(world.events)==8
    assert (world.store_orders.shipped_units<=world.store_orders.ordered_units).all()
    assert world.node_inventory.on_hand_units.min()>=0
    skus=list(world.products.sku)
    shipped=world.store_orders.groupby(['date','sku']).shipped_units.sum().unstack().reindex(columns=skus)
    inventory=world.node_inventory.pivot(index='date',columns='sku',values='on_hand_units').reindex(columns=skus)
    po=world.purchase_orders.dropna(subset=['received_date']).copy()
    po['units']=po.cases*po.sku.map(world.products.set_index('sku').units_per_case)
    arrivals=po.groupby(['received_date','sku']).units.sum().unstack().reindex(index=inventory.index,columns=skus,fill_value=0).fillna(0)
    opening=np.vstack([captured['opening'],inventory.to_numpy()[:-1]])
    np.testing.assert_array_equal(inventory.to_numpy(),opening+arrivals.to_numpy()-shipped.to_numpy())
