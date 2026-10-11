import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {sourceReadGate} from '../source-read-gate.mjs';
import {BROKER_POLICY} from '../internal/source-policy.mjs';
const origin = BROKER_POLICY.origin;
function request() {
  return {candidate: {role: 'two_factor_state', url: origin + '/hub/auth/two-factor/login/state/boursedirect',
    method: 'GET', resourceType: 'XHR', sourceSha256: 'c'.repeat(64)},
  event: {sessionId: 'session', frameId: 'frame', requestId: 'read', resourceType: 'XHR',
    request: {url: origin + '/hub/auth/two-factor/login/state/boursedirect', method: 'GET'}}, expected: {}, grant: 'state-1'};
}
function fixture(overrides = {}) {
  const calls = [];
  const gate = sourceReadGate(BROKER_POLICY, {binding: {targetId: 'page', sessionId: 'session', pageEpoch: randomUUID(),
    frames: {frame: {epoch: randomUUID(), role: 'source'}}},
    retain: value => {calls.push(['retain', value]); return true;},
    consume: value => {calls.push(['consume', value]); return true;},
    continueRequest: id => {calls.push(['continue', id]);}, stop: () => {calls.push(['stop']); return true;}, ...overrides});
  return {gate, calls};
}
test('source read metadata is retained then one grant consumed before native continuation', async () => {
  const f = fixture(); assert.equal(await f.gate.paused(request()), true);
  assert.deepEqual(f.calls.map(row => row[0]), ['retain', 'consume', 'continue']);
  assert.equal(f.calls[0][1].dispatch_authority, false);
  const duplicate = request(); duplicate.event.requestId = 'other';
  await assert.rejects(f.gate.paused(duplicate), /SOURCE_READ_GATE_REFUSED/);
  assert.equal(f.calls.filter(row => row[0] === 'continue').length, 1);
});
for (const [name, mutate] of [
  ['redirect', value => {value.event.redirectedRequestId = 'prior';}],
  ['foreign frame', value => {value.event.frameId = 'other';}],
  ['unlisted source read', value => {value.candidate.url += '/other'; value.event.request.url = value.candidate.url;}],
  ['unexpected payload', value => {value.event.request.postData = 'SYNTHETIC';}],
]) test(`read refuses ${name} before evidence or grant`, async () => {
  const f = fixture(), value = request(); mutate(value);
  await assert.rejects(f.gate.paused(value), /SOURCE_READ_GATE_REFUSED/);
  assert.deepEqual(f.calls.map(row => row[0]), ['stop']);
});
test('failed grant fsync cannot dispatch a retained read', async () => {
  const f = fixture({consume: () => {throw new Error('SYNTHETIC_FSYNC');}});
  await assert.rejects(f.gate.paused(request()), /SOURCE_READ_GATE_REFUSED/);
  assert.deepEqual(f.calls.map(row => row[0]), ['retain', 'stop']);
});
test('fencing while evidence is held prevents consuming or continuing', async () => {
  let entered, release;
  const started = new Promise(resolve => {entered = resolve;}), held = new Promise(resolve => {release = resolve;});
  const f = fixture({retain: () => {entered(); return held;}});
  const pending = f.gate.paused(request()); await started; await f.gate.abort(); release(true);
  await assert.rejects(pending, /SOURCE_READ_GATE_REFUSED/);
  assert.deepEqual(f.calls.map(row => row[0]), ['stop']);
});
