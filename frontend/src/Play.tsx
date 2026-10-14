import { useEffect, useMemo, useRef, useState, type DragEvent } from 'react';
import { api, n, pct, date, fullDate } from './api';
import { Chart, Icon, Modal } from './ui';
import { displayName } from './PlanSections';
import type { Detail, Product } from './types';

type Policy = 'scoop' | 'baseline';
type DayRow = { date: string; demand: number; shipped: number; lost: number; lost_margin: number; on_hand: number; pallets_pre_ship: number; pallets: number; arrived_units: number; ordered_cases: number; skus_short: number };
type Run = { daily: DayRow[]; per_sku: { on_hand: number[][]; shipped: number[][]; lost: number[][]; arrived: number[][] } };
type PlayEvent = { date: string; kind: string; tone: 'good' | 'bad' | 'warn' | 'neutral'; text: string };
type Summary = { fill_rate: number; lost_units: number; lost_margin: number; avg_pallets: number; peak_pallets: number; days_over_capacity: number; stockout_sku_days: number; ending_on_hand: number; ordered_cases: number };
type PlayResult = { start: string; end: string; days: number; capacity_pallets: number; skus: string[]; dates: string[]; demand: number[][]; runs: Record<Policy, Run>; events: PlayEvent[]; summary: Record<Policy, Summary>; notes: Record<string, string | null> };

type Scope = { kind: 'all' | 'tag' | 'brand' | 'sku'; key: string; label: string };
type Measure = 'fill_rate' | 'lost' | 'on_hand' | 'pallets' | 'demand' | 'cover';
type Widget = { id: string; title: string; measure: Measure; scope: Scope; chart: boolean };

const ALL: Scope = { kind: 'all', key: '', label: 'All products' };
const MEASURES: { id: Measure; label: string }[] = [
  { id: 'on_hand', label: 'Stock on hand' },
  { id: 'lost', label: 'Units short' },
  { id: 'demand', label: 'Store orders' },
  { id: 'fill_rate', label: 'Fill rate' },
  { id: 'cover', label: 'Days of cover' },
];
const SPEEDS = [{ label: '1×', ms: 1400 }, { label: '2×', ms: 700 }, { label: '4×', ms: 350 }];
const POLICY_LABEL: Record<Policy, string> = { scoop: 'This plan', baseline: 'Moving-average rule' };

function standardWidgets(): Widget[] {
  return [
    { id: 'fill', title: 'Fill rate to stores', measure: 'fill_rate', scope: ALL, chart: false },
    { id: 'short', title: 'Units short', measure: 'lost', scope: ALL, chart: false },
    { id: 'pallets', title: 'Cold store pallets', measure: 'pallets', scope: ALL, chart: true },
    { id: 'stock', title: 'Stock on hand', measure: 'on_hand', scope: ALL, chart: true },
    { id: 'orders', title: 'Store orders per day', measure: 'demand', scope: ALL, chart: true },
    { id: 'cover', title: 'Days of cover', measure: 'cover', scope: ALL, chart: false },
  ];
}

function scopeSkus(scope: Scope, products: Product[]): Set<string> {
  if (scope.kind === 'all') return new Set(products.map(p => p.sku));
  if (scope.kind === 'brand') return new Set(products.filter(p => p.brand === scope.key).map(p => p.sku));
  if (scope.kind === 'sku') return new Set([scope.key]);
  return new Set(products.filter(p => p.tags.some(t => t.id === scope.key)).map(p => p.sku));
}

function suggestedWidgets(detail: Detail, products: Product[]): Widget[] {
  const tags = new Map(products.flatMap(p => p.tags).map(t => [t.id, t.name]));
  const keys = new Set<string>();
  const out: Widget[] = [];
  const add = (key: string, label: string) => {
    if (!key || keys.has(key) || !tags.has(key)) return;
    keys.add(key);
    out.push({ id: `tag-${key}`, title: `${label}: stock`, measure: 'on_hand', scope: { kind: 'tag', key, label }, chart: true });
  };
  for (const w of detail.watch) {
    const s = (w.scope || {}) as Record<string, unknown>;
    const key = String(s.tag_id || s.group || '');
    if (key) add(key, displayName(tags.get(key) || key));
  }
  for (const f of detail.findings) add(f.tag_id, typeof f.evidence.display === 'string' ? f.evidence.display : displayName(tags.get(f.tag_id) || f.tag_id));
  return out;
}

function series(result: PlayResult, policy: Policy, w: Widget, products: Product[]): number[] {
  const run = result.runs[policy];
  if (w.measure === 'pallets') return run.daily.map(d => d.pallets_pre_ship);
  const skus = scopeSkus(w.scope, products);
  const idx = result.skus.map((s, i) => (skus.has(s) ? i : -1)).filter(i => i >= 0);
  const sum = (rows: number[][]) => rows.map(r => idx.reduce((a, i) => a + r[i], 0));
  const demand = sum(result.demand), shipped = sum(run.per_sku.shipped), lost = sum(run.per_sku.lost), stock = sum(run.per_sku.on_hand);
  if (w.measure === 'demand') return demand;
  if (w.measure === 'lost') return lost;
  if (w.measure === 'on_hand') return stock;
  if (w.measure === 'fill_rate') return demand.map((_, i) => { const d = demand.slice(0, i + 1).reduce((a, b) => a + b, 0); return d ? shipped.slice(0, i + 1).reduce((a, b) => a + b, 0) / d : 1; });
  return stock.map((s, i) => { const recent = demand.slice(Math.max(0, i - 6), i + 1); const avg = recent.reduce((a, b) => a + b, 0) / recent.length; return avg ? s / avg : 0; });
}

function headline(result: PlayResult, w: Widget, day: number, products: Product[]): string {
  const v = series(result, 'scoop', w, products);
  if (w.measure === 'lost') return n(v.slice(0, day + 1).reduce((a, b) => a + b, 0));
  if (w.measure === 'fill_rate') return pct(v[day]);
  if (w.measure === 'pallets') return `${n(v[day], 1)} / ${n(result.capacity_pallets)}`;
  if (w.measure === 'cover') return `${n(v[day], 1)} days`;
  return n(v[day]);
}

function WidgetCard({ w, result, day, products, remove, onDragStart, onDrop }: { w: Widget; result: PlayResult | null; day: number; products: Product[]; remove?: () => void; onDragStart: (e: DragEvent) => void; onDrop?: (e: DragEvent) => void }) {
  const lines = useMemo(() => result ? { s: series(result, 'scoop', w, products), b: series(result, 'baseline', w, products) } : null, [result, w, products]);
  const data = result && lines && day >= 0 ? result.dates.map((d, i) => i <= day
    ? { date: d, scoop: lines.s[i], baseline: lines.b[i], ...(w.measure === 'pallets' ? { capacity: result.capacity_pallets } : {}) }
    : { date: d, scoop: NaN, baseline: NaN }) : [];
  const scopeLabel = w.scope.kind === 'all' || w.title.startsWith(w.scope.label) ? '' : w.scope.label;
  return <article className={`play-widget ${w.chart ? 'wide' : ''}`} draggable onDragStart={onDragStart} onDragOver={e => onDrop && e.preventDefault()} onDrop={onDrop}>
    <header><div><h3>{w.title}</h3>{scopeLabel && <small>{scopeLabel}</small>}</div>{remove && <button className="icon-button" aria-label={`Remove ${w.title}`} onClick={remove}>−</button>}</header>
    {result && day >= 0 ? <>
      <strong className="play-widget-value">{headline(result, w, day, products)}</strong>
      {w.chart && <Chart small data={data} percent={w.measure === 'fill_rate'} lines={[{ key: 'scoop', label: POLICY_LABEL.scoop, color: '#205a4e' }, { key: 'baseline', label: POLICY_LABEL.baseline, color: '#b28a5a', dashed: true }, ...(w.measure === 'pallets' ? [{ key: 'capacity', label: 'Capacity', color: '#c25b4f', dashed: true }] : [])]} />}
    </> : <p className="muted">Waiting for play</p>}
  </article>;
}

function CustomBuilder({ products, close, add }: { products: Product[]; close: () => void; add: (w: Widget) => void }) {
  const tags = useMemo(() => { const m = new Map<string, string>(); products.forEach(p => p.tags.filter(t => t.id.includes(':')).forEach(t => m.set(t.id, displayName(t.name)))); return [...m].sort((a, b) => a[1].localeCompare(b[1])); }, [products]);
  const brands = useMemo(() => [...new Set(products.map(p => p.brand))].sort(), [products]);
  const [measure, setMeasure] = useState<Measure>('on_hand'), [kind, setKind] = useState<Scope['kind']>('tag'), [key, setKey] = useState('');
  const options = kind === 'tag' ? tags : kind === 'brand' ? brands.map(b => [b, b] as [string, string]) : kind === 'sku' ? products.map(p => [p.sku, displayName(p.name)] as [string, string]) : [];
  const label = options.find(o => o[0] === key)?.[1] || '';
  return <Modal title="Add a chart" onClose={close}>
    <div className="play-builder">
      <label className="field">Show<select value={measure} onChange={e => setMeasure(e.target.value as Measure)}>{MEASURES.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}</select></label>
      <label className="field">For<select value={kind} onChange={e => { setKind(e.target.value as Scope['kind']); setKey(''); }}><option value="tag">A category or attribute</option><option value="brand">A brand</option><option value="sku">One product</option><option value="all">All products</option></select></label>
      {kind !== 'all' && <label className="field">Which<select value={key} onChange={e => setKey(e.target.value)}><option value="">Choose…</option>{options.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>}
    </div>
    <div className="modal-actions"><button className="button ghost" onClick={close}>Cancel</button><button className="button primary" disabled={kind !== 'all' && !key} onClick={() => {
      const m = MEASURES.find(x => x.id === measure)!.label;
      const scope: Scope = kind === 'all' ? ALL : { kind, key, label };
      add({ id: `custom-${Date.now()}`, title: kind === 'all' ? m : `${label}: ${m.toLowerCase()}`, measure, scope, chart: measure !== 'fill_rate' && measure !== 'cover' });
      close();
    }}>Add to dashboard</button></div>
  </Modal>;
}

function Comparison({ result }: { result: PlayResult }) {
  const s = result.summary.scoop, b = result.summary.baseline;
  const rows: [string, (x: Summary) => string, number][] = [
    ['Fill rate to stores', x => pct(x.fill_rate), s.fill_rate - b.fill_rate],
    ['Units short', x => n(x.lost_units), b.lost_units - s.lost_units],
    ['Margin lost (HKD)', x => n(x.lost_margin), b.lost_margin - s.lost_margin],
    ['Stockout product-days', x => n(x.stockout_sku_days), b.stockout_sku_days - s.stockout_sku_days],
    ['Average pallets used', x => n(x.avg_pallets, 1), b.avg_pallets - s.avg_pallets],
    ['Peak pallets', x => `${n(x.peak_pallets, 1)} / ${n(result.capacity_pallets)}`, b.peak_pallets - s.peak_pallets],
  ];
  return <section className="play-comparison">
    <h2>{fullDate(result.start)} – {fullDate(result.end)}</h2>
    <table><thead><tr><th/><th>{POLICY_LABEL.scoop}</th><th>{POLICY_LABEL.baseline}</th></tr></thead>
      <tbody>{rows.map(([label, f, better]) => <tr key={label}><td>{label}</td><td className={better > 1e-9 ? 'better' : better < -1e-9 ? 'worse' : ''}>{f(s)}</td><td>{f(b)}</td></tr>)}</tbody></table>
    <p className="muted">{result.notes.baseline} {result.notes.lead_time}{result.notes.autopilot ? ` ${result.notes.autopilot}` : ''}</p>
  </section>;
}

function loadLayout(pid: string): Widget[] | null {
  try { const raw = localStorage.getItem(`scoop-play-layout-${pid}`); return raw ? JSON.parse(raw) : null; } catch { return null; }
}
function saveLayout(pid: string, widgets: Widget[]) {
  try { localStorage.setItem(`scoop-play-layout-${pid}`, JSON.stringify(widgets)); } catch { /* per-viewer convenience only */ }
}

export function PlayWeek({ detail, products, path }: { detail: Detail; products: Product[]; path: string }) {
  const pid = detail.plan.id;
  const pool = useMemo(() => [...standardWidgets(), ...suggestedWidgets(detail, products)], [detail, products]);
  const [showing, setShowing] = useState<Widget[]>(() => loadLayout(pid) || [...standardWidgets().slice(0, 4), ...suggestedWidgets(detail, products).slice(0, 2)]);
  const available = pool.filter(w => !showing.some(s => s.id === w.id));
  const [days, setDays] = useState<7 | 21>(7), [speed, setSpeed] = useState(0);
  const [result, setResult] = useState<PlayResult | null>(null), [loading, setLoading] = useState(false), [error, setError] = useState('');
  const [day, setDay] = useState(-1), [running, setRunning] = useState(false), [builder, setBuilder] = useState(false);
  const dragged = useRef<{ id: string; from: 'showing' | 'available' } | null>(null);
  useEffect(() => saveLayout(pid, showing), [pid, showing]);
  useEffect(() => {
    if (!running || !result) return;
    if (day >= result.days - 1) { setRunning(false); return; }
    const t = setTimeout(() => setDay(d => d + 1), SPEEDS[speed].ms);
    return () => clearTimeout(t);
  }, [running, day, result, speed]);

  async function start() {
    setError('');
    let r = result;
    if (!r || r.days !== days) {
      setLoading(true);
      try { r = await api<PlayResult>(`${path}/play`, 'POST', { days }); setResult(r); }
      catch (e) { setError((e as Error).message); setLoading(false); return; }
      setLoading(false);
    }
    setDay(d => (r && d >= r.days - 1 ? 0 : Math.max(0, d)));
    setRunning(true);
  }
  function drop(to: 'showing' | 'available', beforeId?: string) {
    const d = dragged.current; dragged.current = null;
    if (!d) return;
    if (to === 'available') { setShowing(s => s.filter(w => w.id !== d.id)); return; }
    const w = showing.find(x => x.id === d.id) || available.find(x => x.id === d.id);
    if (!w) return;
    setShowing(s => { const rest = s.filter(x => x.id !== w.id); const i = beforeId ? rest.findIndex(x => x.id === beforeId) : -1; return i < 0 ? [...rest, w] : [...rest.slice(0, i), w, ...rest.slice(i)]; });
  }

  const done = result && day >= result.days - 1 && !running;
  const today = result && day >= 0 ? result.dates[day] : null;
  const events = result && today ? result.events.filter(e => e.date <= today).slice().reverse() : [];
  return <section className="play">
    <div className="play-bar">
      <div className="play-clock"><span>{today ? `Day ${day + 1} of ${result!.days}` : 'Ready'}</span><strong>{today ? fullDate(today) : `Week of ${fullDate(detail.plan.week_start)}`}</strong></div>
      <div className="segmented">{([7, 21] as const).map(d => <button key={d} className={days === d ? 'active' : ''} disabled={running || loading} onClick={() => { setDays(d); setResult(null); setDay(-1); }}>{d === 7 ? '1 week' : '3 weeks'}</button>)}</div>
      <div className="segmented">{SPEEDS.map((s, i) => <button key={s.label} className={speed === i ? 'active' : ''} onClick={() => setSpeed(i)}>{s.label}</button>)}</div>
      {running ? <button className="button ghost" onClick={() => setRunning(false)}>Pause</button>
        : <button className="button primary" disabled={loading} onClick={start}>{loading ? 'Simulating…' : done ? 'Replay' : day >= 0 ? 'Resume' : 'Play'}<Icon name="arrow" size={16} /></button>}
    </div>
    {error && <p className="chat-error" role="alert">{error}</p>}
    <div className="play-body">
      <div>
        <div className="play-zone" onDragOver={e => e.preventDefault()} onDrop={() => drop('showing')}>
          <div className="play-zone-head"><h3>On the dashboard</h3><button className="text-button" onClick={() => setBuilder(true)}>+ Add a chart</button></div>
          <div className="play-grid">{showing.map(w => <WidgetCard key={w.id} w={w} result={result} day={day} products={products}
            remove={() => setShowing(s => s.filter(x => x.id !== w.id))}
            onDragStart={e => { dragged.current = { id: w.id, from: 'showing' }; e.dataTransfer.effectAllowed = 'move'; }}
            onDrop={e => { e.stopPropagation(); drop('showing', w.id); }} />)}
            {!showing.length && <p className="muted">Drag a card here or add a chart.</p>}</div>
        </div>
        <div className="play-zone available" onDragOver={e => e.preventDefault()} onDrop={() => drop('available')}>
          <div className="play-zone-head"><h3>Available</h3></div>
          <div className="play-chips">{available.map(w => <button key={w.id} className="play-chip" draggable onDragStart={() => { dragged.current = { id: w.id, from: 'available' }; }} onClick={() => setShowing(s => [...s, w])}>+ {w.title}</button>)}
            {!available.length && <span className="muted">Everything is on the dashboard.</span>}</div>
        </div>
        {done && result && <Comparison result={result} />}
      </div>
      <aside className="play-events" aria-live="polite">
        <h3>What happened</h3>
        {events.length ? events.map((e, i) => <div key={`${e.date}-${i}`} className={`play-event ${e.tone}`}><span>{date(e.date)}</span><p>{e.text}</p></div>)
          : <p className="muted">{result ? 'Nothing notable yet.' : 'Press Play to run the week.'}</p>}
      </aside>
    </div>
    {builder && <CustomBuilder products={products} close={() => setBuilder(false)} add={w => setShowing(s => [...s, w])} />}
  </section>;
}
