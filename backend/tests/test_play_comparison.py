"""The two ordinary policies share one physical receiving constraint."""

import pandas as pd
import pytest

from scoop import play


def test_equal_proportions_are_rounded_by_sku_order():
    due = pd.Series({'B': 5., 'A': 5.})
    upp = pd.Series({'B': 10., 'A': 10.})
    stock = pd.Series({'B': 0., 'A': 0.})
    admitted = play._admit_receipts(stock, due, upp, .5)
    assert admitted.to_dict() == {'B': 2., 'A': 3.}
    assert (admitted / upp).sum() == pytest.approx(.5)
    assert (due - admitted).sum() == 5


def test_larger_unit_uses_only_free_space_it_can_fit():
    due = pd.Series({'A': 3., 'B': 3.})
    upp = pd.Series({'A': 2., 'B': 10.})
    admitted = play._admit_receipts(pd.Series({'A': 0., 'B': 0.}), due, upp, .3)
    assert (admitted / upp).sum() <= .3 + 1e-9
    assert admitted['A'] == 0
    assert admitted['B'] == 3


def test_impossible_opening_is_not_erased():
    with pytest.raises(ValueError, match='exceeds physical capacity'):
        play._admit_receipts(pd.Series({'A': 11.}), pd.Series({'A': 1.}),
                             pd.Series({'A': 10.}), 1.)
