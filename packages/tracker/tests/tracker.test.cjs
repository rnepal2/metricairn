const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');
const source = readFileSync(__dirname + '/../dist/metricairn.js', 'utf8');
function boot(options = {}) {
  const location = new URL('https://app.test/pricing?utm_source=google&email=secret@example.com#token');
  const handlers = {}; const timers = []; const calls = []; const storage = new Map();
  const window = { addEventListener: (name, fn) => { handlers[name] = fn; } };
  const context = {
    window, location, URL, URLSearchParams, TextEncoder, crypto: webcrypto,
    navigator: { userAgent: 'iPhone Mobile Mac OS Safari', ...options.navigator },
    document: { currentScript: { dataset: { api: 'https://analytics.test/api/v1/ingest', key: 'alw_test', ...options.dataset } }, referrer: 'https://google.test/search?q=secret', readyState: 'complete' },
    localStorage: { getItem: key => { if (options.blockStorage) throw new Error('denied'); return storage.get(key) || null; }, setItem: (key, value) => { if (options.blockStorage) throw new Error('denied'); storage.set(key, value); } },
    history: { pushState() {}, replaceState() {} },
    setTimeout: fn => { timers.push(fn); return timers.length; },
    fetch: async (url, init) => { calls.push({ url, init, body: JSON.parse(init.body) }); if (options.networkError) throw new Error("offline"); return { status: options.status || 200 }; },
  };
  vm.createContext(context); vm.runInContext(source, context);
  const flush = () => { while (timers.length) timers.shift()(); };
  return { context, window, location, handlers, calls, flush };
}
test('strips arbitrary query strings and fragments; keeps landing attribution', () => {
  const tracker = boot(); tracker.location.href = 'https://app.test/checkout?token=secret#hash';
  tracker.window.metricairn.revenue(49); tracker.flush();
  const events = tracker.calls.flatMap(call => call.body.events);
  assert.equal(events.length, 2);
  assert.equal(events[1].url, 'https://app.test/checkout?utm_source=google');
  assert.equal(events[0].referrer, 'https://google.test/search');
  assert.equal(events[0].os, 'iOS');
  assert.ok(events[1].event_id);
});
test('storage denial preserves identity within a page', () => {
  const tracker = boot({ blockStorage: true }); tracker.window.metricairn.event('signup'); tracker.flush();
  const events = tracker.calls[0].body.events;
  assert.equal(events[0].visitor_id, events[1].visitor_id);
  assert.equal(events[0].session_id, events[1].session_id);
});
test('honors DNT and global privacy control before installing navigation hooks', () => {
  for (const navigator of [{ doNotTrack: '1' }, { globalPrivacyControl: true }]) {
    const tracker = boot({ navigator }); tracker.window.metricairn.event('signup'); tracker.flush();
    assert.equal(tracker.calls.length, 0); assert.equal(tracker.window.metricairn.context(), null);
  }
});
test('duplicate installation does not double track', () => {
  const tracker = boot(); vm.runInContext(source, tracker.context); tracker.flush();
  assert.equal(tracker.calls[0].body.events.length, 1);
});
test('SPA replaceState and pushState track only changed paths', () => {
  const tracker = boot(); tracker.location.pathname = '/signup'; tracker.context.history.replaceState();
  tracker.context.history.pushState(); tracker.flush();
  assert.equal(tracker.calls[0].body.events.length, 2);
});
test('large bursts stay bounded and each request fits keepalive budget', () => {
  const tracker = boot();
  for (let i = 0; i < 600; i++) tracker.window.metricairn.event('click', { label: 'x'.repeat(7000) });
  tracker.flush();
  const events = tracker.calls.flatMap(call => call.body.events);
  assert.equal(events.length, 100);
  for (const call of tracker.calls) {
    assert.ok(Buffer.byteLength(call.init.body) <= 48 * 1024); assert.ok(call.body.events.length <= 20);
  }
});
test('rejects invalid revenue and oversize properties without breaking the host', () => {
  const tracker = boot(); tracker.window.metricairn.revenue(NaN); tracker.window.metricairn.revenue(-1);
  tracker.window.metricairn.event('signup', { value: 'x'.repeat(9000) }); tracker.flush();
  assert.equal(tracker.calls[0].body.events.length, 1);
});

test('explicit disable skips storage, tracking and context', () => {
  const tracker = boot({ dataset: { disabled: 'true' }, blockStorage: true });
  tracker.window.metricairn.event('signup'); tracker.flush();
  assert.equal(tracker.calls.length, 0); assert.equal(tracker.window.metricairn.context(), null);
});
test('transient failures retry bounded identical event IDs; permanent failures stop', async () => {
  for (const options of [{ status: 429 }, { status: 503 }, { networkError: true }, { status: 403 }]) {
    const tracker = boot(options);
    for (let i = 0; i < 10; i++) { tracker.flush(); await new Promise(resolve => setImmediate(resolve)); }
    assert.equal(tracker.calls.length, options.status === 403 ? 1 : 3);
    assert.ok(tracker.calls.every(call => call.body.events[0].event_id === tracker.calls[0].body.events[0].event_id));
  }
});
