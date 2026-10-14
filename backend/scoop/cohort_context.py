"""Persistent planner context, stored as cohort definitions rather than factors."""
from copy import deepcopy
from datetime import date, datetime
from hashlib import sha256
import json
import math

from .db import session_scope
from .models import Setting

KEY = 'cohort_overrides'


def load_overrides(session=None, as_of=None):
    if session is None:
        with session_scope() as own:
            return load_overrides(own, as_of)
    stored = session.get(Setting, KEY)
    items = json.loads(stored.value) if stored else []
    if as_of is not None:
        items = [x for x in items if not x.get('expires_on') or date.fromisoformat(x['expires_on']) >= as_of]
    return items


def save_overrides(session, items):
    stored = session.get(Setting, KEY)
    if stored is None:
        stored = Setting(key=KEY, value='[]')
        session.add(stored)
    stored.value = json.dumps(items, allow_nan=False)


def validate_override(body):
    value = deepcopy(body)
    kind = value['type']
    if kind not in {'one_off', 'ends_on', 'cap', 'expect', 'cases'}:
        raise ValueError('Unknown override type')
    path = value.get('tag_path', [])
    if any(not isinstance(p.get('id'), str) or not isinstance(p.get('included'), bool) for p in path):
        raise ValueError('A cohort path needs tag IDs and included flags')
    value['tag_path'] = sorted(path, key=lambda p: (p['id'], p['included']))
    value['districts'] = sorted(set(value.get('districts', [])))
    data = value.get('value')
    if kind == 'ends_on':
        value['value'] = date.fromisoformat(data).isoformat()
    elif kind == 'cap':
        if isinstance(data, bool) or not isinstance(data, (int, float)) or not math.isfinite(data) or data <= -1:
            raise ValueError('cap must be a finite fractional change greater than -1')
    elif kind == 'expect':
        if not isinstance(data, dict) or data.get('strength') not in {'low', 'medium', 'high'}:
            raise ValueError('expect needs pct and low, medium or high strength')
        pct = data.get('pct')
        if isinstance(pct, bool) or not isinstance(pct, (int, float)) or not math.isfinite(pct) or pct <= -1:
            raise ValueError('Expected fractional change must be greater than -1')
    elif kind == 'cases':
        if not isinstance(data, dict) or not isinstance(data.get('sku'), str) or type(data.get('cases')) is not int or data['cases'] < 0:
            raise ValueError('cases needs a SKU and a nonnegative integer quantity')
    else:
        value['value'] = None
    if value.get('expires_on'):
        value['expires_on'] = date.fromisoformat(value['expires_on']).isoformat()
    identity = {'tag_path': value['tag_path'], 'districts': value['districts'], 'type': kind}
    if kind == 'cases':
        identity['sku'] = data['sku']
    value['id'] = 'O' + sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    value['note'] = value.get('note', '')
    return value


def put_override(session, body):
    value = validate_override(body)
    previous = load_overrides(session)
    value['created_at'] = datetime.now().isoformat()
    current = [x for x in previous if x['id'] != value['id']] + [value]
    save_overrides(session, current)
    return previous, current, value
