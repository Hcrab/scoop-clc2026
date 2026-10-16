const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { test, afterEach } = require('node:test');
const ts = require('typescript');

const modules = new Map();
function load(relative) {
  const file = path.resolve(__dirname, '../src', relative);
  if (modules.has(file)) return modules.get(file).exports;
  const mod = new Module(file, module);
  mod.filename = file; mod.paths = Module._nodeModulePaths(path.dirname(file));
  const normal = mod.require.bind(mod);
  mod.require = id => id.startsWith('.') ? load(path.relative(path.resolve(__dirname, '../src'), path.resolve(path.dirname(file), `${id}.ts`))) : normal(id);
  modules.set(file, mod);
  mod._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, file);
  return mod.exports;
}
const runtime = load('tour/runtime.ts');
const { api, assistantStream } = load('api.ts');
const originalFetch = global.fetch;
const originalWindow = global.window;
afterEach(() => { runtime.endTour(); global.fetch = originalFetch; global.window = originalWindow; });

const answer = reply => ({ reply, provider: 'gemini', model: 'recorded-model', usage: { input_tokens: 4 }, tool_trace: [], grounding: { passed: true, claims: [], evidence: {} }, snapshot_hash: 'recorded-hash' });
function fixture() {
  const snapshot = count => ({
    detail: { plan: { id: 'tour-plan', week_start: '2026-07-27', stage: 'execute', service_level: null, summary: { flow: { step: 'results', max_step: 'results' } } }, flow: { step: 'results', max_step: 'results', order_hash: `hash-${count}` }, orders: [{ sku: 'strawberry', final_cases: count, status: 'draft' }], messages: [], decisions: [] },
    cohorts: { cards: [{ id: 'strawberry', case_change: count }], method: {}, overrides: count === 10 ? [] : [{ id: count, type: 'trend', value: count }] },
    direction_preview: { service_level: null, cases: count, projected_peak_pallets: count / 2, capacity_pallets: 120 },
    order_summary: { groups: [{ id: 'strawberry', name: 'Strawberry', skus: ['strawberry'] }], capacity: { feasible: true, peak_pallets: count / 2 }, edited_skus: [] },
    dashboard: { widgets: [], options: [], facts_through: '2026-07-26' },
    simulation: { status: 'ready', order_hash: `hash-${count}`, result: { days: 14, summary: { scoop: { lost_units: count }, baseline: { lost_units: 40 } } } },
  });
  const branches = Object.fromEntries(['summer', 'growing', 'unchanged'].map((id, i) => {
    const count = [20, 30, 10][i], snap = snapshot(count);
    return [id, { id, context: id === 'unchanged' ? null : { cohort: 'strawberry', type: 'trend', value: count }, snapshot: snap, edit: id === 'unchanged' ? null : { edit_id: count, affected_orders: [{ sku: 'strawberry', before: 10, after: count }] }, before_cases: 10, after_cases: count, total_cases: count, peak: count / 2, capacity: 120, answer: answer(`Context ${id}`), moments: { heat_date: '2026-07-30', strawberry_arrival: null, stockout: null }, widgets: Object.fromEntries(['stock', 'space', 'cover'].map((widget, index) => [widget, { spec: { title: widget, scope: { kind: 'warehouse' }, metric: ['on_hand', 'pallets', 'days_cover'][index] }, dashboard: { ...snap.dashboard, widgets: [{ id: `${id}-${widget}`, value: count, title: widget }] }, edit: { edit_id: count + index, label: 'Widget added', affected_orders: [] } }])) }];
  }));
  return { version: 1, default_week: '2026-07-27', default_order_hash: 'source-hash', plan_id: 'tour-plan', meta: {}, common: { bootstrap: { today: '2026-07-27', plans: [snapshot(10).detail.plan] }, settings: { week_start: '2026-07-27' } }, base: snapshot(10), branches, questions: { why: answer('Why recorded'), heat: answer('Heat recorded') } };
}
const plan = '/plans/tour-plan';

test('all contexts and widgets run the native App flow without any network request or bundle mutation', async () => {
  const bundle = fixture(), before = structuredClone(bundle), requests = [];
  global.fetch = async (...args) => { requests.push(args); throw new Error('Unexpected network'); };
  for (const context of ['summer', 'growing', 'unchanged']) for (const widget of ['stock', 'space', 'cover']) {
    runtime.beginTour(bundle);
    const initial = await api(plan);
    assert.equal(initial.plan.stage, 'discover');
    assert.equal(initial.flow.max_step, 'report');
    assert.equal(initial.plan.summary.flow.step, 'report');
    await assert.rejects(api(`${plan}/flow`, 'PUT', { step: 'results' }), /preceding/);
    const branch = runtime.selectContext(context);
    const selected = await api(plan);
    assert.deepEqual(selected.orders, branch.snapshot.detail.orders);
    assert.deepEqual(await api(`${plan}/cohorts`), branch.snapshot.cohorts);
    assert.deepEqual(await api(`${plan}/overrides`), branch.snapshot.cohorts.overrides);
    assert.deepEqual(await api(`${plan}/direction-preview`, 'POST', { service_level: null }), branch.snapshot.direction_preview);
    assert.deepEqual(await api(`${plan}/order-summary`), branch.snapshot.order_summary);
    assert.equal((await api('/bootstrap')).plans[0].stage, 'discover');
    assert.deepEqual(await api(`${plan}/advance`, 'POST', {}), { stage: 'direction' });
    assert.equal((await api(plan)).flow.step, 'orders');
    assert.deepEqual(await api(`${plan}/approve-orders`, 'POST', {}), { stage: 'execute', capacity: branch.snapshot.order_summary.capacity });
    assert.equal((await api('/bootstrap')).plans[0].stage, 'execute');
    assert.equal((await api(plan)).orders[0].status, 'confirmed');
    runtime.selectWidget(widget);
    const watchDashboard = await api(`${plan}/dashboard`);
    assert.deepEqual(watchDashboard, branch.widgets[widget].dashboard);
    assert.equal((await api(`${plan}/flow`, 'PUT', { step: 'play' })).max_step, 'play');
    assert.deepEqual(await api(`${plan}/simulation`), branch.snapshot.simulation);
    assert.deepEqual(await api(`${plan}/dashboard`), watchDashboard);
    await assert.rejects(api(`${plan}/flow`, 'PUT', { step: 'results' }), /preceding/);
    assert.equal((await api(`${plan}/play-complete`, 'POST', {})).max_step, 'results');
    assert.equal((await api(`${plan}/flow`, 'PUT', { step: 'results' })).step, 'results');
    assert.deepEqual(await api(`${plan}/dashboard`), watchDashboard);
    assert.equal((await api(`${plan}/simulation`)).result.summary.scoop.lost_units, branch.after_cases);
    runtime.setTourView('play');
    assert.equal((await api(plan)).flow.max_step, 'results');
    // Every externally returned object is isolated, including the bundle accessor.
    selected.orders[0].final_cases = -1;
    branch.snapshot.simulation.result.days = -1;
    runtime.getTourBundle().base.detail.orders[0].final_cases = -1;
    runtime.getTourBranch().widgets[widget].dashboard.widgets[0].value = -1;
    watchDashboard.widgets[0].value = -1;
    assert.equal((await api(`${plan}/dashboard`)).widgets[0].value, before.branches[context].after_cases);
    runtime.endTour();
  }
  assert.deepEqual(requests, []);
  assert.deepEqual(bundle, before);
});

test('fixture adapter returns stored edit responses and rejects unsupported controls and routes', async () => {
  const bundle = fixture(); runtime.beginTour(bundle);
  global.fetch = async () => { throw new Error('Network fallback'); };
  assert.deepEqual(await api(`${plan}/overrides`, 'POST', bundle.branches.summer.context), bundle.branches.summer.edit);
  assert.equal(runtime.getTourBranch().id, 'summer');
  for (const [route, method, body] of [['/unknown', 'GET'], [plan + '/orders/bulk', 'POST', {}], [plan + '/goal', 'PUT', {}], [plan + '/direction-preview', 'POST', { service_level: .9 }], [plan + '/overrides', 'POST', { free: 'form' }], ['/plans/other', 'GET'], ['/plans', 'POST', {}]]) await assert.rejects(api(route, method, body));
  await api(`${plan}/advance`, 'POST', {});
  await api(`${plan}/approve-orders`, 'POST', {});
  assert.deepEqual(await api(`${plan}/dashboard`, 'POST', bundle.branches.summer.widgets.stock.spec), bundle.branches.summer.widgets.stock.edit);
  assert.throws(() => runtime.selectContext('growing'), /Report/);
  await assert.rejects(api(`${plan}/play-complete`, 'POST', {}), /Play/);
});

test('only genuine stored answers are served and assistant never falls back to HTTP', async () => {
  const bundle = fixture(); runtime.beginTour(bundle);
  global.fetch = async () => { throw new Error('Network fallback'); };
  assert.deepEqual(runtime.getRecordedQuestion('why'), bundle.questions.why);
  assert.deepEqual(await assistantStream(`${plan}/chat`, { message: 'Could this just be the heat?' }, () => {}), bundle.questions.heat);
  await assert.rejects(assistantStream(`${plan}/chat`, { message: 'Unrecorded free chat' }, () => {}), /recorded/);
  bundle.questions.why = null; runtime.beginTour(bundle);
  assert.throws(() => runtime.getRecordedQuestion('why'), /unavailable/);
});

test('loading uses two GETs and explicitly rejects a stale default order hash', async () => {
  const bundle = fixture(), requests = [];
  global.fetch = async (url, options) => { requests.push([url, options.method]); return { ok: true, json: async () => url === '/tour-bundle.json' ? bundle : { default_week: bundle.default_week, default_order_hash: bundle.default_order_hash, plan_id: bundle.plan_id } }; };
  assert.deepEqual(await runtime.loadTourBundle(), bundle);
  assert.deepEqual(requests, [['/tour-bundle.json', 'GET'], ['/api/tour/source', 'GET']]);
  global.fetch = async url => ({ ok: true, json: async () => url === '/tour-bundle.json' ? bundle : { default_week: bundle.default_week, default_order_hash: 'changed-source-hash', plan_id: bundle.plan_id } });
  await assert.rejects(runtime.loadTourBundle(), /stale/);
  assert.equal(runtime.isTourActive(), false);
});

test('refresh events fire for context, widget and view changes; ending fully restores live transport', async () => {
  const events = []; global.window = { dispatchEvent: event => events.push(event.type) };
  runtime.beginTour(fixture()); runtime.selectContext('unchanged');
  await api(`${plan}/advance`, 'POST', {}); await api(`${plan}/approve-orders`, 'POST', {});
  runtime.selectWidget('cover'); runtime.setTourView('play');
  assert.equal(events.length, 6); assert.ok(events.every(event => event === 'scoop:tour-refresh'));
  runtime.endTour(); assert.equal(runtime.getTourBundle(), null); assert.equal(runtime.getTourBranch(), null);
  const requests = [];
  global.fetch = async (url, options) => { requests.push([url, options]); return { ok: true, json: async () => ({ live: true }) }; };
  assert.deepEqual(await api('/normal', 'POST', { normal: true }), { live: true });
  assert.equal(requests[0][0], '/api/normal'); assert.equal(requests[0][1].method, 'POST');
  assert.equal(requests[0][1].body, '{"normal":true}');
});
