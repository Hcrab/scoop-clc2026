"""Generic code-owned names and their unchanged passage into model context."""
from copy import deepcopy
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from scoop.ai import weekly
from scoop.ai.narrator import cohort_display
from scoop.algorithms.groups import Group
from scoop.cohort_cards import build_cards, build_observations


def groups_for(*items):
    return {identifier: Group(identifier, label, dimension, ('A',))
            for identifier, label, dimension in items}


@pytest.mark.parametrize('flavour', ['Strawberry', 'Fig', 'Guava'])
def test_price_flavour_base_is_composed_generically(flavour):
    groups = groups_for(('band:price_hkd:0', 'Low price', 'price_hkd'),
                        ('flavour:fruit', flavour, 'flavour'),
                        ('band:dairy:0', 'Water-based', 'dairy'))
    path = [{'id': identifier, 'included': True} for identifier in reversed(groups)]
    before = deepcopy(path)
    assert cohort_display(path, groups, ['North']) == f'Low-price {flavour.lower()} water ices'
    assert path == before


@pytest.mark.parametrize('format_name,noun', [('Stick', 'ice bars'), ('Cup', 'cups'),
                                            ('Sandwich', 'sandwiches'), ('Mochi', 'mochi')])
def test_explicit_format_is_the_noun(format_name, noun):
    groups = groups_for(('flavour:fruit', 'Guava', 'flavour'),
                        ('band:dairy:0', 'Water-based', 'dairy'),
                        ('format:serving', format_name, 'format'))
    path = [{'id': identifier, 'included': True} for identifier in groups]
    assert cohort_display(path, groups, []) == f'Guava water-based {noun}'


def test_exclusion_and_actual_district_qualifiers_are_preserved():
    groups = groups_for(('band:price_hkd:1', 'Mid price', 'price_hkd'),
                        ('flavour:fruit', 'Guava', 'flavour'),
                        ('format:cup', 'Cup', 'format'))
    path = [{'id': 'band:price_hkd:1', 'included': True},
            {'id': 'flavour:fruit', 'included': False},
            {'id': 'format:cup', 'included': True},
            {'id': 'district:North', 'included': False}]
    assert cohort_display(path, groups, ['South', 'East']) == 'Other mid-price cups · South, East'


def test_negative_only_and_district_only_scopes_have_readable_names():
    assert cohort_display([{'id': 'flavour:fruit', 'included': False}], {}, []) == 'Other products'
    assert cohort_display([{'id': 'district:North', 'included': True}], {}, ['North']) == 'Products · North'
    assert cohort_display([], {}, ['North', 'South']) == 'All products'


@pytest.mark.parametrize('label,expected', [('Mixed', 'Mixed-dairy ice creams'),
                                           ('Creamy', 'Creamy ice creams')])
def test_other_dairy_bases_are_generic(label, expected):
    groups = groups_for(('band:dairy:1', label, 'dairy'))
    assert cohort_display([{'id': 'band:dairy:1', 'included': True}], groups, []) == expected


def test_cards_and_observations_share_canonical_name_without_changing_inputs():
    groups = groups_for(('band:price_hkd:2', 'High price', 'price_hkd'),
                        ('flavour:fruit', 'Guava', 'flavour'),
                        ('format:cup', 'Cup', 'format'))
    leaf = {'id': 'leaf', 'tag_path': [{'id': key, 'included': True} for key in groups],
            'districts': ['North'], 'skus': ['A'], 'split_p_values': [.01],
            'posterior_mean': .2, 'interval_80': [.1, .3]}
    result = {'leaves': [leaf], 'units': [{'sku': 'A', 'leaf_id': 'leaf', 'expected_recent': 1}],
              'sku_factors': {'A': {}}, 'method': {}}
    before = deepcopy(result)
    row = {'sku': 'A', 'demand_p10': 8, 'demand_p50': 10, 'demand_p90': 12,
           'inventory_position': 0, 'projected_pallets': 1}
    orders = pd.DataFrame([{**row, 'final_cases': 8}])
    baseline = pd.DataFrame([{**row, 'final_cases': 5}])
    products = pd.DataFrame([{'sku': 'A', 'units_per_case': 10, 'cases_per_pallet': 10,
                              'price_hkd': 10, 'cost_hkd': 5}])
    cards = build_cards(result, orders, baseline, products, groups, {'A': 'A'})
    observations = build_observations(result, cards, groups)
    assert cards[0]['name'] == cards[0]['display_name'] == 'High-price guava cups'
    assert observations[0]['display_name'] == observations[0]['name'] == cards[0]['display_name']
    assert cards[0]['case_change'] == 3
    assert result == before


def test_uncropped_names_survive_initial_and_saved_authoring_context(monkeypatch):
    from scoop.api import service
    from scoop import dashboard
    title = 'High-price ' + 'unusual catalog flavour ' * 20 + 'cups'
    cards = [{'id': f'leaf-{i}', 'name': title + str(i), 'display_name': title + str(i),
              'effect_pct': 12, 'method': {}, 'skus': ['A']} for i in range(15)]
    observations = [dict(card, in_card=False, daily=[]) for card in cards]
    plan = SimpleNamespace(week_start=date(2026, 6, 1), goal='balanced', stage='discover',
                           id='naming-test', summary={'cohort_cards': cards,
                                                      'cohort_observations': observations})
    monkeypatch.setattr(dashboard, 'options', lambda *args: [])
    monkeypatch.setattr(service, 'cohort_observations', lambda *args: pytest.fail('Saved observations should be used'))
    context = weekly._context(SimpleNamespace(scalars=lambda query: []), plan)
    assert [q['result']['display_name'] for q in context['cohort_cards']] == [c['display_name'] for c in cards]
    assert [o['display_name'] for o in context['all_observations']] == [o['display_name'] for o in observations]
    assert weekly.program_evidence(plan)[-1]['result'] == cards[-1]
    assert weekly.authoring_evidence(cards[-1])['display_name'] == cards[-1]['display_name']


def test_prompt_uses_placeholder_and_supplied_names():
    assert '"{cohort display name} · stock"' in weekly.SYSTEM
    assert 'display_name verbatim' in weekly.SYSTEM
    assert 'strawberry' not in weekly.SYSTEM.lower()
    assert 'mango' not in weekly.SYSTEM.lower()
