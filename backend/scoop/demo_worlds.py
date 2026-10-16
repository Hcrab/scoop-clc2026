"""Transactional synthetic-world snapshots. No active table is dropped."""
from datetime import date,timedelta
from dataclasses import dataclass
import io,json,re,sys
from sqlalchemy import text,select
from sqlalchemy.orm import Session
from .db import engine
from .models import Base,Plan
from .demo_gate import gate,DemoBusy
from .demo_config import DEMO_SEED, DEMO_WEEK, DEMO_SCENARIO

WEEKS=[(date(2026,6,1)+timedelta(weeks=i)).isoformat() for i in range(14)]
SCENARIOS=[
    dict(id='july-context',name='Summer trading',description='Follow the original retail network through changing summer demand and weekly purchasing decisions.',seed=42,default_week='2026-07-13',weeks=WEEKS),
    dict(id='august-seed73',name='Another summer',description='Explore another simulated season with different store orders, weather and demand patterns.',seed=73,default_week='2026-07-27',weeks=WEEKS),
    dict(id='crosscurrents',name='Crosscurrents',description='Explore a retail network with changing local demand and a different product mix.',seed=91,default_week='2026-07-27',weeks=WEEKS),
    dict(id='new-season',name='New season',description='Explore a new simulated season of store orders and weekly purchasing decisions.',seed=92,default_week='2026-07-27',weeks=WEEKS),
    dict(id=DEMO_SCENARIO,name='Demo warehouse',description='Synthetic warehouse data.',seed=DEMO_SEED,default_week=DEMO_WEEK,weeks=WEEKS),
]
PLANNING={'plans','simulation_runs','findings','hypotheses','questions','decisions','direction_items','purchase_suggestions','watch_items','chat_messages'}
SOURCE_FIELDS={'stores':'stores','nodes':'nodes','suppliers':'suppliers','products':'products','product_nutrition':'nutrition','tag_dimensions':'tag_dimensions','tags':'tags','product_tags':'product_tags','weather_daily':'weather','weather_forecasts':'forecasts','promotions':'promotions','store_orders':'store_orders','node_inventory':'node_inventory','purchase_orders':'purchase_orders','ground_truth_events':'events'}

def quoted(value):
    if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,62}',value): raise ValueError('Invalid internal schema identifier')
    return '"'+value+'"'

def clear_runtime_caches():
    for name in ['scoop.algorithms.runs','scoop.monitoring','scoop.algorithms.protection_calibration']:
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
        with self.engine.connect() as c: return int(self.setting(c,'seed',str(DEMO_SEED)))
    def info(self):
        with self.engine.connect() as c:
            seed=int(self.setting(c,'seed',str(DEMO_SEED)));today=self.setting(c,'today',DEMO_WEEK)
            scenario=self.setting(c,'demo_scenario',next((s['id'] for s in SCENARIOS if s['seed']==seed),DEMO_SCENARIO))
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
        if planning_only:
            c.execute(text(f"DELETE FROM {quoted(self.active)}.purchase_orders WHERE source='scoop'"))
            c.execute(text(f"DELETE FROM {quoted(self.active)}.settings WHERE key='cohort_overrides'"))
    def clear_plan(self,c,plan_id):
        schema=quoted(self.active)
        c.execute(text(f'DELETE FROM {schema}.hypotheses WHERE finding_id IN '
                       f'(SELECT id FROM {schema}.findings WHERE plan_id=:id)'),{'id':plan_id})
        for name in ('simulation_runs','findings','questions','decisions','direction_items',
                     'purchase_suggestions','watch_items','chat_messages'):
            c.execute(text(f'DELETE FROM {schema}.{quoted(name)} WHERE plan_id=:id'),{'id':plan_id})
        c.execute(text(f'DELETE FROM {schema}.plans WHERE id=:id'),{'id':plan_id})
    def restore(self,c,schema):
        self.clear(c)
        for table in self.tables:
            if table.name=='simulation_runs' and c.execute(text('SELECT to_regclass(:name)'),
                    {'name':schema+'.simulation_runs'}).scalar() is None:
                continue  # Snapshots saved before this cache table existed have no runs.
            c.execute(text(f'INSERT INTO {quoted(self.active)}.{quoted(table.name)} SELECT * FROM {quoted(schema)}.{quoted(table.name)}'))
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
    def build(self,week,*,report=True):
        if self.builder: return self.builder(week)
        from .planning import build_plan
        from .db import session_scope
        with session_scope() as s:
            old=s.scalar(select(Plan).where(Plan.week_start==week))
            if old: return old.id
        pid=build_plan(week)
        if report:
            from .ai.weekly import prepare
            prepare(pid)
        return pid
    def choose(self,scenario_id,week_start,reset=False):
        scenario=next((s for s in SCENARIOS if s['id']==scenario_id),None)
        if not scenario or week_start not in scenario['weeks']: raise ValueError('Select a listed simulation and Monday.')
        seed=scenario['seed'];week=date.fromisoformat(week_start)
        fast_reset=False
        if reset:
            from .demo_reset import template_key
            with self.engine.connect() as c:
                fast_reset=int(self.setting(c,'seed',str(DEMO_SEED)))==seed and bool(c.execute(
                    text(f'SELECT 1 FROM {quoted(self.active)}.settings WHERE key=:key'),
                    {'key':template_key(seed,week)}).scalar())
        with self.gate.replacement(planning_only=fast_reset):
            previous=self.active_seed()
            if fast_reset and previous!=seed:raise DemoBusy('The selected simulation changed. Please try again.')
            if previous==seed:
                from .demo_reset import load_initial_plan,restore_initial_plan
                try:
                    with self.engine.begin() as c:
                        initial=load_initial_plan(c,self.active,seed,week)
                        existing=c.execute(text(f'SELECT id FROM {quoted(self.active)}.plans WHERE week_start=:week'),
                                           {'week':week}).scalar()
                        if reset and initial is not None:
                            self.clear(c,planning_only=True)
                            restore_initial_plan(c,self.active,initial)
                        elif not reset and not existing and initial is not None:
                            restore_initial_plan(c,self.active,initial)
                        if initial is not None or (existing and not reset):
                            self.put(c,'seed',seed);self.put(c,'today',week_start);self.put(c,'demo_scenario',scenario_id)
                            return dict(id='P'+week.strftime('%Y%m%d'),today=week_start,scenario_id=scenario_id)
                except Exception as exc:
                    raise WorldPreparationError('The simulation could not be restored. Your previous progress is unchanged.') from exc
                if not reset or not existing:
                    try:
                        with self.engine.begin() as c:
                            old_today=self.setting(c,'today',DEMO_WEEK)
                            old_scenario=self.setting(c,'demo_scenario',scenario_id)
                            self.put(c,'today',week_start);self.put(c,'demo_scenario',scenario_id)
                        pid=self.build(week,report=not reset)
                        from .demo_reset import capture_initial_plan
                        capture_initial_plan(self.engine,self.active,seed=seed,week_start=week)
                        with self.engine.begin() as c:
                            if reset:
                                initial=load_initial_plan(c,self.active,seed,week)
                                if initial is None:raise RuntimeError('Initial planning state was not prepared')
                                self.clear(c,planning_only=True)
                                restore_initial_plan(c,self.active,initial)
                            self.put(c,'today',week_start);self.put(c,'demo_scenario',scenario_id)
                        return dict(id=pid,today=week_start,scenario_id=scenario_id)
                    except Exception as exc:
                        with self.engine.begin() as c:
                            self.clear_plan(c,'P'+week.strftime('%Y%m%d'))
                            from .demo_reset import template_key
                            c.execute(text(f'DELETE FROM {quoted(self.active)}.settings WHERE key=:key'),{'key':template_key(seed,week)})
                            self.put(c,'today',old_today);self.put(c,'demo_scenario',old_scenario)
                        raise WorldPreparationError('The selected week could not be prepared. Your previous progress is unchanged.') from exc
            try:
                previous_schema=self.schema(previous)
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
                pid=self.build(week,report=not reset)
                from .demo_reset import capture_initial_plan
                capture_initial_plan(self.engine,self.active,seed=seed,week_start=week)
                with self.engine.begin() as c: self.snapshot(c,self.schema(seed))
            except Exception as exc:
                try:
                    with self.engine.begin() as c: self.restore(c,previous_schema)
                    self.invalidate()
                except Exception as restore_error: raise WorldPreparationError('The simulation could not be prepared or restored. Your previous snapshot is retained for recovery.') from restore_error
                raise WorldPreparationError('The simulation could not be prepared. Your previous progress has been restored; try again.') from exc
            return dict(id=pid,today=week_start,scenario_id=scenario_id)

manager=WorldManager()
