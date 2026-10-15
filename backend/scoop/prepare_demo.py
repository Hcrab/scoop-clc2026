"""Build the default plan after a fresh load; never reload or delete source data.

Use --report to let the configured provider prepare the visual report as well.
Without a live key the ordinary card-list report remains available.
"""
from datetime import date
import argparse

from .db import SessionLocal, get_setting, set_setting
from .demo_config import DEMO_SEED, DEMO_WEEK, DEMO_SCENARIO
from .models import Plan
from .planning import build_plan


def prepare(report=False):
    if get_setting('seed') != str(DEMO_SEED):
        raise RuntimeError('Load the seed 93 demo with python -m scoop.synth.load first.')
    week = date.fromisoformat(DEMO_WEEK)
    pid = 'P' + week.strftime('%Y%m%d')
    with SessionLocal() as session:
        exists = session.get(Plan, pid) is not None
    if not exists:
        build_plan(week)
    set_setting('today', DEMO_WEEK)
    set_setting('demo_scenario', DEMO_SCENARIO)
    if report:
        from .ai.weekly import prepare as prepare_report
        result = prepare_report(pid)
        print('Report:', result['status'])
    print('Demo ready:', pid, 'seed', DEMO_SEED, 'week', DEMO_WEEK)
    return pid


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', action='store_true')
    prepare(parser.parse_args().report)
