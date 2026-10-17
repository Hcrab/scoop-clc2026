"""Future definition and evidence provenance, without any database mutation."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
import pytest
from scoop.tour_worlds import (START, multiplier, units, private_schema,
                               preserve_questions, historical_evidence, digest)


def test_exact_multiplier_curves_and_half_up():
    for i in range(30):
        day=START+timedelta(days=i)
        assert multiplier('unchanged',day)==Decimal('1.5')
        assert multiplier('summer',day)==(Decimal('1.5') if i<=14 else Decimal(1))
        assert multiplier('growing',day)==Decimal('1.5')+Decimal('.2')*min(i,15)/15
    assert multiplier('growing','2026-08-11')==Decimal('1.7')
    assert units(15,'growing','2026-08-11')==17
    assert units(15,'summer','2026-08-11')==10
    # Scale the same integer realization, once, before store aggregation.
    assert units(37,'growing','2026-07-29')==38
    assert units(38,'growing','2026-07-29')==39
    for branch in ('unchanged','summer','growing'):
        assert units(37,branch,'2026-07-26')==37


def test_replacement_cannot_target_public_or_arbitrary_schema():
    for schema in ('public','tour_recording_x','other','tour_recording_'+'f'*16+'; DROP SCHEMA public'):
        with pytest.raises(ValueError):private_schema(schema)
    assert private_schema('tour_recording_'+'a'*16)=='"tour_recording_'+'a'*16+'"'


def test_context_free_control_disables_real_loader_and_cache_then_restores(monkeypatch):
    from types import SimpleNamespace
    import pandas as pd
    from scoop import cohort_context
    from scoop.tour_worlds import context_free_control
    original_loader=lambda *a,**k:['actual override']
    monkeypatch.setattr(cohort_context,'load_overrides',original_loader)
    read=lambda *a,**k:pd.DataFrame({'value':['actual override']})
    play=SimpleNamespace(read_sql=read,_CACHE={'cached':'result'})
    def simulate(*args):
        assert not play._CACHE
        assert cohort_context.load_overrides()==[]
        assert play.read_sql("SELECT value FROM settings WHERE key = 'cohort_overrides'").empty
        return {'actual':'uncached replay'}
    play.simulate=simulate
    assert context_free_control(play,'P20260727',START)=={'actual':'uncached replay'}
    assert play.read_sql is read and cohort_context.load_overrides is original_loader


def test_grounded_question_keeps_original_snapshot_hash_after_ledger_addition():
    evidence={'detail':{'plan':{'summary':{'weekly_review':{'report':'actual report'}}},
                        'orders':[{'sku':'A','effective_cases':4}]},
              'simulation':{'order_hash':'physical'}}
    answer={'snapshot_hash':digest(evidence),'source_order_hash':'physical','reply':'Genuine recording'}
    old={'base':evidence,'questions':{'why':answer,'heat':answer}}
    new={'base':deepcopy(evidence)}
    new['base']['detail']['orders'][0]['ledger']={'forecast':12}
    preserve_questions(new,old)
    assert new['questions']==old['questions']
    assert new['question_evidence']==evidence
    assert new['questions']['why']['snapshot_hash'] != digest(new['base'])
    new['base']['detail']['plan']['summary']['weekly_review']['report']='Changed history'
    with pytest.raises(ValueError,match='history/report changed'):preserve_questions(new,old)


def test_existing_recordings_have_the_same_historical_evidence_across_contexts():
    import json
    from pathlib import Path
    bundle=json.loads((Path(__file__).resolve().parents[2]/'frontend/public/tour-bundle.json').read_text(encoding='utf-8'))
    before=historical_evidence(bundle['base'])
    for branch in bundle['branches'].values():
        assert historical_evidence(branch['snapshot'])==before


def test_postgres_scaling_expression_matches_python_for_actual_source_cohort():
    """Read-only SQL validates the expression used by private replacement."""
    from scoop import db
    from sqlalchemy import text
    import json
    from pathlib import Path
    bundle=json.loads((Path(__file__).resolve().parents[2]/'frontend/public/tour-bundle.json').read_text(encoding='utf-8'))
    with db.engine.connect() as c:
        c.exec_driver_sql('SET TRANSACTION READ ONLY')
        for branch in ('unchanged','summer','growing'):
            rows=c.execute(text("SELECT date,ordered_units,round(ordered_units::numeric * "
                "CASE WHEN :branch='summer' THEN CASE WHEN date<=:summer_end THEN 1.5 ELSE 1 END "
                "WHEN :branch='growing' THEN 1.5+0.2*LEAST(date-CAST(:start AS date),15)/15 "
                "ELSE 1.5 END / 1.5) FROM public.store_orders WHERE date>=:start AND sku=ANY(:skus)"),
                {'branch':branch,'summer_end':date(2026,8,10),'start':START,'skus':bundle['meta']['strawberry_skus']}).all()
            assert rows
            assert all(int(actual)==units(old,branch,day) for day,old,actual in rows)
