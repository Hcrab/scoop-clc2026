"""Read-only acceptance fingerprint for tour browser runs."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from scoop import db
from scoop.ai.usage import summary
spec=importlib.util.spec_from_file_location('tour_builder',ROOT/'scripts/build-tour-bundle.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
print(json.dumps({'database':builder.fingerprint(db.engine),'provider':summary()},sort_keys=True))
