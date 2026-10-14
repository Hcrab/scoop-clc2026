"""Monitored product groups: tags, and tercile bands of graded / numeric attributes.

Bands are derived, never stored as tags: the cut points are tercile edges over the
catalog and are frozen for a taxonomy version so that a new product does not move them.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..db import read_sql

_CATEGORY = json.loads((Path(__file__).resolve().parents[1] / "category_config.json").read_text(encoding="utf-8"))
BANDED = {dimension: tuple(labels) for dimension, labels in _CATEGORY["band_labels"].items()}
TAG_DIMENSIONS = tuple(_CATEGORY["tag_dimensions"])
MIN_SKUS = 3


@dataclass(frozen=True)
class Group:
    id: str
    name: str
    dimension: str
    skus: tuple[str, ...]


def load_groups() -> list[Group]:
    tags = read_sql("SELECT pt.sku, pt.tag_id, pt.value_num, t.name, t.dimension_id FROM product_tags pt JOIN tags t ON t.id = pt.tag_id")
    groups: list[Group] = []
    for dim in TAG_DIMENSIONS:
        sub = tags[tags.dimension_id == dim]
        for tag_id, part in sub.groupby("tag_id"):
            if part.sku.nunique() >= MIN_SKUS:
                groups.append(Group(tag_id, part.name.iloc[0], dim, tuple(sorted(part.sku))))
    for dim, labels in BANDED.items():
        sub = tags[tags.tag_id == dim].set_index("sku").value_num
        edges = np.quantile(sub.to_numpy(), [1 / 3, 2 / 3])
        band = np.digitize(sub.to_numpy(), edges, right=True)
        for b, label in enumerate(labels):
            skus = tuple(sorted(sub.index[band == b]))
            if len(skus) >= MIN_SKUS:
                groups.append(Group(f"band:{dim}:{b}", label, dim, skus))
    return groups


def membership(groups: list[Group], skus: list[str]) -> pd.DataFrame:
    """SKU x group 0/1 matrix in the given SKU order."""
    m = pd.DataFrame(0.0, index=skus, columns=[g.id for g in groups])
    for g in groups:
        m.loc[list(g.skus), g.id] = 1.0
    return m
