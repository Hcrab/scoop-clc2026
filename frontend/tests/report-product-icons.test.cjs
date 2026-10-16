const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { test } = require('node:test');
const ts = require('typescript');

const src = path.join(__dirname, '..', 'src');
const loaded = new Map();
function load(name) {
  const file = path.join(src, name);
  if (loaded.has(file)) return loaded.get(file).exports;
  const source = fs.readFileSync(file, 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  const mod = new Module(file, module);
  mod.filename = file;
  mod.paths = Module._nodeModulePaths(path.dirname(file));
  loaded.set(file, mod);
  const normalRequire = mod.require.bind(mod);
  mod.require = id => {
    if (id.endsWith('.css')) return {};
    if (!id.startsWith('./')) return normalRequire(id);
    const relative = id.slice(2);
    return load(relative + (fs.existsSync(path.join(src, relative + '.tsx')) ? '.tsx' : '.ts'));
  };
  mod._compile(compiled, file);
  return mod.exports;
}

const { reportProductRepresentatives, decorateReportProductIcons } = load('nativeReportCards.tsx');
const { productVisuals } = load('productVisuals.ts');
const detail = (queries = [], units = [], cards = []) => ({
  plan: { summary: { cohort_model: { units } } }, findings: [],
  review: { queries }, cohort_cards: cards,
});
const query = (id, skus, extra = {}) => ({ id, name: 'query_group', result: { scope: { skus, districts: ['East'] }, ...extra } });
const unit = (sku, recent_A, recent_E, district = 'East') => ({ sku, district, recent_A, recent_E });

test('exact cohort scope uses the same native representative, independent of report titles', () => {
  const card = { id: 'leaf', name: 'Unrelated title', effect_pct: 5, skus: ['IC006', 'IC062'], districts: ['East'], representative_sku: 'IC062' };
  const data = detail([query('Q2', ['IC062', 'IC006'])], [], [card]);
  const icons = reportProductRepresentatives(data);
  assert.equal(icons.get('Q2'), 'IC062');
  assert.equal(icons.get('Q-cohort-leaf'), 'IC062');
});

test('model units aggregate only matching districts and rank signed excess, then catalog product name', () => {
  const skus = ['IC001', 'IC002', 'IC003'];
  const data = detail([query('Q2', skus)], [
    unit('IC001', 0, 100), unit('IC002', 12, 10), unit('IC002', 13, 10),
    unit('IC003', 15, 10), unit('IC001', 1000, 0, 'West'),
  ]);
  const tied = ['IC002', 'IC003'].sort((a, b) => productVisuals[a].name.localeCompare(productVisuals[b].name));
  assert.equal(reportProductRepresentatives(data).get('Q2'), tied[0]);
  data.plan.summary.cohort_model.units.push(unit('IC003', 1, 0));
  assert.equal(reportProductRepresentatives(data).get('Q2'), 'IC003');
});

test('complete negative contributors rank greatest excess, while truncated negative evidence stays empty', () => {
  const contributors = [{ sku: 'IC001', excess_units: -100 }, { sku: 'IC002', excess_units: -2 }];
  const complete = detail([query('Q2', ['IC001', 'IC002'], { sku_contributors: contributors })]);
  assert.equal(reportProductRepresentatives(complete).get('Q2'), 'IC002');
  const sparse = detail([query('Q2', ['IC001', 'IC002', 'IC003'], { sku_contributors: contributors })]);
  assert.equal(reportProductRepresentatives(sparse).has('Q2'), false);
  const positive = detail([query('Q2', ['IC001', 'IC002', 'IC003'], { sku_contributors: [{ sku: 'IC002', excess_units: 2 }] })]);
  assert.equal(reportProductRepresentatives(positive).get('Q2'), 'IC002');
});

test('empty, unmatched, nonfinite and unknown catalog products never create a representative', () => {
  const data = detail([
    query('empty', []), query('unknown', ['https://example.com/image']), query('missing', ['IC001']),
    query('nan', ['IC002'], { sku_contributors: [{ sku: 'IC002', excess_units: NaN }] }),
  ]);
  assert.equal(reportProductRepresentatives(data).size, 0);
});

test('finding icons use explicit catalog membership and district rather than the displayed name', () => {
  const data = detail([{ id: 'Q1', name: 'catalog_groups', result: { groups: [{ id: 'flavour:fruit', skus: ['IC001', 'IC002'] }] } }], [unit('IC001', 1, 0), unit('IC002', 5, 0)]);
  data.findings = [{ id: 'finding', tag_id: 'flavour:fruit', district: 'East', evidence: { display: 'Chocolate', checks: {}, related: {} } }];
  assert.equal(reportProductRepresentatives(data).get('finding'), 'IC002');
});

test('host decoration keeps the original expand trigger and renders only a 32px trusted local icon', () => {
  global.window = { location: { origin: 'http://localhost:8008' } };
  const trigger = { dataset: { trendId: 'Q2' }, before(anchor) { this.anchor = anchor; } };
  const card = { querySelector() { return trigger; } };
  const doc = {
    querySelectorAll() { return [card]; },
    createElement() { return { dataset: {}, append(...children) { this.children = children; } }; },
  };
  decorateReportProductIcons(doc, detail([query('Q2', ['IC062'])], [unit('IC062', 10, 0)]));
  const [icon, originalTrigger] = trigger.anchor.children;
  assert.equal(originalTrigger, trigger);
  assert.equal(icon.dataset.productSku, 'IC062');
  assert.match(icon.innerHTML, /width:32px;height:32px/);
  assert.match(icon.innerHTML, /src="http:\/\/localhost:8008\/products\/IC062.webp"/);
  assert.match(icon.innerHTML, /aria-hidden="true"/);
  assert.doesNotMatch(icon.innerHTML, /example\.com/);
  delete global.window;
});
