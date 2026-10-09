import test from 'node:test';
import assert from 'node:assert/strict';
import {requestExperiment, captureExperiment, FIXTURE} from '../capability-policy.mjs';
const event = () => ({requestId: 'r1', sessionId: FIXTURE.session, frameId: FIXTURE.frame,
  pageEpoch: 1, frameEpoch: 1, resourceType: 'Document', request: {url: FIXTURE.auth, method: 'POST'}});
function policy(overrides = {}) {
  const actions = [];
  const p = requestExperiment({consume: async () => {actions.push('durable-consumed'); return true;},
    continueRequest: async id => {actions.push('continue:' + id);},
    stop: async () => {actions.push('stop');}, ...overrides});
  p.arm(); return {p, actions};
}
test('one invented POST continues only after positive durable consumption', async () => {
  const {p, actions} = policy();
  assert.deepEqual(await p.paused(event()), {continued: 1, browser_proven: false});
  assert.deepEqual(actions, ['durable-consumed', 'continue:r1']);
});
test('two concurrently paused auth requests consume and continue at most once', async () => {
  const {p, actions} = policy();
  const results = await Promise.allSettled([p.paused(event()), p.paused({...event(), requestId: 'r2'})]);
  assert.equal(results[0].status, 'fulfilled'); assert.equal(results[1].status, 'rejected');
  assert.deepEqual(actions, ['durable-consumed', 'continue:r1', 'stop']); assert.equal(p.fenced(), true);
});
for (const [name, change] of [
  ['popup frame', e => {e.frameId = 'popup';}], ['worker session', e => {e.sessionId = 'worker';}],
  ['subresource', e => {e.resourceType = 'Script';}], ['stale page', e => {e.pageEpoch = 0;}],
  ['stale frame', e => {e.frameEpoch = 0;}], ['GET instead of POST', e => {e.request.method = 'GET';}],
  ['foreign URL', e => {e.request.url = 'https://foreign.invalid/';}],
  ['307 redirect replay', e => {e.redirectedRequestId = 'prior307';}],
  ['308 redirect replay', e => {e.redirectedRequestId = 'prior308';}],
]) test(`${name} never consumes or continues`, async () => {
  const {p, actions} = policy(); const value = event(); change(value);
  await assert.rejects(p.paused(value), /CAPABILITY_REQUEST_REJECTED/);
  assert.deepEqual(actions, ['stop']);
});
for (const kind of ['refused', 'throws']) test(`durable permit ${kind} never continues`, async () => {
  const {p, actions} = policy({consume: async () => {if (kind === 'throws') throw new Error('synthetic fsync failure'); return false;}});
  await assert.rejects(p.paused(event()), /CAPABILITY_REQUEST_REJECTED/);
  assert.deepEqual(actions, ['stop']);
});
test('lost continuation leaves one-shot fenced rather than replayable', async () => {
  let calls = 0;
  const {p} = policy({continueRequest: async () => {calls++; throw new Error('synthetic pipe loss');}});
  await assert.rejects(p.paused(event()), /CAPABILITY_REQUEST_REJECTED/);
  await assert.rejects(p.paused(event()), /CAPABILITY_REQUEST_REJECTED/); assert.equal(calls, 1);
});
test('abort during permit persistence prevents a later continuation', async () => {
  let release, entered;
  const gate = new Promise(ok => {release = ok;}), started = new Promise(ok => {entered = ok;});
  const {p, actions} = policy({consume: async () => {entered(); await gate; return true;}});
  const task = p.paused(event()), failure = assert.rejects(task, /CAPABILITY_REQUEST_REJECTED/);
  await started; await p.abort(); release(); await failure; assert.deepEqual(actions, ['stop']);
});

const ticket = () => ({target: FIXTURE.target, frame: FIXTURE.frame, account: FIXTURE.account,
  day: FIXTURE.day, url: FIXTURE.document, pageEpoch: 1, frameEpoch: 1, role: 'statement'});
const requested = () => ({sessionId: FIXTURE.session, frameId: FIXTURE.frame, requestId: 'request',
  loaderId: 'fresh-loader', type: 'Document', request: {url: FIXTURE.document, method: 'GET'}});
const committed = () => ({sessionId: FIXTURE.session, frame: {id: FIXTURE.frame, loaderId: 'fresh-loader', url: FIXTURE.document}});
const loaded = () => ({sessionId: FIXTURE.session, frameId: FIXTURE.frame, loaderId: 'fresh-loader', name: 'load'});
const identity = () => ({target: FIXTURE.target, account: FIXTURE.account, day: FIXTURE.day, pageEpoch: 1, frameEpoch: 1});
test('capture requires exact request commit and loader-bound load, once', () => {
  const p = captureExperiment(); p.arm(ticket()); p.request(requested()); p.commit(committed()); p.load(loaded());
  assert.deepEqual(p.capture(identity()), {requestId: 'request', loaderId: 'fresh-loader', browser_proven: false});
  assert.throws(() => p.capture(identity()), /CAPABILITY_CAPTURE_REJECTED/);
});
for (const [name, change] of [
  ['wrong account', v => {v.account = 'other';}], ['wrong day', v => {v.day = '2026-09-18';}],
  ['unsupported operation', v => {v.role = 'orders';}], ['wrong target', v => {v.target = 'popup';}],
]) test(`capture ticket ${name} refuses before navigation`, () => {
  const p = captureExperiment(), value = ticket(); change(value);
  assert.throws(() => p.arm(value), /CAPABILITY_CAPTURE_REJECTED/);
});
test('DOM-only load event cannot substitute for request and frame commit', () => {
  const p = captureExperiment(); p.arm(ticket());
  assert.throws(() => p.load(loaded()), /CAPABILITY_CAPTURE_REJECTED/);
});
test('older loader cannot authorize capture of a new navigation', () => {
  const p = captureExperiment(); p.arm(ticket()); p.request(requested()); p.commit(committed());
  assert.throws(() => p.load({...loaded(), loaderId: 'old-loader'}), /CAPABILITY_CAPTURE_REJECTED/);
});
test('redirected document request cannot establish capture freshness', () => {
  const p = captureExperiment(); p.arm(ticket());
  assert.throws(() => p.request({...requested(), redirectResponse: {status: 307}}), /CAPABILITY_CAPTURE_REJECTED/);
});
test('changed account after load refuses serialization', () => {
  const p = captureExperiment(); p.arm(ticket()); p.request(requested()); p.commit(committed()); p.load(loaded());
  assert.throws(() => p.capture({...identity(), account: 'different'}), /CAPABILITY_CAPTURE_REJECTED/);
});
