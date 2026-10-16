import { useState } from 'react';
import { date, n, pct } from './api';
import type { DashboardHealth, DashboardHealthProduct } from './types';
import { capacityTone, countTone, fillTone, lowCover, rankedCover } from './dashboardHealth';
import { Modal } from './ui';
import './dashboardKpis.css';

export function CoverList({products,limit}:{products:DashboardHealthProduct[];limit?:number}) {
  const rows=rankedCover(products).slice(0,limit);
  return rows.length?<ol className="dashboard-cover-list">{rows.map(p=><li key={p.sku}><span>{p.name}<small>{p.sku} · lead time {n(p.lead_time_days,1)} days</small></span><strong>{n(p.days_cover,1)} {n(p.days_cover,1)==='1'?'day':'days'}</strong></li>)}</ol>:<p className="muted">No products with usable recent demand.</p>;
}

export function DashboardKpis({health,flowYesterday=false}:{health:DashboardHealth;flowYesterday?:boolean}) {
  const [open,setOpen]=useState(false),low=lowCover(health.products);
  return <><div className="dashboard-kpis" aria-label="Warehouse health">
    <div className={`dashboard-kpi ${fillTone(health.fill_rate)}`} title={`${n(health.shipped_units)} / ${n(health.requested_units)} units since ${date(health.period_start)}`}><span>Fill rate</span><strong>{pct(health.fill_rate)}</strong><small>of store requests{flowYesterday?' · through yesterday':''}</small></div>
    <div className={`dashboard-kpi ${countTone(health.stockout_skus.length)}`}><span>Stockouts</span><strong>{n(health.stockout_skus.length)} <em>products</em></strong><small>{n(health.stockout_sku_days)} product-days</small></div>
    <button className={`dashboard-kpi ${countTone(low.length)}`} onClick={()=>setOpen(true)} aria-label={`Low cover: ${low.length} products. View list`}><span>Low cover <b aria-hidden="true">↗</b></span><strong>{n(low.length)} <em>products</em></strong><small>Tap to see which</small></button>
    <div className={`dashboard-kpi ${capacityTone(health.pallets,health.capacity_pallets)}`}><span>Cold store</span><strong>{n(health.pallets,1)} <em>/ {n(health.capacity_pallets,1)}</em></strong><small>Pallets · peak {n(health.peak_pallets,1)}</small></div>
  </div>{open&&<Modal title={`Low cover · ${low.length} products`} onClose={()=>setOpen(false)}>{low.length?<CoverList products={low}/>:<p>No products below supplier lead time.</p>}</Modal>}</>;
}
