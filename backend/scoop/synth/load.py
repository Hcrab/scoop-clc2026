"""Create the schema and load a freshly generated synthetic world."""

from __future__ import annotations

import json
import time

from ..db import copy_frame, engine, set_setting
from ..models import Base
from .generate import generate
from ..demo_config import DEMO_SEED, DEMO_WEEK, DEMO_SCENARIO

DEMO_TODAY = DEMO_WEEK


def load(seed: int = DEMO_SEED) -> None:
    t0 = time.time()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    world = generate(seed)
    print(f"generated world in {time.time() - t0:.1f}s; {len(world.store_orders):,} store-order rows")

    events = world.events.copy()
    events["districts"] = events["districts"].apply(json.dumps)
    order = [
        ("stores", world.stores),
        ("nodes", world.nodes),
        ("suppliers", world.suppliers),
        ("products", world.products),
        ("product_nutrition", world.nutrition),
        ("tag_dimensions", world.tag_dimensions),
        ("tags", world.tags),
        ("product_tags", world.product_tags),
        ("weather_daily", world.weather),
        ("weather_forecasts", world.forecasts),
        ("promotions", world.promotions),
        ("store_orders", world.store_orders),
        ("node_inventory", world.node_inventory),
        ("purchase_orders", world.purchase_orders),
        ("ground_truth_events", events),
    ]
    for table, frame in order:
        copy_frame(frame, table)
    set_setting("today", DEMO_TODAY)
    set_setting("seed", str(seed))
    if seed == DEMO_SEED:
        set_setting("demo_scenario", DEMO_SCENARIO)
    print(f"loaded in {time.time() - t0:.1f}s; cold store capacity {int(world.nodes.capacity_pallets[0])} pallets")


if __name__ == "__main__":
    load()
