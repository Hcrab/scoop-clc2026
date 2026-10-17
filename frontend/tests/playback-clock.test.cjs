const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const {test} = require('node:test');
const ts = require('typescript');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

const loaded = new Map(), dashboardProps = [];
function load(name) {
  if (name === 'Dashboard') return {Dashboard: props => { dashboardProps.push(props); return null; }};
  const base = path.join(__dirname, '..', 'src', name);
  const file = fs.existsSync(base) ? base : ['.ts', '.tsx'].map(ext => base + ext).find(fs.existsSync);
  if (file.endsWith('.css')) return {};
  if (loaded.has(file)) return loaded.get(file).exports;
  const mod = new Module(file, module);
  mod.filename = file; mod.paths = Module._nodeModulePaths(path.dirname(file)); loaded.set(file, mod);
  const normal = mod.require.bind(mod);
  mod.require = id => id.startsWith('./') ? load(id.slice(2)) : normal(id);
  mod._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX}}).outputText, file);
  return mod.exports;
}
const {playbackPosition, playbackDayMs, DEFAULT_PLAYBACK_SPEED, PLAYBACK_SPEEDS} = load('playbackClock');
const {emptyReplay, PlayWeek} = load('Play');
const origin = {day: 0, minute: 0};
const dates = Array.from({length: 14}, (_, day) => `2026-08-${String(day + 1).padStart(2, '0')}`);
const result = {days: 14, dates, events: [
  {id: 'arrival', date: dates[2], minute: 760, time: '12:40', kind: 'arrival', tone: 'good', text: 'Strawberry delivery arrived.'},
  {id: 'stockout', date: dates[4], minute: 910, time: '15:10', kind: 'stockout', tone: 'bad', text: 'Strawberry ran out.'},
]};
function render(position, speed, extra = {}) {
  return renderToStaticMarkup(React.createElement(PlayWeek, {
    detail: {plan: {week_start: dates[0]}}, products: [], path: '/test',
    replay: {...emptyReplay('plan', 'orders'), result, ...position, speed, running: !position.complete, ...extra},
    setReplay: () => {}, onSeeResults: () => {},
  }));
}

test('new replays default to 2× with the required native clock rates', () => {
  assert.equal(DEFAULT_PLAYBACK_SPEED, 2);
  assert.equal(emptyReplay().speed, 2);
  assert.deepEqual(PLAYBACK_SPEEDS.map(playbackDayMs), [2000, 1000, 500]);
  for (const speed of PLAYBACK_SPEEDS) {
    assert.deepEqual(playbackPosition(origin, playbackDayMs(speed), 14, speed), {day: 1, minute: 0, complete: false});
    assert.deepEqual(playbackPosition(origin, 0, 14, speed), {...origin, complete: false});
  }
  assert.deepEqual(playbackPosition(origin, 2000, 14), {day: 1, minute: 0, complete: false});
});

test('every ten-minute frame has identical dashboard time, events and captions at all speeds', () => {
  // Check the complete precomputed two-week timeline, including exact event boundaries.
  for (let tick = 0; tick < 14 * 144; tick++) {
    const expected = {day: Math.floor(tick / 144), minute: tick % 144 * 10, complete: tick === 14 * 144 - 1};
    for (const speed of PLAYBACK_SPEEDS) {
      const elapsed = (tick + 0.01) * playbackDayMs(speed) / 144;
      assert.deepEqual(playbackPosition(origin, elapsed, 14, speed), expected);
    }
  }
  for (const [day, minute] of [[2, 750], [2, 760], [4, 900], [4, 910]]) {
    const frames = PLAYBACK_SPEEDS.map(speed => {
      const tick = day * 144 + minute / 10;
      const position = playbackPosition(origin, (tick + 0.01) * playbackDayMs(speed) / 144, 14, speed);
      const html = render(position, speed);
      assert.equal(dashboardProps.at(-1).result, result);
      assert.equal(dashboardProps.at(-1).day, day);
      assert.equal(dashboardProps.at(-1).minute, minute);
      assert.equal(html.includes('Strawberry delivery arrived.'), day > 2 || minute >= 760);
      assert.equal(html.includes('Strawberry ran out.'), day === 4 && minute >= 910);
      return html.slice(html.indexOf('<div class="play-body">'));
    });
    assert.equal(frames[0], frames[1]); assert.equal(frames[1], frames[2]);
  }
});

test('speed switches reanchor without jumping, including midnight and final frame', () => {
  let cursor = playbackPosition(origin, 1988, 14, 2);
  assert.deepEqual(cursor, {day: 0, minute: 1430, complete: false});
  for (const speed of [4, 8, 2]) {
    assert.deepEqual(playbackPosition(cursor, 0, 14, speed), cursor);
    cursor = playbackPosition(cursor, playbackDayMs(speed), 14, speed);
  }
  assert.deepEqual(cursor, {day: 3, minute: 1430, complete: false});
  // Resuming uses the paused cursor as the anchor; time spent paused is excluded.
  assert.deepEqual(playbackPosition(cursor, 0, 14, 8), cursor);
  assert.deepEqual(playbackPosition(cursor, 500, 14, 8), {day: 4, minute: 1430, complete: false});
  for (const speed of PLAYBACK_SPEEDS) {
    assert.deepEqual(playbackPosition({day: 13, minute: 1420}, 10000, 14, speed), {day: 13, minute: 1430, complete: true});
  }
});

test('native control exposes all three speeds and keeps pause, resume and Results flow', () => {
  for (const speed of PLAYBACK_SPEEDS) {
    const html = render(origin, speed);
    assert.match(html, /class="segmented play-speed" role="group" aria-label="Playback speed"/);
    for (const value of PLAYBACK_SPEEDS) assert.ok(html.includes(`aria-pressed="${value === speed}">${value}×</button>`));
    assert.match(html, />Pause<\/button>/);
  }
  assert.match(render(origin, 4, {running: false}), />Resume<\/button>/);
  const completed = playbackPosition(origin, 28000, 14, 2);
  const final = render(completed, 8, {unlocked: true});
  assert.match(final, />Replay<\/button>/); assert.match(final, />See results<\/button>/);
  assert.doesNotMatch(final, /<button[^>]*disabled/);
});
