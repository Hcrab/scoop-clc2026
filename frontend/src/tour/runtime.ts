import type { Detail, FlowState, FlowStep, Stage } from '../types';
import type { Branch, ContextId, QuestionId, RecordedAnswer, Snapshot, TourBundle, TourSource, WidgetId } from './types';

const steps: FlowStep[] = ['report', 'orders', 'watch', 'play', 'results'];
const contexts: ContextId[] = ['summer', 'growing', 'unchanged'];
const widgets: WidgetId[] = ['stock', 'space', 'cover'];
const clone = <T,>(value: T): T => structuredClone(value);
type Session = { bundle: TourBundle; branch: ContextId; chosenContext: boolean; widget: WidgetId | null; stage: Stage; step: FlowStep; maximum: FlowStep };
let session: Session | null = null;
function current(): Session { if (!session) throw new Error('The tour is not active.'); return session; }
function refresh() { if (typeof window !== 'undefined') window.dispatchEvent(new Event('scoop:tour-refresh')); }
function snapshot(s = current()): Snapshot { return s.chosenContext ? s.bundle.branches[s.branch].snapshot : s.bundle.base; }
function flow(s = current()): FlowState { return { step: s.step, max_step: s.maximum, order_hash: snapshot(s).simulation.order_hash ?? snapshot(s).detail.flow?.order_hash ?? null, notice: null }; }
function detail(s = current()): Detail {
  const result = clone(snapshot(s).detail);
  result.plan.stage = s.stage;
  result.flow = flow(s);
  if (result.plan.summary && typeof result.plan.summary === 'object') result.plan.summary = { ...result.plan.summary, flow: result.flow };
  if (s.stage === 'execute') result.orders.forEach(order => { order.status = 'confirmed'; });
  return result;
}
function same(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object') return false;
  const ak = Object.keys(a), bk = Object.keys(b);
  return ak.length === bk.length && ak.every(key => Object.prototype.hasOwnProperty.call(b, key) && same((a as Record<string, unknown>)[key], (b as Record<string, unknown>)[key]));
}
async function readJSON<T>(path: string): Promise<T> {
  const response = await fetch(path, { method: 'GET' });
  if (!response.ok) throw new Error(`Could not load tour data (${response.status}).`);
  return response.json();
}
export async function loadTourBundle(): Promise<TourBundle> {
  const [bundle, source] = await Promise.all([readJSON<TourBundle>('/tour-bundle.json'), readJSON<TourSource>('/api/tour/source')]);
  if (bundle.version !== 1 || !bundle.default_order_hash || bundle.default_order_hash !== source.default_order_hash || bundle.default_week !== source.default_week || bundle.plan_id !== source.plan_id) throw new Error('The tour bundle is stale. Rebuild it for the current default week.');
  return bundle;
}
export function beginTour(bundle: TourBundle): void {
  session = { bundle: clone(bundle), branch: 'unchanged', chosenContext: false, widget: null, stage: 'discover', step: 'report', maximum: 'report' };
  refresh();
}
export function endTour(): void { session = null; refresh(); }
export function isTourActive(): boolean { return session !== null; }
export function getTourBundle(): TourBundle | null { return session ? clone(session.bundle) : null; }
export function getTourBranch(): Branch | null { return session ? clone(session.bundle.branches[session.branch]) : null; }
export function selectContext(id: ContextId): Branch {
  const s = current();
  if (!contexts.includes(id)) throw new Error('Unknown tour context.');
  if (s.stage !== 'discover' || s.step !== 'report') throw new Error('Choose context in Report.');
  s.branch = id; s.chosenContext = true; s.widget = null;
  refresh(); return clone(s.bundle.branches[id]);
}
export function selectWidget(id: WidgetId): void {
  const s = current();
  if (!widgets.includes(id)) throw new Error('Unknown tour widget.');
  if (s.step !== 'watch') throw new Error('Choose a widget in Watch.');
  s.widget = id; refresh();
}
export function setTourView(step: FlowStep): void {
  const s = current();
  if (!steps.includes(step)) throw new Error('Unknown tour view.');
  const maximum = step === 'play' && s.maximum === 'watch' ? 'play' : s.maximum;
  if (steps.indexOf(step) > steps.indexOf(maximum)) throw new Error('Complete the preceding step first.');
  s.step = step; s.maximum = maximum; refresh();
}
function recorded(answer: RecordedAnswer | null): RecordedAnswer {
  if (!answer?.reply || answer.grounding?.passed !== true || !answer.snapshot_hash || !answer.provider || !answer.model) throw new Error('This recorded tour answer is unavailable.');
  return clone(answer);
}
export function getRecordedQuestion(id: QuestionId): RecordedAnswer {
  if (id !== 'why' && id !== 'heat') throw new Error('Unknown tour question.');
  return recorded(current().bundle.questions[id]);
}
export async function tourRequest<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const s = current(), verb = method.toUpperCase(), snap = snapshot(s);
  let result: unknown;
  if (verb === 'GET' && path === '/bootstrap') {
    const boot = clone(s.bundle.common.bootstrap);
    boot.plans = boot.plans.filter(plan => plan.id === s.bundle.plan_id).map(() => detail(s).plan);
    result = boot;
  } else if (verb === 'GET' && path === '/demo-settings') result = s.bundle.common.settings;
  else {
    const prefix = `/plans/${encodeURIComponent(s.bundle.plan_id)}`;
    if (path !== prefix && !path.startsWith(`${prefix}/`)) throw new Error(`Unsupported tour request: ${verb} ${path}`);
    const route = path.slice(prefix.length);
    if (verb === 'GET') {
      switch (route) {
        case '': result = detail(s); break;
        case '/cohorts': result = snap.cohorts; break;
        case '/overrides': result = snap.cohorts.overrides; break;
        case '/dashboard': result = s.widget ? s.bundle.branches[s.branch].widgets[s.widget].dashboard : snap.dashboard; break;
        case '/order-summary': result = snap.order_summary; break;
        case '/simulation': result = snap.simulation; break;
        default: throw new Error(`Unsupported tour request: ${verb} ${path}`);
      }
    } else if (verb === 'POST' && route === '/direction-preview' && same(body, { service_level: null })) result = snap.direction_preview;
    else if (verb === 'POST' && route === '/advance') {
      if (s.stage !== 'discover') throw new Error('Review and approve the order list to start execution.');
      s.stage = 'direction'; s.step = s.maximum = 'orders'; result = { stage: s.stage }; refresh();
    } else if (verb === 'POST' && route === '/approve-orders') {
      if (s.stage === 'discover') throw new Error('Review orders first.');
      s.stage = 'execute'; s.step = s.maximum = 'watch'; result = { stage: s.stage, capacity: snap.order_summary.capacity }; refresh();
    } else if (verb === 'PUT' && route === '/flow') {
      setTourView((body as { step: FlowStep })?.step); result = flow(s);
    } else if (verb === 'POST' && route === '/play-complete') {
      if (s.step !== 'play') throw new Error('Enter Play first.');
      if (snap.simulation.status !== 'ready' || !snap.simulation.result) throw new Error('Replay is still preparing.');
      s.maximum = 'results'; result = flow(s); refresh();
    } else if (verb === 'POST' && route === '/overrides') {
      const id = contexts.find(id => s.bundle.branches[id].context !== null && same(body, s.bundle.branches[id].context));
      if (!id) throw new Error('This context is not available in the tour.');
      result = selectContext(id).edit;
    } else if (verb === 'POST' && route === '/dashboard') {
      const id = widgets.find(id => same(body, s.bundle.branches[s.branch].widgets[id].spec));
      if (!id) throw new Error('This widget is not available in the tour.');
      selectWidget(id); result = s.bundle.branches[s.branch].widgets[id].edit;
    } else throw new Error(`Unsupported tour request: ${verb} ${path}`);
  }
  return clone(result) as T;
}
export async function tourAssistant<T>(path: string, body: unknown, _onProgress: (event: { phase: string; label: string; tool?: string }) => void): Promise<T> {
  const s = current();
  if (path !== `/plans/${encodeURIComponent(s.bundle.plan_id)}/chat`) throw new Error('Unsupported tour assistant request.');
  const message = (body as { message?: string })?.message;
  if (message === 'Why strawberry, and why now?') return getRecordedQuestion('why') as T;
  if (message === 'Could this just be the heat?') return getRecordedQuestion('heat') as T;
  throw new Error('Choose a recorded tour question.');
}
