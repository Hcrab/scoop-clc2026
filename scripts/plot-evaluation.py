"""Render publication figures directly from the final evaluation JSON."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

ROOT=Path(__file__).resolve().parents[1]
report=json.loads((ROOT/'reports/evaluation.json').read_text(encoding='utf-8'))
OUT=ROOT/'reports/figures';OUT.mkdir(exist_ok=True,parents=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'axes.labelcolor':'#173f39','text.color':'#173f39','axes.titleweight':'bold','figure.facecolor':'#fbfcf8','axes.facecolor':'#fbfcf8','savefig.facecolor':'#fbfcf8'})

def save(fig,name):
    fig.savefig(OUT/f'{name}.png',dpi=190,bbox_inches='tight')
    fig.savefig(OUT/f'{name}.svg',bbox_inches='tight')
    plt.close(fig)

f=report['forecast']; values=f['store_sku_day']
fig,ax=plt.subplots(figsize=(8,4.4))
labels=['LightGBM','Same weekday\nlast week','28-day\nmoving average'];keys=['scoop_lightgbm','same_weekday_last_week','moving_average_28d']
bars=ax.bar(labels,[values[k] for k in keys],color=['#287966','#aebeb4','#aebeb4'],width=.55)
ax.bar_label(bars,labels=[f'{values[k]:.1%}' for k in keys],padding=7)
ax.yaxis.set_major_formatter(PercentFormatter(1));ax.set_ylabel('WAPE (lower is better)');ax.set_ylim(0,max(values[k] for k in keys)*1.25)
ax.set_title('Daily demand forecast error',loc='left',pad=20)
fig.text(.12,-.025,'Synthetic holdout: April-May 2026. Store × SKU × day. Seed 42.',fontsize=9,color='#64736e')
save(fig,'forecast_wape')

r=report['replay'];fig,ax=plt.subplots(figsize=(8.8,5.7))
for i,p in enumerate(r):
    col='#8d9c93' if p['policy']=='history' else '#287966' if p['policy']=='scoop_forecast' else '#c66e59'
    ax.scatter(p['avg_pallets'],p['fill_rate'],s=90,color=col,marker='o' if p['policy']=='history' else 's' if p['policy']=='scoop_forecast' else '^',zorder=3)
    label=p['label'].replace('scoop_forecast @ ','forecast ').replace('scoop_full @ ','full ')
    offset=(-72,3) if p['policy']=='scoop_full' and p['service_level']!=.96 else (8,9 if p['policy']=='scoop_full' else -12)
    ax.annotate(label,(p['avg_pallets'],p['fill_rate']),xytext=offset,textcoords='offset points',fontsize=8.5)
ax.yaxis.set_major_formatter(PercentFormatter(1));ax.set_xlabel('Average closing inventory (pallets)');ax.set_ylabel('Fulfilment rate');ax.set_title('Service and inventory trade-off',loc='left',pad=20);ax.grid(alpha=.2)
ax.margins(x=.25,y=.22)
fig.text(.12,-.015,'Synthetic replay: June-August 2026. full = forecast + signals; CR = economic quantile.',fontsize=9,color='#64736e')
save(fig,'inventory_service_tradeoff')

d=report['detection'];events=d['events'];fig,ax=plt.subplots(figsize=(9,5.2));y=np.arange(len(events))
for off,key,label,color in [(-.23,'cusum_delay_days','Raw CUSUM','#287966'),(0,'bh_gated_delay_days','BH-gated exposure','#75ad99'),(.23,'weekly_delay_days','Weekly check','#b6c2ba')]:
    vals=[e[key] if e[key] is not None else 0 for e in events]
    bars=ax.barh(y+off,vals,.21,label=label,color=color)
    for bar,e in zip(bars,events):
        ax.text(bar.get_width()+.8,bar.get_y()+bar.get_height()/2,'missed' if e[key] is None else str(e[key]),va='center',fontsize=8)
ax.set_yticks(y,[f"{e['event']} / {e['district']}" for e in events]);ax.invert_yaxis();ax.set_xlabel('Days from planted onset to first eligible alert');ax.set_title('Detection delays, including misses',loc='left',pad=20);ax.legend(frameon=False,loc='lower right',fontsize=9)
maximum=max((e[k] or 0) for e in events for k in ['cusum_delay_days','bh_gated_delay_days','weekly_delay_days']);ax.set_xlim(0,max(10,maximum+18))
fig.text(.12,-.025,'EV01: fruit drift. EV02: chocolate coating decline. Null-world false alarms are reported separately.',fontsize=9,color='#64736e')
save(fig,'detection_delays')
print(OUT)

# Keep generated SVG text clean for source-control whitespace checks.
for path in OUT.glob("*.svg"):
    path.write_text("\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines())+"\n",encoding="utf-8")
