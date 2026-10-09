import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import * as core from '../core.mjs';
import {requestController, REQUEST_LIMITS} from '../request-controller.mjs';

function fixture(overrides = {}) {
  const source = {schema_version: 1, origin: core.ORIGIN, roles: {
    password: {url: core.ORIGIN + '/invented-auth', method: 'POST', resource_type: 'XHR', evidence: 'synthetic only'},
    app_method: null, otp: null,
  }};
  const binding = {targetId: 'owned-page', sessionId: 'owned-session', pageEpoch: randomUUID(),
    frames: {'root-frame': {epoch: randomUUID(), role: 'view'}, 'child-frame': {epoch: randomUUID(), role: 'asset'}}};
  const actions = [];
  const read = {role: 'view', url: core.ORIGIN + '/invented-document', method: 'GET', resourceType: 'Document'};
  const options = {binding, source, reads: [read], now: () => 101,
    consume: () => {actions.push('consumed'); return true;},
    continueRequest: id => {actions.push('continued:' + id);},
    cancelAuth: (id, response) => {actions.push(['cancel', id, response]);},
    stop: () => {actions.push('stopped'); return true;}, ...overrides};
  const policy = requestController(options);
  const action = {phase: 'password_uncertain', nonce: randomUUID(), pageEpoch: binding.pageEpoch,
    frameEpoch: binding.frames['root-frame'].epoch, frameId: 'root-frame',
    url: source.roles.password.url, method: 'POST', resourceType: 'XHR'};
  const event = (id = 'a', auth = true) => ({requestId: id, sessionId: binding.sessionId,
    frameId: 'root-frame', pageEpoch: binding.pageEpoch, frameEpoch: binding.frames['root-frame'].epoch,
    resourceType: auth ? 'XHR' : 'Document', request: {url: auth ? action.url : read.url, method: auth ? 'POST' : 'GET'}});
  return {policy, options, binding, source, action, event, actions, read};
}
const deferred = () => {
  let resolve;
  const promise = new Promise(done => {resolve = done;});
  return {promise, resolve};
};

test('one exact native auth request consumes durably before continuation, with disabled readiness', async () => {
  const f = fixture(); f.policy.arm(f.action);
  assert.deepEqual(await f.policy.paused(f.event()), {continued: 1, online_ready: false, browser_proven: false, import_ready: false});
  assert.deepEqual(f.actions, ['consumed', 'continued:a']);
});
test('exact read tuples need no auth permit and remain tied to the owning frame role', async () => {
  const f = fixture(); await f.policy.paused(f.event('read', false));
  assert.deepEqual(f.actions, ['continued:read']);
  const wrong = f.event('foreign-role', false); wrong.frameId = 'child-frame'; wrong.frameEpoch = f.binding.frames['child-frame'].epoch;
  await assert.rejects(f.policy.paused(wrong), /REQUEST_REJECTED/);
  assert.deepEqual(f.actions, ['continued:read', 'stopped']);
});

for (const [name, change] of [
  ['popup session', e => {e.sessionId = 'popup';}],
  ['unknown frame', e => {e.frameId = 'foreign';}],
  ['old page epoch', e => {e.pageEpoch = randomUUID();}],
  ['old frame epoch', e => {e.frameEpoch = randomUUID();}],
  ['resource-type normalization', e => {e.resourceType = 'Fetch';}],
  ['wrong method', e => {e.request.method = 'GET';}],
  ['uncharacterized same-origin path', e => {e.request.url = core.ORIGIN + '/other';}],
  ['foreign origin', e => {e.request.url = 'https://foreign.invalid/';}],
  ['307 auth redirect', e => {e.redirectedRequestId = 'previous307';}],
  ['308 auth redirect', e => {e.redirectedRequestId = 'previous308';}],
  ['empty redirect metadata', e => {e.redirectedRequestId = undefined;}],
  ['secret-bearing raw request', e => {e.request.postData = 'PRIVATE_SYNTHETIC_SENTINEL';}],
  ['unsupported worker type', e => {e.resourceType = 'Other';}],
]) test(`${name} cannot consume or continue`, async () => {
  const f = fixture(); f.policy.arm(f.action); const value = f.event(); change(value);
  await assert.rejects(f.policy.paused(value), /^Error: REQUEST_REJECTED$/);
  assert.deepEqual(f.actions, ['stopped']); assert.equal(f.policy.status().fenced, true);
});
test('GET redirects and duplicate read IDs fence without another continuation', async () => {
  for (const duplicate of [false, true]) {
    const f = fixture(), value = f.event('read', false);
    if (duplicate) await f.policy.paused(value); else value.redirectedRequestId = 'prior';
    await assert.rejects(f.policy.paused(value), /REQUEST_REJECTED/);
    assert.deepEqual(f.actions, duplicate ? ['continued:read', 'stopped'] : ['stopped']);
  }
});
test('second simultaneous auth fences a held first consumption before either can continue', async () => {
  const gate = deferred(), entered = deferred(); let consumed = 0, continued = 0;
  const f = fixture({consume: () => {consumed++; entered.resolve(); return gate.promise;}, continueRequest: () => {continued++;}});
  f.policy.arm(f.action); const first = f.policy.paused(f.event('first'));
  await entered.promise;
  const second = f.policy.paused(f.event('second'));
  const fencedAtIngress = f.policy.status().fenced;
  const settling = Promise.allSettled([first, second]);
  gate.resolve(true); const outcomes = await settling;
  assert.equal(fencedAtIngress, true);
  assert.deepEqual(outcomes.map(x => x.status), ['rejected', 'rejected']);
  assert.equal(consumed, 1); assert.equal(continued, 0); assert.deepEqual(f.actions, ['stopped']);
});
test('HTTP challenge fences at ingress while CancelAuth acknowledgement is held', async () => {
  const consumeGate = deferred(), entered = deferred(), cancelGate = deferred(); let continued = 0, stopped = 0;
  let f, fencedWhenCancelling, cancellation;
  f = fixture({consume: () => {entered.resolve(); return consumeGate.promise;},
    continueRequest: () => {continued++;}, stop: () => {stopped++; return true;},
    cancelAuth: (id, response) => {
      fencedWhenCancelling = f.policy.status().fenced; cancellation = {id, response}; return cancelGate.promise;
    }});
  f.policy.arm(f.action); const requestOutcome = Promise.allSettled([f.policy.paused(f.event())]);
  await entered.promise;
  const challengeOutcome = Promise.allSettled([f.policy.authRequired({sessionId: f.binding.sessionId, requestId: 'challenge'})]);
  const fencedAtIngress = f.policy.status().fenced;
  consumeGate.resolve(true); const requests = await requestOutcome;
  const stoppedBeforeCancelAcknowledgement = stopped;
  cancelGate.resolve(); const challenges = await challengeOutcome;
  assert.equal(fencedWhenCancelling, true); assert.equal(fencedAtIngress, true);
  assert.deepEqual(cancellation, {id: 'challenge', response: {response: 'CancelAuth'}});
  assert.equal(requests[0].status, 'rejected'); assert.equal(challenges[0].status, 'rejected');
  assert.equal(stoppedBeforeCancelAcknowledgement, 1); assert.equal(continued, 0);
});
test('failed or timed-out HTTP cancellation still stops and never supplies credentials/default', async () => {
  for (const hang of [false, true]) {
    let stopped = 0;
    const f = fixture({limits: {...REQUEST_LIMITS, callbackMs: 10}, stop: () => {stopped++; return true;},
      cancelAuth: (_id, response) => {assert.deepEqual(response, {response: 'CancelAuth'});
        if (hang) return new Promise(() => {}); throw new Error('PRIVATE_SYNTHETIC_SENTINEL');}});
    await assert.rejects(f.policy.authRequired({sessionId: f.binding.sessionId, requestId: 'challenge'}), /^Error: REQUEST_AUTH_REJECTED$/);
    assert.equal(stopped, 1);
  }
});
test('foreign HTTP challenge never emits a CDP command to the foreign session', async () => {
  const f = fixture(); await assert.rejects(f.policy.authRequired({sessionId: 'foreign', requestId: 'c'}), /REQUEST_AUTH_REJECTED/);
  assert.deepEqual(f.actions, ['stopped']);
});
test('duplicate HTTP challenge never retries cancellation', async () => {
  const f = fixture(), challenge = {sessionId: f.binding.sessionId, requestId: 'c'};
  await assert.rejects(f.policy.authRequired(challenge), /REQUEST_AUTH_REJECTED/);
  await assert.rejects(f.policy.authRequired(challenge), /REQUEST_AUTH_REJECTED/);
  assert.deepEqual(f.actions, [['cancel', 'c', {response: 'CancelAuth'}], 'stopped']);
});
test('abort crosses held read continuation and prohibits queued auth consumption', async () => {
  const held = deferred(), entered = deferred(); let consumed = 0;
  const f = fixture({continueRequest: () => {entered.resolve(); return held.promise;}, consume: () => {consumed++; return true;}});
  const readRejected = assert.rejects(f.policy.paused(f.event('read', false)), /REQUEST_REJECTED/);
  await entered.promise; f.policy.arm(f.action);
  const authRejected = assert.rejects(f.policy.paused(f.event('auth')), /REQUEST_REJECTED/);
  await f.policy.abort(); held.resolve(); await Promise.all([readRejected, authRejected]);
  assert.equal(consumed, 0); assert.deepEqual(f.actions, ['stopped']);
});
test('queue overflow fences a held callback, and total IDs never recycle', async () => {
  const entered = deferred(), held = deferred();
  const f = fixture({limits: {...REQUEST_LIMITS, queue: 1}, continueRequest: () => {entered.resolve(); return held.promise;}});
  const first = assert.rejects(f.policy.paused(f.event('a', false)), /REQUEST_REJECTED/);
  await entered.promise; const overflow = f.policy.paused(f.event('b', false));
  assert.equal(f.policy.status().fenced, true); await assert.rejects(overflow, /REQUEST_REJECTED/);
  held.resolve(); await first;
  const g = fixture({limits: {...REQUEST_LIMITS, requests: 1}});
  await g.policy.paused(g.event('a', false)); await assert.rejects(g.policy.paused(g.event('b', false)), /REQUEST_REJECTED/);
  assert.deepEqual(g.actions, ['continued:a', 'stopped']);
});
test('queued metadata and initial contracts are detached from caller mutation', async () => {
  const entered = deferred(), held = deferred(), calls = [];
  const f = fixture({continueRequest: id => {calls.push(id); if (id === 'first') {entered.resolve(); return held.promise;}}});
  const first = f.policy.paused(f.event('first', false)); await entered.promise;
  const value = f.event('second', false), second = f.policy.paused(value);
  value.requestId = 'changed'; value.request.url = 'https://foreign.invalid/';
  f.read.url = 'https://foreign.invalid/'; f.binding.frames['root-frame'].epoch = randomUUID();
  held.resolve(); await Promise.all([first, second]); assert.deepEqual(calls, ['first', 'second']);
});
for (const kind of ['false', 'error', 'timeout']) test(`durable consumption ${kind} never continues and is redacted`, async () => {
  const f = fixture({limits: {...REQUEST_LIMITS, callbackMs: 10}, consume: () => {
    if (kind === 'false') return false;
    if (kind === 'timeout') return new Promise(() => {});
    throw new Error('PRIVATE_SYNTHETIC_SENTINEL');
  }}); f.policy.arm(f.action);
  await assert.rejects(f.policy.paused(f.event()), /^Error: REQUEST_REJECTED$/); assert.deepEqual(f.actions, ['stopped']);
});
test('invalid clock, continuation failure and unproved stop never permit retry or cleanup claims', async () => {
  for (const override of [{now: () => NaN}, {continueRequest: () => {throw new Error('PRIVATE_SYNTHETIC_SENTINEL');}}]) {
    const f = fixture(override); f.policy.arm(f.action);
    await assert.rejects(f.policy.paused(f.event()), /^Error: REQUEST_REJECTED$/);
    await assert.rejects(f.policy.paused(f.event('retry')), /^Error: REQUEST_REJECTED$/);
    assert.equal(f.actions.filter(x => x === 'consumed').length <= 1, true);
  }
  for (const stop of [() => false, () => {throw new Error('PRIVATE_SYNTHETIC_SENTINEL');}, () => new Promise(() => {})]) {
    const f = fixture({stop, limits: {...REQUEST_LIMITS, callbackMs: 10}});
    await assert.rejects(f.policy.abort(), /^Error: REQUEST_STOP_UNVERIFIED$/);
    assert.equal(f.policy.status().fenced, true);
  }
});
test('missing source roles, unsupported app-method, wrong nonce and repeated arm refuse action', async () => {
  for (const change of [f => {f.action.phase = 'password_accepted';}, f => {f.action.nonce = 'invalid';},
    f => {f.action.frameEpoch = randomUUID();}]) {
    const f = fixture(); change(f); assert.throws(() => f.policy.arm(f.action), /REQUEST_ACTION_REJECTED/); await f.policy.abort();
  }
  const f = fixture(); f.policy.arm(f.action); assert.throws(() => f.policy.arm(f.action), /REQUEST_ACTION_REJECTED/); await f.policy.abort();
  const source = {schema_version: 1, origin: core.ORIGIN, roles: {password: null, app_method: null, otp: null}};
  const g = fixture({source}); assert.throws(() => g.policy.arm(g.action), /REQUEST_ACTION_REJECTED/); await g.policy.abort();
});
test('configuration rejects wildcard/unbounded/read-auth overlap before any callback', () => {
  const f = fixture();
  for (const change of [o => {o.reads = [{...f.read, url: 'https://foreign.invalid/'}];},
    o => {o.reads = [{...f.read, url: f.source.roles.password.url}];},
    o => {o.reads = [f.read, f.read];}, o => {o.limits = {...REQUEST_LIMITS, queue: 65};},
    o => {o.binding = {...f.binding, frames: {}};}]) {
    const options = {...f.options}; change(options); assert.throws(() => requestController(options), /^Error: REQUEST_CONFIG_INVALID$/);
  }
  assert.deepEqual(f.actions, []);
});

function otpFixture(overrides = {}) {
  const source = {schema_version: 1, origin: core.ORIGIN, roles: {password: null, app_method: null,
    otp: {url: core.ORIGIN + '/invented-auth', method: 'POST', resource_type: 'XHR', evidence: 'synthetic OTP'}}};
  let time = 121;
  const f = fixture({source, now: () => time, ...overrides});
  f.action = {...f.action, phase: 'otp_uncertain', otp: {issuedAt: 120, step: 4}};
  return {...f, source, time: value => {time = value;}};
}
test('valid one-step OTP applies the same timing metadata for either credential mode', async () => {
  const f = otpFixture(); f.policy.arm(f.action);
  // Request contains no code/provider/seed metadata; both modes share this guard.
  await f.policy.paused(f.event()); assert.deepEqual(f.actions, ['consumed', 'continued:a']);
  await assert.rejects(f.policy.paused(f.event('retry')), /REQUEST_REJECTED/);
});
for (const [name, time] of [['near expiry', 146], ['rollover', 150], ['age', 141], ['reversed clock', 120]]) {
  test(`OTP ${name} after arm cannot consume`, async () => {
    const f = otpFixture(); f.policy.arm(f.action); f.time(time);
    await assert.rejects(f.policy.paused(f.event()), /REQUEST_REJECTED/);
    assert.deepEqual(f.actions, ['stopped']);
  });
}
test('malformed or absent OTP timing, wrong step and future issue refuse arm', async () => {
  for (const change of [a => {delete a.otp;}, a => {a.otp.step = 5;}, a => {a.otp.issuedAt = 123;},
    a => {a.otp.issuedAt = NaN;}, a => {a.otp.extra = true;}]) {
    const f = otpFixture(); change(f.action);
    assert.throws(() => f.policy.arm(f.action), /REQUEST_ACTION_REJECTED/); await f.policy.abort();
  }
});
test('OTP expiration across held durable fsync preserves consumed uncertainty without continuation', async () => {
  for (const expired of [146, 150, 120]) {
    const entered = deferred(), held = deferred(); let consumed = 0, continued = 0;
    const f = otpFixture({consume: () => {consumed++; entered.resolve(); return held.promise;}, continueRequest: () => {continued++;}});
    f.policy.arm(f.action); const outcome = Promise.allSettled([f.policy.paused(f.event())]);
    await entered.promise; f.time(expired); held.resolve(true);
    assert.equal((await outcome)[0].status, 'rejected'); assert.equal(consumed, 1); assert.equal(continued, 0);
    assert.deepEqual(f.actions, ['stopped']);
  }
});
test('OTP clock checked again inside continuation callback after scheduling', async () => {
  let sampled = 0, continued = 0;
  const f = otpFixture({now: () => (++sampled < 5 ? 121 : 150), continueRequest: () => {continued++;}});
  f.policy.arm(f.action); await assert.rejects(f.policy.paused(f.event()), /REQUEST_REJECTED/);
  assert.equal(sampled, 5); assert.equal(continued, 0); assert.deepEqual(f.actions, ['consumed', 'stopped']);
});
test('OTP action timing is cloned before caller mutation', async () => {
  const f = otpFixture(); f.policy.arm(f.action); f.action.otp.step = 999; f.action.otp.issuedAt = 99999;
  await f.policy.paused(f.event()); assert.deepEqual(f.actions, ['consumed', 'continued:a']);
});

async function isolatedAuthority(run) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'bd-request-policy-'));
  const homedir = os.homedir; os.homedir = () => directory;
  try {await run(directory);}
  finally {os.homedir = homedir; fs.rmSync(directory, {recursive: true, force: true});}
}
for (const failure of ['none', 'fsync', 'continuation']) test(`real synthetic durable authority: ${failure}, one-use and fresh-process fence`, async () => isolatedAuthority(async directory => {
  const f = fixture(); core.enroll('SYNTHETIC'); const handle = core.acquirePrincipal('SYNTHETIC');
  core.startAttempt(handle, 100); core.transition(handle, 'password_uncertain', 100);
  const action = {...f.action};
  action.nonce = core.armPermit(handle, {phase: action.phase, page_epoch: action.pageEpoch, frame_epoch: action.frameEpoch,
    url: action.url, method: action.method, resource_type: action.resourceType}, 100, f.source);
  let continued = 0;
  const policy = requestController({...f.options, consume: (request, time) => core.consumePermit(handle, request, time),
    continueRequest: () => {continued++; if (failure === 'continuation') throw new Error('PRIVATE_SYNTHETIC_SENTINEL');}});
  policy.arm(action);
  const fsync = fs.fsyncSync;
  try {
    if (failure === 'fsync') fs.fsyncSync = () => {throw new Error('PRIVATE_SYNTHETIC_SENTINEL');};
    if (failure === 'none') await policy.paused(f.event());
    else await assert.rejects(policy.paused(f.event()), /^Error: REQUEST_REJECTED$/);
  } finally {fs.fsyncSync = fsync; core.releasePrincipal(handle);}
  assert.equal(continued, failure === 'fsync' ? 0 : 1);
  assert.equal(fs.statSync(path.join(handle.directory, 'journal.yaml')).mode & 0o777, 0o600);
  const child = spawnSync(process.execPath, ['--import', path.resolve('tests/no-network.mjs'), path.resolve('tests/principal-child.mjs')],
    {env: {HOME: directory, PATH: '/usr/bin:/bin'}, encoding: 'utf8', timeout: 5000});
  assert.equal(child.status, 0); assert.equal(child.stdout.trim(), 'AUTH_PRINCIPAL_FENCED');
}));
test('real OTP permit consumed before expiry remains uncertain in a fresh process', async () => isolatedAuthority(async directory => {
  const f = otpFixture(), source = structuredClone(f.source);
  source.roles.password = {...source.roles.otp, url: core.ORIGIN + '/invented-password'};
  core.enroll('SYNTHETIC'); const handle = core.acquirePrincipal('SYNTHETIC');
  core.startAttempt(handle, 100); core.transition(handle, 'password_uncertain', 100);
  const password = {phase: 'password_uncertain', page_epoch: f.action.pageEpoch, frame_epoch: f.action.frameEpoch,
    url: source.roles.password.url, method: 'POST', resource_type: 'XHR'};
  const n = core.armPermit(handle, password, 100, source); core.consumePermit(handle, {...password, nonce: n, redirect: false}, 101);
  core.transition(handle, 'password_accepted', 102); core.transition(handle, 'otp_uncertain', 120);
  const otp = {phase: 'otp_uncertain', page_epoch: f.action.pageEpoch, frame_epoch: f.action.frameEpoch,
    url: source.roles.otp.url, method: 'POST', resource_type: 'XHR'};
  f.action.nonce = core.armPermit(handle, otp, 120, source);
  let continued = 0;
  const policy = requestController({...f.options, source,
    consume: (request, time) => {const result = core.consumePermit(handle, request, time); f.time(150); return result;},
    continueRequest: () => {continued++;}});
  policy.arm(f.action);
  try {await assert.rejects(policy.paused(f.event()), /REQUEST_REJECTED/);}
  finally {core.releasePrincipal(handle);}
  assert.equal(continued, 0);
  const child = spawnSync(process.execPath, ['--import', path.resolve('tests/no-network.mjs'), path.resolve('tests/principal-child.mjs')],
    {env: {HOME: directory, PATH: '/usr/bin:/bin'}, encoding: 'utf8', timeout: 5000});
  assert.equal(child.status, 0); assert.equal(child.stdout.trim(), 'AUTH_PRINCIPAL_FENCED');
}));
