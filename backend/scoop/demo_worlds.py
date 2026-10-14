"""Transactional synthetic-world snapshots. No active table is dropped."""
from datetime import date,timedelta
from dataclasses import dataclass
import io,json,re,sys
from sqlalchemy import text,select
from sqlalchemy.orm import Session
from .db import engine
from .models import Base,Plan
from .demo_gate import gate

WEEKS=[(date(2026,6,1)+timedelta(weeks=i)).isoformat() for i in range(14)]
SCENARIOS=[
    dict(id='july-context',name='Summer trading',description='Follow the original retail network through changing summer demand and weekly purchasing decisions.',seed=42,default_week='2026-07-13',weeks=WEEKS),
    dict(id='august-seed73',name='Another summer',description='Explore another simulated season with different store orders, weather and demand patterns.',seed=73,default_week='2026-07-27',weeks=WEEKS),
]
PLANNING={'plans','findings','hypotheses','questions','decisions','direction_items','purchase_suggestions','watch_items','chat_messages'}
SOURCE_FIELDS={'stores':'stores','nodes':'nodes','suppliers':'suppliers','products':'products','product_nutrition':'nutrition','tag_dimensions':'tag_dimensions','tags':'tags','product_tags':'product_tags','weather_daily':'weather','weather_forecasts':'forecasts','promotions':'promotions','store_orders':'store_orders','node_inventory':'node_inventory','purchase_orders':'purchase_orders','ground_truth_events':'events'}

def quoted(value):
    if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,62}',value): raise ValueError('Invalid internal schema identifier')
    return '"'+value+'"'

def clear_runtime_caches():
    for name in ['scoop.algorithms.runs','scoop.monitoring']:
        module=sys.modules.get(name)
        if module and hasattr(module,'reset_cache'): module.reset_cache()
    planning=sys.modules.get('scoop.planning')
    if planning: planning._CAPACITY_DEMAND_CACHE.clear()
    forecast=sys.modules.get('scoop.algorithms.forecast')
    if forecast:
        forecast._PROTECTION_CACHE.clear()
        forecast._DAILY_MEAN_CACHE.clear()

class WorldPreparationError(RuntimeError): pass

class WorldManager:
    def __init__(self,db_engine=engine,active_schema='public',namespace='scoop_demo',activity_gate=gate,generator=None,builder=None,invalidate=clear_runtime_caches):
        self.engine=db_engine;self.active=active_schema;self.namespace=namespace;self.gate=activity_gate
        quoted(active_schema);quoted(namespace)
        self.generator=generator;self.builder=builder;self.invalidate=invalidate
        self.tables=list(Base.metadata.sorted_tables)
    def schema(self,seed): return self.namespace+'_world_'+str(seed)
    def setting(self,connection,key,default=None):
        value=connection.execute(text(f'SELECT value FROM {quoted(self.active)}.settings WHERE key=:key'),{'key':key}).scalar()
        return value if value is not None else default
    def put(self,connection,key,value):
        connection.execute(text(f'INSERT INTO {quoted(self.active)}.settings(key,value) VALUES(:key,:value) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value'),{'key':key,'value':str(value)})
    def active_seed(self):
        with self.engine.connect() as c: return int(self.setting(c,'seed','42'))
    def info(self):
        with self.engine.connect() as c:
            seed=int(self.setting(c,'seed','42'));today=self.setting(c,'today','2026-07-13')
            scenario=self.setting(c,'demo_scenario','july-context' if seed==42 else 'august-seed73')
        day=date.fromisoformat(today)
        return dict(scenario_id=scenario,today=today,week_start=(day-timedelta(days=day.weekday())).isoformat(),scenarios=SCENARIOS)
    def exists(self,c,schema): return c.execute(text('SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name=:schema)'),{'schema':schema}).scalar()
    def snapshot(self,c,schema):
        c.execute(text(f'CREATE SCHEMA IF NOT EXISTS {quoted(schema)}'))
        for table in self.tables:
            name=quoted(table.name)
            c.execute(text(f'CREATE TABLE IF NOT EXISTS {quoted(schema)}.{name} AS SELECT * FROM {quoted(self.active)}.{name} WITH NO DATA'))
            c.execute(text(f'TRUNCATE {quoted(schema)}.{name}'))
            c.execute(text(f'INSERT INTO {quoted(schema)}.{name} SELECT * FROM {quoted(self.active)}.{name}'))
    def clear(self,c,planning_only=False):
        for table in reversed(self.tables):
            if table.name=='settings' and planning_only: continue
            if not planning_only or table.name in PLANNING: c.execute(text(f'DELETE FROM {quoted(self.active)}.{quoted(table.name)}'))
        if planning_only: c.execute(text(f"DELETE FROM {quoted(self.active)}.purchase_orders WHERE source='scoop'"))
    def restore(self,c,schema):
        self.clear(c)
        for table in self.tables: c.execute(text(f'INSERT INTO {quoted(self.active)}.{quoted(table.name)} SELECT * FROM {quoted(schema)}.{quoted(table.name)}'))
        for table,column in [('decisions','id'),('chat_messages','id')]:
            target=self.active+'.'+table
            sequence=c.execute(text('SELECT pg_get_serial_sequence(:table,:column)'),{'table':target,'column':column}).scalar()
            if sequence:
                maximum=c.execute(text(f'SELECT MAX({quoted(column)}) FROM {quoted(self.active)}.{quoted(table)}')).scalar()
                c.execute(text('SELECT setval(CAST(:sequence AS regclass),:value,:called)'),{'sequence':sequence,'value':maximum or 1,'called':maximum is not None})
    def generate(self,c,seed):
        if self.generator: world=self.generator(seed)
        else:
            from .synth.generate import generate
            world=generate(seed)
        self.clear(c)
        raw=c.connection.driver_connection
        for table in self.tables:
            if table.name not in SOURCE_FIELDS: continue
            frame=getattr(world,SOURCE_FIELDS[table.name]).copy()
            if frame.empty: continue
            if table.name=='ground_truth_events': frame['districts']=frame['districts'].apply(json.dumps)
            buffer=io.StringIO();frame.to_csv(buffer,index=False,header=False,na_rep='\\N')
            columns=', '.join(quoted(str(column)) for column in frame.columns)
            with raw.cursor() as cursor:
                with cursor.copy(f"COPY {quoted(self.active)}.{quoted(table.name)} ({columns}) FROM STDIN WITH (FORMAT csv, NULL '\\N')") as copy: copy.write(buffer.getvalue())
        self.put(c,'seed',seed)
    def build(self,week):
        if self.builder: return self.builder(week)
        from .planning import build_plan
        from .db import session_scope
        from . import workflow
        with session_scope() as s:
            old=s.scalar(select(Plan).where(Plan.week_start==week))
            if old: return old.id
        pid=build_plan(week)
        with session_scope() as s: workflow.initialize_plan(s,s.get(Plan,pid))
        return pid
    def choose(self,scenario_id,week_start,reset=False):
        scenario=next((s for s in SCENARIOS if s['id']==scenario_id),None)
        if not scenario or week_start not in scenario['weeks']: raise ValueError('Select a listed simulation and Monday.')
        seed=scenario['seed'];week=date.fromisoformat(week_start)
        with self.gate.replacement():
            try:
                previous=self.active_seed();previous_schema=self.schema(previous)
                # This backup includes existing user plans before any switch/reset.
                with self.engine.begin() as c: self.snapshot(c,previous_schema)
            except Exception as exc: raise WorldPreparationError('Your simulation has not been changed. Its backup could not be prepared; please try again.') from exc
            try:
                with self.engine.begin() as c:
                    if previous!=seed:
                        if self.exists(c,self.schema(seed)): self.restore(c,self.schema(seed))
                        else: self.generate(c,seed)
                    if reset:
                        self.snapshot(c,self.namespace+'_reset_backup')
                        self.clear(c,planning_only=True)
                    self.put(c,'seed',seed);self.put(c,'today',week_start);self.put(c,'demo_scenario',scenario_id)
                self.invalidate()
                pid=self.build(week)
                with self.engine.begin() as c: self.snapshot(c,self.schema(seed))
            except Exception as exc:
                try:
                    with self.engine.begin() as c: self.restore(c,previous_schema)
                    self.invalidate()
                except Exception as restore_error: raise WorldPreparationError('The simulation could not be prepared or restored. Your previous snapshot is retained for recovery.') from restore_error
                raise WorldPreparationError('The simulation could not be prepared. Your previous progress has been restored; try again.') from exc
            return dict(id=pid,today=week_start,scenario_id=scenario_id)

manager=WorldManager()
