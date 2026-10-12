import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {parse} from 'yaml';
import {brokerAuthenticationComposition} from '../source-authentication-gate.mjs';

const roles = {
  password_uncertain: ['password_submit', '/hub/auth/login'],
  otp_uncertain: ['otp_submit', '/hub/auth/two-factor/validate-totp'],
  finalization_uncertain: ['password_finalize', '/hub/auth/login-2fa'],
};
function request(phase) {
  const [role, endpoint] = roles[phase];
  const expected = phase === 'otp_uncertain' ? {code: '123456', branding: 'boursedirect'}
    : {login: 'SYNTHETIC', password: 'SYNTHETIC_PASSWORD', branding: 'boursedirect'};
  const body = phase === 'otp_uncertain' ? {...expected, trusted_device: false}
    : {username: expected.login, password: expected.password, branding: expected.branding, redirect: null};
  const url = 'https://www.boursedirect.fr' + endpoint;
  return {phase, candidate: {role, url, method: 'POST', resourceType: 'XHR', sourceSha256: 'c'.repeat(64)},
    event: {requestId: phase, sessionId: 'session', frameId: 'frame', resourceType: 'XHR',
      request: {url, method: 'POST', headers: {'Content-Type': 'application/json'}, postData: JSON.stringify(body)}},
    expected, ...(phase === 'otp_uncertain' ? {otp: {issuedAt: 100, step: 3}} : {})};
}
async function isolated(run, overrides = {}) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'bd-source-gate-'));
  const homedir = os.homedir; os.homedir = () => directory;
  const authority = brokerAuthenticationComposition(); authority.enroll('SYNTHETIC');
  const handle = authority.acquirePrincipal('SYNTHETIC');
  const retained = [], continued = [], stopped = [];
  const journal = () => parse(fs.readFileSync(path.join(handle.directory, 'journal.yaml'), 'utf8')).attempts[handle.attempt];
  try {
    authority.startAttempt(handle, 100, 'post-2fa-finalization');
    authority.transition(handle, 'password_uncertain', 100);
    const source = {schema_version: 2, origin: 'https://www.boursedirect.fr', roles: {
      password: null, app_method: null, otp: null, finalize: null}};
    const options = {handle, source, binding: {targetId: 'page', sessionId: 'session', pageEpoch: randomUUID(),
      frames: {frame: {epoch: randomUUID(), role: 'source'}}}, now: () => 100,
      retain: observation => {retained.push(observation); assert.equal(journal().permit, null); return true;},
      continueRequest: id => {assert.equal(journal().permit.consumed, true); continued.push(id);},
      cancelAuth: () => {throw new Error('SYNTHETIC_UNEXPECTED_CALLBACK');},
      stop: () => {stopped.push(true); return true;}, ...overrides};
    const gate = authority.gate(options);
    await run({authority, handle, gate, options, journal, retained, continued, stopped});
  } finally {authority.releasePrincipal(handle); os.homedir = homedir; fs.rmSync(directory, {recursive: true, force: true});}
}
test('native inspection and retention precede three distinct consumed requests without declaring success', () => isolated(async f => {
  for (const phase of Object.keys(roles)) {
    if (phase === 'otp_uncertain') {
      f.authority.transition(f.handle, 'password_accepted', 100);
      f.authority.confirmLocalAppMethod(f.handle, f.options.source, {...f.journal().initial_auth_epochs,
        source_sha256: 'c'.repeat(64), session_id: 'session', frame_id: 'frame',
        method: 'TOTP', trusted_device: false, native_dom_checked: true}, 100);
      f.authority.transition(f.handle, phase, 100);
    } else if (phase === 'finalization_uncertain') {
      f.authority.transition(f.handle, 'otp_accepted', 100); f.authority.transition(f.handle, phase, 100);
    }
    assert.equal((await f.gate.paused(request(phase))).continued, 1);
    assert.equal(f.journal().state, phase);
  }
  assert.equal(f.retained.length, 3); assert.equal(f.continued.length, 3); assert.equal(f.stopped.length, 0);
  const raw = JSON.stringify(f.retained);
  for (const secret of ['SYNTHETIC_PASSWORD', 'SYNTHETIC', '123456', 'postData', 'headers']) assert.equal(raw.includes(secret), false);
  assert.equal(f.gate.status().online_ready, false);
}));
for (const [name, mutate] of [
  ['wrong principal', value => {value.expected.login = 'OTHER'; value.event.request.postData = value.event.request.postData.replace('SYNTHETIC', 'OTHER');}],
  ['wrong password', value => {value.expected.password = 'OTHER';}],
  ['unknown endpoint', value => {value.candidate.url += '/other'; value.event.request.url = value.candidate.url;}],
  ['wrong purpose', value => {value.candidate.role = 'password_finalize';}],
  ['redirect', value => {value.event.redirectedRequestId = undefined;}],
  ['foreign frame', value => {value.event.frameId = 'other';}],
  ['content type', value => {value.event.request.headers['Content-Type'] = 'text/plain';}],
]) test(`qualification refuses ${name} before retention or continuation`, () => isolated(async f => {
  const value = request('password_uncertain'); mutate(value);
  await assert.rejects(f.gate.paused(value), /^Error: SOURCE_AUTHENTICATION_GATE_REFUSED$/);
  assert.deepEqual(f.retained, []); assert.deepEqual(f.continued, []); assert.equal(f.stopped.length, 1);
  assert.equal(f.journal().permit, null);
}));
test('private evidence publication failure cannot create a permit', () => isolated(async f => {
  await assert.rejects(f.gate.paused(request('password_uncertain')), /^Error: SOURCE_AUTHENTICATION_GATE_REFUSED$/);
  assert.equal(f.journal().permit, null);
}, {retain: () => {throw new Error('PRIVATE_SYNTHETIC_DETAILS');}}));
test('durable consumption fsync failure cannot continue an inspected request', () => isolated(async f => {
  const sync = fs.fsyncSync; let count = 0;
  fs.fsyncSync = fd => {if (++count === 3) throw new Error('PRIVATE_SYNTHETIC_DETAILS'); return sync(fd);};
  try {await assert.rejects(f.gate.paused(request('password_uncertain')), /^Error: SOURCE_AUTHENTICATION_GATE_REFUSED$/);}
  finally {fs.fsyncSync = sync;}
  assert.equal(f.continued.length, 0); assert.equal(f.retained.length, 1); assert.equal(f.journal().permit.consumed, false);
}));
test('duplicate ingress fences a held evidence publication before either request can continue', () => isolated(async f => {
  let entered, release;
  const held = new Promise(resolve => {release = resolve;}), started = new Promise(resolve => {entered = resolve;});
  const gate = f.authority.gate({...f.options, retain: () => {entered(); return held;}});
  const first = gate.paused(request('password_uncertain'));
  await started;
  const value = request('password_uncertain'); value.event.requestId = 'duplicate';
  const second = gate.paused(value), settling = Promise.allSettled([first, second]);
  assert.equal(gate.status().fenced, true); release(true);
  assert.deepEqual((await settling).map(row => row.status), ['rejected', 'rejected']);
  assert.equal(f.continued.length, 0); assert.equal(f.journal().permit, null); assert.equal(f.stopped.length, 1);
}));
test('caller mutation during retention cannot alter the qualified role or queued native metadata', () => isolated(async f => {
  let entered, release;
  const held = new Promise(resolve => {release = resolve;}), started = new Promise(resolve => {entered = resolve;});
  const gate = f.authority.gate({...f.options, retain: () => {entered(); return held;}});
  const value = request('password_uncertain'), pending = gate.paused(value);
  await started; value.candidate.url += '/other'; value.event.requestId = 'other'; value.event.request.url += '/other';
  release(true); await pending;
  assert.deepEqual(f.continued, ['password_uncertain']); assert.equal(f.journal().permit.url, request('password_uncertain').candidate.url);
}));
test('a foreign composition cannot adopt the original authority handle', () => isolated(async f => {
  assert.throws(() => brokerAuthenticationComposition().gate(f.options), /AUTH_HANDLE_CLOSED/);
}));
test('HTTP authentication cancels once and fences a held qualification before any permit', () => isolated(async f => {
  let entered, release;
  const held = new Promise(resolve => {release = resolve;}), started = new Promise(resolve => {entered = resolve;});
  const cancelled = [];
  const gate = f.authority.gate({...f.options, retain: () => {entered(); return held;},
    cancelAuth: (id, response) => {cancelled.push({id, response});}});
  const pending = gate.paused(request('password_uncertain'));
  await started;
  const challenge = {sessionId: 'session', requestId: 'challenge'};
  const refused = gate.authRequired(challenge), settling = Promise.allSettled([pending, refused]);
  assert.equal(gate.status().fenced, true); release(true);
  assert.deepEqual((await settling).map(row => row.status), ['rejected', 'rejected']);
  await assert.rejects(gate.authRequired(challenge), /REQUEST_AUTH_REJECTED/);
  assert.deepEqual(cancelled, [{id: 'challenge', response: {response: 'CancelAuth'}}]);
  assert.equal(f.continued.length, 0); assert.equal(f.journal().permit, null); assert.equal(f.stopped.length, 1);
}));
