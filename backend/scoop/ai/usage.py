"""Small durable call ledger: bounded demo usage, no credentials or prompt text."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import uuid

from ..config import ROOT, settings

LEDGER = ROOT / 'data' / 'cache' / 'assistant-usage.sqlite3'
# Conservative standard-tier allowance; actual billing depends on provider/model.
# Higher than Gemini 3.8 Flash standard rates verified 2026-10-14.
INPUT_USD_PER_MILLION = 1.5
OUTPUT_USD_PER_MILLION = 7.5

def rates(model):
    # Argon standard rates after its introductory period; reserve conservatively.
    return (4.0,20.0) if model.startswith('gemini-4') else (INPUT_USD_PER_MILLION,OUTPUT_USD_PER_MILLION)


class UsageLimit(Exception):
    pass


@contextmanager
def ledger(path=None):
    path=Path(path or LEDGER)
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=10)
    try:
        db.execute('CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, created_at TEXT, model TEXT, request_hash TEXT, status TEXT, input_tokens INTEGER, output_tokens INTEGER, reserved_usd REAL, estimated_usd REAL)')
        db.commit()
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def reserve(model, request_hash, max_input_tokens, max_output_tokens, *, path=None):
    input_rate,output_rate=rates(model)
    amount=(max_input_tokens*input_rate+max_output_tokens*output_rate)/1_000_000
    with ledger(path) as db:
        db.execute('BEGIN IMMEDIATE')
        total,count=db.execute('SELECT COALESCE(SUM(COALESCE(estimated_usd,reserved_usd)),0), COUNT(*) FROM calls').fetchone()
        if count>=settings.llm_max_calls or total+amount>settings.llm_budget_usd:
            raise UsageLimit('The configured demo assistant allowance is used up.')
        rid=uuid.uuid4().hex
        db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?,?,?)',(rid,datetime.now(timezone.utc).isoformat(),model,request_hash,'reserved',None,None,amount,None))
    return rid


def finish(rid, usage, status='ok', *, path=None):
    incoming=int(usage.get('promptTokenCount',0))
    outgoing=int(usage.get('candidatesTokenCount',0))+int(usage.get('thoughtsTokenCount',0))
    with ledger(path) as db:
        model=db.execute('SELECT model FROM calls WHERE id=?',(rid,)).fetchone()[0]
        input_rate,output_rate=rates(model)
        amount=(incoming*input_rate+outgoing*output_rate)/1_000_000
        # Unknown transport outcomes retain the reservation rather than pretending zero use.
        db.execute('UPDATE calls SET status=?,input_tokens=?,output_tokens=?,estimated_usd=? WHERE id=?',
                   (status,incoming,outgoing,amount if usage else None,rid))


def summary(*, path=None):
    with ledger(path) as db:
        count,spent,inputs,outputs=db.execute('SELECT COUNT(*),COALESCE(SUM(COALESCE(estimated_usd,reserved_usd)),0),COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0) FROM calls').fetchone()
    return {'calls':count,'estimated_usd':round(spent,6),'input_tokens':inputs,'output_tokens':outputs,'limit_usd':settings.llm_budget_usd,'call_limit':settings.llm_max_calls}
