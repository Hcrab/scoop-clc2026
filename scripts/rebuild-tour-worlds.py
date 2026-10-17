"""Parent-only integration entry point; run after all tour owners have finished.

Retains the private tour_recording_* schema and immutable original demand for
inspection. It never deletes public data or invokes a provider. Cleanup, after
acceptance: DROP SCHEMA "<schema_name from data/tour/bundle-build.json>" CASCADE.
Expected runtime: several minutes (six actual two-week replays plus API recording).
"""
from pathlib import Path
import runpy

if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).with_name('build-tour-bundle.py')), run_name='__main__')
