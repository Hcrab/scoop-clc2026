"""Relational schema for the warehouse (cold store) version of Scoop.

Four layers:
1. facts      - imported operational data, append-only (orders, inventory, weather)
2. derived    - algorithm outputs, reproducible per run (forecasts, findings)
3. decisions  - what the planner chose, with source and time
4. views      - what the AI may read (see ``api/readonly.py``)
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------- master data


class Store(Base):
    __tablename__ = "stores"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    district: Mapped[str] = mapped_column(String(40))  # also the CUSUM store cluster
    format: Mapped[str] = mapped_column(String(20))  # superstore / standard / compact
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    size_factor: Mapped[float] = mapped_column(Float)


class Node(Base):
    """A capacity-limited storage node. The prototype has one DC cold store."""

    __tablename__ = "nodes"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20))  # dc_cold_store / store_freezer
    capacity_pallets: Mapped[int] = mapped_column(Integer)


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    lead_time_days: Mapped[int] = mapped_column(Integer)
    lead_time_sd: Mapped[float] = mapped_column(Float)
    order_weekday: Mapped[int] = mapped_column(Integer)  # 0 = Monday
    review_days: Mapped[int] = mapped_column(Integer)  # R in the order-up-to policy


class Product(Base):
    __tablename__ = "products"
    sku: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    brand: Mapped[str] = mapped_column(String(40))
    format: Mapped[str] = mapped_column(String(20))
    size_ml: Mapped[int] = mapped_column(Integer)
    units_per_case: Mapped[int] = mapped_column(Integer)
    cases_per_pallet: Mapped[int] = mapped_column(Integer)
    price_hkd: Mapped[float] = mapped_column(Float)
    cost_hkd: Mapped[float] = mapped_column(Float)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"))
    moq_cases: Mapped[int] = mapped_column(Integer)
    launch_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / new / delisting
    description: Mapped[str] = mapped_column(Text)


class ProductNutrition(Base):
    __tablename__ = "product_nutrition"
    sku: Mapped[str] = mapped_column(ForeignKey("products.sku"), primary_key=True)
    serving_ml: Mapped[float] = mapped_column(Float)
    kcal: Mapped[float] = mapped_column(Float)
    sugar_g: Mapped[float] = mapped_column(Float)
    fat_g: Mapped[float] = mapped_column(Float)
    protein_g: Mapped[float] = mapped_column(Float)


# --------------------------------------------------------------------------- tags (C1)


class TagDimension(Base):
    __tablename__ = "tag_dimensions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(10))  # graded / single / multi / numeric
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    definition: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10))  # llm / computed


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    dimension_id: Mapped[str] = mapped_column(ForeignKey("tag_dimensions.id"))
    name: Mapped[str] = mapped_column(String(60))
    definition: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="active")  # active / proposed / rejected
    taxonomy_version: Mapped[int] = mapped_column(Integer, default=1)


class ProductTag(Base):
    __tablename__ = "product_tags"
    sku: Mapped[str] = mapped_column(ForeignKey("products.sku"), primary_key=True)
    tag_id: Mapped[str] = mapped_column(ForeignKey("tags.id"), primary_key=True)
    value_num: Mapped[float] = mapped_column(Float)  # 0-1 for graded, 1 for membership, raw for numeric
    source: Mapped[str] = mapped_column(String(10))  # llm / human / computed
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)


# --------------------------------------------------------------------------- facts


class WeatherDaily(Base):
    __tablename__ = "weather_daily"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    tmax: Mapped[float] = mapped_column(Float)
    rain_mm: Mapped[float] = mapped_column(Float)


class WeatherForecast(Base):
    __tablename__ = "weather_forecasts"
    issued_date: Mapped[date] = mapped_column(Date, primary_key=True)
    target_date: Mapped[date] = mapped_column(Date, primary_key=True)
    tmax_fc: Mapped[float] = mapped_column(Float)
    rain_fc: Mapped[float] = mapped_column(Float)


class Promotion(Base):
    __tablename__ = "promotions"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    sku: Mapped[str] = mapped_column(ForeignKey("products.sku"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    discount_pct: Mapped[float] = mapped_column(Float)
    note: Mapped[str] = mapped_column(String(120))


class StoreOrder(Base):
    __tablename__ = "store_orders"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    store_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    sku: Mapped[str] = mapped_column(String(16), primary_key=True)
    ordered_units: Mapped[int] = mapped_column(Integer)
    shipped_units: Mapped[int] = mapped_column(Integer)


class NodeInventory(Base):
    __tablename__ = "node_inventory"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    sku: Mapped[str] = mapped_column(String(16), primary_key=True)
    on_hand_units: Mapped[int] = mapped_column(Integer)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    sku: Mapped[str] = mapped_column(ForeignKey("products.sku"))
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"))
    order_date: Mapped[date] = mapped_column(Date)
    expected_date: Mapped[date] = mapped_column(Date)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    cases: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16))  # history / scoop


class GroundTruthEvent(Base):
    """Events planted in the synthetic data. Used only for evaluation, never by the planner."""

    __tablename__ = "ground_truth_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # trend / weak_trend / promo / bulk_order / heatwave
    tag_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(16), nullable=True)
    districts: Mapped[list] = mapped_column(JSON)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_label: Mapped[str] = mapped_column(String(20))  # persistent / one_off / data_issue / weather
    note: Mapped[str] = mapped_column(Text)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


# --------------------------------------------------------------------------- derived (algorithms)


class ModelRun(Base):
    __tablename__ = "model_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    trained_through: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    params: Mapped[dict] = mapped_column(JSON)
    metrics: Mapped[dict] = mapped_column(JSON)


class DailyExpectation(Base):
    """Model expectation per store x SKU x day (p50, plus p10/p90)."""

    __tablename__ = "daily_expectations"
    run_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    store_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    sku: Mapped[str] = mapped_column(String(16), primary_key=True)
    p10: Mapped[float] = mapped_column(Float)
    p50: Mapped[float] = mapped_column(Float)
    p90: Mapped[float] = mapped_column(Float)


class CusumSeries(Base):
    """Daily monitored statistic per tag x district."""

    __tablename__ = "cusum_series"
    run_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tag_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    district: Mapped[str] = mapped_column(String(40), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    actual_share: Mapped[float] = mapped_column(Float)
    expected_share: Mapped[float] = mapped_column(Float)
    z: Mapped[float] = mapped_column(Float)
    s_up: Mapped[float] = mapped_column(Float)
    s_down: Mapped[float] = mapped_column(Float)


# --------------------------------------------------------------------------- plans and decisions


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    week_start: Mapped[date] = mapped_column(Date, unique=True)
    stage: Mapped[str] = mapped_column(String(16))  # discover / direction / execute / closed
    goal: Mapped[str] = mapped_column(String(16), default="margin")  # margin / fill_rate / sales
    service_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"))
    kind: Mapped[str] = mapped_column(String(12))  # significant / weak
    tag_id: Mapped[str] = mapped_column(String(48))
    district: Mapped[str] = mapped_column(String(40))
    direction: Mapped[str] = mapped_column(String(6))  # up / down
    alarm_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    statistic: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    p_value: Mapped[float] = mapped_column(Float)
    q_value: Mapped[float] = mapped_column(Float)
    share_before: Mapped[float] = mapped_column(Float)
    share_now: Mapped[float] = mapped_column(Float)
    effect_volume: Mapped[float] = mapped_column(Float)
    effect_mix: Mapped[float] = mapped_column(Float)
    effect_interaction: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(12))  # scan / ai_review
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification: Mapped[str | None] = mapped_column(String(20), nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


class Hypothesis(Base):
    __tablename__ = "hypotheses"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id"))
    cause: Mapped[str] = mapped_column(String(24))
    label: Mapped[str] = mapped_column(String(20))  # persistent / one_off / data_issue / weather / unsure
    text: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"))
    stage: Mapped[str] = mapped_column(String(16))
    finding_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON)
    answer: Mapped[str | None] = mapped_column(String(40), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"))
    stage: Mapped[str] = mapped_column(String(16))
    key: Mapped[str] = mapped_column(String(60))
    value: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(16))  # question / chat / ui / system
    created_at: Mapped[datetime] = mapped_column(DateTime)


class DirectionItem(Base):
    __tablename__ = "direction_items"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"))
    bucket: Mapped[str] = mapped_column(String(10))  # more / less / clear / hold
    tag_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(16), nullable=True)
    districts: Mapped[list] = mapped_column(JSON, default=list)
    factor: Mapped[float] = mapped_column(Float, default=1.0)
    finding_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")


class PurchaseSuggestion(Base):
    __tablename__ = "purchase_suggestions"
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"), primary_key=True)
    sku: Mapped[str] = mapped_column(String(16), primary_key=True)
    order_date: Mapped[date] = mapped_column(Date)
    protection_days: Mapped[int] = mapped_column(Integer)
    demand_p10: Mapped[float] = mapped_column(Float)
    demand_p50: Mapped[float] = mapped_column(Float)
    demand_p90: Mapped[float] = mapped_column(Float)
    adjustment: Mapped[float] = mapped_column(Float)
    critical_ratio: Mapped[float] = mapped_column(Float)
    target_units: Mapped[float] = mapped_column(Float)
    on_hand_units: Mapped[int] = mapped_column(Integer)
    on_order_units: Mapped[int] = mapped_column(Integer)
    inventory_position: Mapped[int] = mapped_column(Integer)
    suggested_cases: Mapped[int] = mapped_column(Integer)
    capacity_cut_cases: Mapped[int] = mapped_column(Integer, default=0)
    final_cases: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="suggested")  # suggested / confirmed
    reason: Mapped[str] = mapped_column(Text)


class WatchItem(Base):
    __tablename__ = "watch_items"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"))
    kind: Mapped[str] = mapped_column(String(20))  # tag_share / days_cover / fill_rate / capacity / po_delay
    title: Mapped[str] = mapped_column(String(160))
    assumption: Mapped[str] = mapped_column(Text)
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    origin: Mapped[str] = mapped_column(String(12))  # baseline / decision / chat
    status: Mapped[str] = mapped_column(String(12), default="active")
    __table_args__ = (UniqueConstraint("plan_id", "title"),)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"))
    stage: Mapped[str] = mapped_column(String(16))
    role: Mapped[str] = mapped_column(String(10))  # user / assistant
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime)
