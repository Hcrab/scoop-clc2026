"""Measure the selected P6 week before the authorized physical-capacity correction."""
from datetime import date
import json
from pathlib import Path

from scoop.db import SessionLocal, get_setting
from scoop.models import Plan
from scoop.planning import build_plan
from scoop.play import simulate
from scoop.api.service import clean


def main():
    assert get_setting('seed') == '93'
    week=date(2026,7,20)
    pid='P20260720'
    with SessionLocal() as session:
        exists=session.get(Plan,pid) is not None
    if not exists:
        print('Creating selected-week plan through build_plan; no report/LLM call',flush=True)
        build_plan(week)
    result=simulate(pid,week)
    evidence={'stage':'before_capacity_correction','week':week,'capacity_pallets':result['capacity_pallets'],
              'days':result['days'],'summary':result['summary'],'affected_comparison':result['affected_comparison'],
              'history_rule_peak_fraction':result['summary']['baseline']['peak_pallets']/result['capacity_pallets']}
    Path('reports/p6-play-before-capacity.json').write_text(json.dumps(clean(evidence),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(clean(evidence)),flush=True)


if __name__=='__main__':
    main()
