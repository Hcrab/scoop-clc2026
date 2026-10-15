"""Small, durable initial planning snapshots for a synthetic world and week."""
from datetime import date, datetime
import json
import re

from sqlalchemy import Date, DateTime, MetaData, select, text

from .db import engine
from .models import Base, Plan

INITIAL_TABLES = ('plans', 'findings', 'hypotheses', 'questions',
                  'direction_items', 'purchase_suggestions', 'watch_items')


def template_key(seed, week_start):
    return f'initial_{seed}_{week_start.isoformat()}'


def _table(name, schema):
    return Base.metadata.tables[name].to_metadata(MetaData(), schema=schema)


def _quoted(schema):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,62}', schema):
        raise ValueError('Invalid internal schema identifier')
    return '"' + schema + '"'


def _encode_row(table, row):
    return {column.name: value.isoformat() if isinstance(value, (date, datetime)) else value
            for column, value in zip(table.columns, row)}


def _decode_row(table, row):
    decoded = dict(row)
    for column in table.columns:
        value = decoded.get(column.name)
        if value is not None:
            if isinstance(column.type, DateTime):
                decoded[column.name] = datetime.fromisoformat(value)
            elif isinstance(column.type, Date):
                decoded[column.name] = date.fromisoformat(value)
    return decoded


def _rows(connection, schema, plan_id):
    result = {}
    finding_ids = None
    for name in INITIAL_TABLES:
        table = _table(name, schema)
        if name == 'plans':
            query = select(table).where(table.c.id == plan_id)
        elif name == 'hypotheses':
            if finding_ids is None:
                raise AssertionError('Findings must precede hypotheses')
            query = select(table).where(table.c.finding_id.in_(finding_ids))
        else:
            query = select(table).where(table.c.plan_id == plan_id)
        query = query.order_by(*(table.c[column.name] for column in table.primary_key.columns))
        records = [_encode_row(table, row) for row in connection.execute(query)]
        result[name] = records
        if name == 'findings':
            finding_ids = [row['id'] for row in records]
    return result


def _same_mechanics(before, after):
    # Report preparation may add AI findings and questions; user changes to the
    # plan, order list, directions, or widgets must never replace the baseline.
    for name in ('plans', 'direction_items', 'purchase_suggestions', 'watch_items'):
        old, new = before[name], after[name]
        if name == 'plans':
            old = [{k: v for k, v in row.items() if k != 'summary'} for row in old]
            new = [{k: v for k, v in row.items() if k != 'summary'} for row in new]
        if old != new:
            return False
    return True


def _has_user_progress(connection, schema, plan_id):
    for name in ('decisions', 'chat_messages'):
        if connection.execute(text(f'SELECT 1 FROM {schema}.{name} WHERE plan_id=:id LIMIT 1'),
                              {'id': plan_id}).first():
            return True
    return False


def capture_initial_plan(db_engine=engine, active_schema=None, *, seed=None,
                         week_start=None, complete=False, connection=None):
    """Save a pristine plan once; add its first prepared report while still untouched.

    This is also the entry point for seeding a reviewed, clean existing plan:
    ``capture_initial_plan(week_start=date(...), complete=True)``.
    """
    if week_start is None:
        raise ValueError('week_start is required')
    if isinstance(week_start, str):
        week_start = date.fromisoformat(week_start)
    def capture(connection):
        schema_name=active_schema or connection.execute(text('SELECT current_schema()')).scalar_one()
        schema = _quoted(schema_name)
        current_seed=seed
        if current_seed is None:
            current_seed = connection.execute(text(f"SELECT value FROM {schema}.settings WHERE key='seed'")).scalar()
        if current_seed is None:
            return False
        key = template_key(current_seed, week_start)
        plan_id = 'P' + week_start.strftime('%Y%m%d')
        rows = _rows(connection, schema_name, plan_id)
        if not rows['plans']:
            return False
        if rows['plans'][0]['stage'] != 'discover' or _has_user_progress(connection, schema, plan_id):
            return False
        overrides=connection.execute(text(f"SELECT value FROM {schema}.settings WHERE key='cohort_overrides'")).scalar()
        if overrides and json.loads(overrides):
            return False
        rows['plans'][0]['summary']={**(rows['plans'][0]['summary'] or {}),
                                    'flow':{'step':'report','max_step':'report','notice':None}}
        prior = connection.execute(text(f'SELECT value FROM {schema}.settings WHERE key=:key'), {'key': key}).scalar()
        if prior:
            template = json.loads(prior)
            if template['complete'] or not complete or not _same_mechanics(template['rows'], rows):
                return False
            template = {'complete': True, 'rows': rows}
        else:
            template = {'complete': complete, 'rows': rows}
        connection.execute(text(f'INSERT INTO {schema}.settings(key,value) VALUES(:key,:value) '
                                'ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value'),
                           {'key': key, 'value': json.dumps(template, ensure_ascii=False)})
        return True
    if connection is not None:
        return capture(connection)
    with db_engine.begin() as opened:
        return capture(opened)


def load_initial_plan(connection, active_schema, seed, week_start):
    value = connection.execute(text(f'SELECT value FROM {_quoted(active_schema)}.settings WHERE key=:key'),
                               {'key': template_key(seed, week_start)}).scalar()
    return json.loads(value)['rows'] if value else None


def restore_initial_plan(connection, active_schema, rows):
    """Insert saved planning rows after the caller clears mutable planning state."""
    for name in INITIAL_TABLES:
        table = _table(name, active_schema)
        data = [_decode_row(table, row) for row in rows[name]]
        if data:
            connection.execute(table.insert(), data)
