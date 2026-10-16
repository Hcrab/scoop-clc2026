import type { Bootstrap, CohortCard, CohortObservation, DashboardData, DashboardSpec, DemoSettings, Detail, DirectionPreview, SimulationStatus } from '../types';
import type { PlanEdit } from '../EditReceipt';

export type ContextId = 'summer' | 'growing' | 'unchanged';
export type WidgetId = 'stock' | 'space' | 'cover';
export type QuestionId = 'why' | 'heat';
export type RecordedAnswer = {
  reply: string; provider: string; model: string; usage: Record<string, unknown>;
  tool_trace: unknown[]; grounding: { passed: true; claims: unknown[]; evidence: Record<string, unknown> };
  snapshot_hash: string;
};
export type ContextRequest = { cohort: string; type: string; value: unknown; note?: string };
export type TourOverride = { id: number | string; type: string; value: unknown; [key: string]: unknown };
export type CohortsResponse = { cards: CohortCard[]; observations?: CohortObservation[]; method: unknown; overrides: TourOverride[] };
export type OrderSummary = { groups: { id: string; name: string; skus: string[] }[]; capacity: Record<string, unknown>; edited_skus: string[] };
export type Snapshot = {
  detail: Detail; cohorts: CohortsResponse; direction_preview: DirectionPreview;
  order_summary: OrderSummary; dashboard: DashboardData; simulation: SimulationStatus;
};
export type WidgetChoice = { spec: DashboardSpec; dashboard: DashboardData; edit: PlanEdit };
export type Branch = {
  id: ContextId; context: ContextRequest | null; snapshot: Snapshot; edit: PlanEdit | null;
  before_cases: number; after_cases: number; total_cases: number; peak: number; capacity: number;
  answer: RecordedAnswer | null;
  moments: { heat_date: string; strawberry_arrival: { date: string; time: string; minute: number; units: number } | null; stockout: { date: string; time: string; minute: number; product: string } | null };
  widgets: Record<WidgetId, WidgetChoice>;
};
export type TourSource = { default_week: string; default_order_hash: string; plan_id: string };
export type TourBundle = TourSource & {
  version: 1;
  meta: { capacity: number; product_count: number; strawberry_card_id: string; strawberry_skus: string[]; effect: number; l1: number; l2: number; l3: number; heat_date: string };
  common: { bootstrap: Bootstrap; settings: DemoSettings };
  base: Snapshot; branches: Record<ContextId, Branch>;
  questions: Record<QuestionId, RecordedAnswer | null>;
};
