import { useEffect, useRef, type ReactNode } from 'react';
import { n, pct, date } from './api';
export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    settings: <><circle cx="12" cy="12" r="3"/><path d="m9 3 1-1h4l1 1 1 3 3 1 2 3-1 3-2 2-1 3-3 2-3-1-2-2-3-1-2-3 1-3 2-2 1-3Z"/></>,
    plans: <><rect x="4" y="3" width="16" height="18" rx="3"/><path d="M8 8h8M8 12h8M8 16h5"/></>,
    stores: <><path d="m3 9 2-6h14l2 6M3 9v3a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0V9M5 15v6h14v-6M10 21v-6h4v6"/></>,
    catalog: <><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/></>,
    evaluation: <><path d="M4 20V4M4 20h16M8 16V9M13 16V5M18 16v-4"/></>,
    arrow: <><path d="M5 12h14m-5-5 5 5-5 5"/></>,
    check: <path d="m5 12 4 4L19 6"/>,
    spark: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/></>,
    plus: <path d="M12 5v14M5 12h14"/>,
    close: <path d="m6 6 12 12M6 18 18 6"/>,
    download: <><path d="M12 3v12m-4-4 4 4 4-4M4 17v4h16v-4"/></>,
    search: <><circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/></>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    cone: <><path d="m7 13 5 9 5-9M5 13h14a3 3 0 0 0 1-5 8 8 0 0 0-16 0 3 3 0 0 0 1 5ZM8 16h8M10 19h4"/></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.spark}</svg>;
}
export function Empty({ title, children, icon = 'plans' }: { title: string; children?: ReactNode; icon?: string }) { return <div className="empty"><span className="empty-icon"><Icon name={icon} size={30}/></span><h3>{title}</h3><p>{children}</p></div>; }
export function Loading({ text = 'Loading your workspace…' }: { text?: string }) { return <div className="loading"><span className="spinner"/>{text}</div>; }
export function Badge({ children, tone = '' }: { children: ReactNode; tone?: string }) { return <span className={`badge ${tone}`}>{children}</span>; }
export function DataView({ value }: { value: unknown }) {
  if (value == null) return <span className="muted">Not available</span>;
  if (Array.isArray(value)) return <div className="data-list">{value.map((v, i) => <div key={i}><DataView value={v}/></div>)}</div>;
  if (typeof value === 'object') return <dl className="data-grid">{Object.entries(value).map(([key, v]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd><DataView value={v}/></dd></div>)}</dl>;
  return <span>{typeof value === 'number' ? n(value, 4) : typeof value === 'boolean' ? value ? 'Yes' : 'No' : String(value)}</span>;
}
export function Chart({ data, lines, percent = false, small = false }: { data: Record<string, string | number>[]; lines: { key: string; label: string; color: string; dashed?: boolean }[]; percent?: boolean; small?: boolean }) {
  if (!data.length) return <div className="chart-empty">The trend is not available yet.</div>;
  const width = 680, height = small ? 150 : 260, left = 48, right = 18, top = 20, bottom = 36;
  const values = data.flatMap(d => lines.map(l => Number(d[l.key]))).filter(Number.isFinite);
  const lo = Math.min(0, ...values), hi = Math.max(...values, 0.001) * 1.12;
  const x = (i: number) => left + i / Math.max(1, data.length - 1) * (width - left - right);
  const y = (v: number) => top + (hi - v) / (hi - lo) * (height - top - bottom);
  const summary = `${date(String(data[0].date))} to ${date(String(data.at(-1)!.date))}. ${lines.map(l=>{const value = data.map(d=>Number(d[l.key])).filter(Number.isFinite).at(-1);return `${l.label}: ${value==null?'unavailable':percent?pct(value):n(value,1)} at the latest observation`}).join('. ')}.`;
  return <div className={`chart ${small ? 'small' : ''}`}><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={summary}>
    {[0, 1, 2, 3].map(i => { const val = lo + (hi - lo) * i / 3; return <g key={i}><line x1={left} x2={width - right} y1={y(val)} y2={y(val)} stroke="#e4e9e3"/><text x={left - 10} y={y(val) + 4} textAnchor="end">{percent ? pct(val) : n(val, 1)}</text></g>; })}
    {lines.map(l => <polyline key={l.key} fill="none" stroke={l.color} strokeWidth="2.8" strokeDasharray={l.dashed ? '6 5' : undefined} strokeLinejoin="round" strokeLinecap="round" points={data.map((d,i)=>({i,v:Number(d[l.key])})).filter(d=>Number.isFinite(d.v)).map(d=>`${x(d.i)},${y(d.v)}`).join(' ')}/>)}
    {[0, Math.floor((data.length - 1) / 2), data.length - 1].filter((v, i, a) => a.indexOf(v) === i).map(i => <text key={i} x={x(i)} y={height - 10} textAnchor={i === 0 ? 'start' : i === data.length - 1 ? 'end' : 'middle'}>{date(String(data[i].date))}</text>)}
  </svg><div className="legend">{lines.map(l => <span key={l.key}><i style={{ background:l.dashed?'none':l.color,borderTop:l.dashed?`2px dashed ${l.color}`:undefined }}/>{l.label} · {l.dashed?'dashed':'solid'}</span>)}</div><p className="chart-summary">{summary}</p></div>;
}

export function Metric({ label, value, unit }: { label: string; value: string; unit: string }) { return <div className="metric"><span>{label}</span><strong>{value}</strong><small>{unit}</small></div>; }
export function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => { const before = document.activeElement as HTMLElement | null; ref.current?.focus(); const overflow = document.body.style.overflow; document.body.style.overflow = 'hidden'; return () => { document.body.style.overflow = overflow; before?.focus(); }; }, []);
  useEffect(() => { const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); if (e.key === 'Tab') { const elements = Array.from(ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],summary') || []); const first = elements[0], last = elements[elements.length - 1]; if (e.shiftKey && (document.activeElement === first || document.activeElement === ref.current)) { e.preventDefault(); last?.focus(); } else if (!e.shiftKey && (document.activeElement === last || document.activeElement === ref.current)) { e.preventDefault(); first?.focus(); } } }; document.addEventListener('keydown', handler); return () => document.removeEventListener('keydown', handler); }, [onClose]);
  return <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}><section ref={ref} tabIndex={-1} className="modal" role="dialog" aria-modal="true" aria-label={title}><button className="modal-close icon-button" aria-label="Close dialog" onClick={onClose}><Icon name="close"/></button><div className="eyebrow">SCOOP PLANNER</div><h2>{title}</h2>{children}</section></div>;
}
