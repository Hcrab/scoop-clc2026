"""Planner context changes fresh posteriors without mutating the fit."""
from copy import deepcopy
from datetime import date
from math import exp, log1p

import pandas as pd
import pytest

from scoop.algorithms.cohort_overrides import apply_overrides
from scoop.algorithms.groups import Group


GROUPS = {"fruit": Group("fruit", "Fruit", "kind", ("A", "B"))}
PRODUCTS = pd.DataFrame([
    {"sku": sku, "order_weekday": 0, "lead_time_days": 2, "review_days": 7}
    for sku in ("A", "B")])


def fitted():
    units = [{"sku": sku, "district": district, "m": .4, "s2": .05,
              "conditional_variance": .01, "leaf_weight": .5,
              "leaf_id": "leaf", "expected_recent": 100}
             for sku in ("A", "B") for district in ("north", "south")]
    return {"units": units, "leaves": [{"id": "leaf", "posterior_mean": .4,
             "posterior_variance": .04, "interval_80": [.14, .66]}],
            "sku_factors": {sku: {"f10": 1.1, "f50": exp(.4), "f90": 1.9,
                                  "m": .4, "s2": .045} for sku in ("A", "B")},
            "method": {}}


def rule(kind, value=None, **extra):
    return {"id": kind, "type": kind, "value": value,
            "tag_path": [{"id": "fruit", "included": True}],
            "districts": [], **extra}


def apply(rules):
    return apply_overrides(fitted(), rules, PRODUCTS, date(2026, 7, 27), GROUPS)


def test_one_off_and_expired_cover_are_exactly_one_and_input_is_immutable():
    original = fitted()
    saved = deepcopy(original)
    one_off = apply_overrides(original, [rule("one_off")], PRODUCTS, date(2026, 7, 27), GROUPS)
    expired = apply_overrides(original, [rule("ends_on", "2026-07-29")], PRODUCTS,
                              date(2026, 7, 27), GROUPS)
    assert original == saved
    for result in (one_off, expired):
        assert all(f == {"f10": 1., "f50": 1., "f90": 1., "m": 0., "s2": 0.}
                   for f in result["sku_factors"].values())


def test_partial_cover_tracks_supplier_order_and_fraction():
    result = apply([rule("ends_on", "2026-08-02")])
    cover = result["applied_overrides"][0]["cover"]["A"]
    assert cover == {"order_date": "2026-07-27", "cover_start": "2026-07-29",
                     "cover_end_exclusive": "2026-08-05", "ends_on": "2026-08-02",
                     "fraction": 4 / 7}
    assert result["sku_factors"]["A"]["f50"] == pytest.approx(1 + (exp(.4) - 1) * 4 / 7)


def test_cap_truncates_posterior_and_limits_upper_factor():
    result = apply([rule("cap", .2)])
    factor = result["sku_factors"]["A"]
    assert 0 < factor["m"] < log1p(.2)
    assert 0 < factor["s2"] < .05
    assert factor["f90"] <= 1.2


def test_expect_strength_and_overlap_produce_single_factor():
    levels = [apply([rule("expect", {"pct": -.1, "strength": strength})])
              ["sku_factors"]["A"]["f50"] for strength in ("low", "medium", "high")]
    assert levels[0] > levels[1] > levels[2]
    overlap = apply([rule("expect", {"pct": .1, "strength": "low"}),
                     rule("ends_on", "2026-08-02")])
    assert len(overlap["sku_factors"]) == 2
    assert overlap["sku_factors"]["A"]["f50"] < exp(.4)
    assert len(overlap["applied_overrides"]) == 2


def test_cases_only_changes_final_case_map():
    result = apply([rule("cases", {"sku": "A", "cases": 12})])
    assert result["cases_overrides"] == {"A": 12}
    assert result["sku_factors"]["A"]["f50"] == pytest.approx(exp(.4))


def test_saved_definition_matches_fresh_units_without_leaf_id():
    original = fitted()
    original["units"][0]["leaf_id"] = "new"
    original["leaves"].append({"id": "new", "posterior_mean": .4, "posterior_variance": .04,
                               "interval_80": [.14, .66]})
    result = apply_overrides(original, [rule("one_off", districts=["north"])],
                             PRODUCTS, date(2026, 7, 27), GROUPS)
    assert result["units"][0]["m"] == 0
    assert result["units"][1]["m"] == .4


def test_district_split_path_matches_units():
    result = apply([rule('one_off', tag_path=[{'id':'district:north','included':True}])])
    assert all(u['m'] == (0. if u['district'] == 'north' else .4) for u in result['units'])
