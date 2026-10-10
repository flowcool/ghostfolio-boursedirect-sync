import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {randomUUID} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {parse} from 'yaml';
import * as broker from '../core.mjs';
import {requestController} from '../request-controller.mjs';
import {nativeComposition} from '../lab/native-composition.mjs';
import {authorityForPolicy} from '../core.mjs';

const origin = 'http://127.0.0.1:48123';
function isolated(run) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'bd-native-policy-')), previous = process.env.HOME;
  process.env.HOME = home;
  return Promise.resolve().then(() => run(home)).finally(() => {
    if (previous === undefined) delete process.env.HOME; else process.env.HOME = previous;
    fs.rmSync(home, {recursive: true, force: true});
  });
}
function fixture() {
  const allocation = randomUUID(), authority = nativeComposition(origin, allocation);
  authority.enroll(); const handle = authority.acquirePrincipal();
  authority.startAttempt(handle, 100); authority.transition(handle, 'password_uncertain', 100);
  const source = {schema_version: 1, origin, roles: {password: {
    url: origin + '/allowed', method: 'POST', resource_type: 'XHR', evidence: 'invented native fixture'},
    app_method: null, otp: null}};
  const binding = {targetId: 'native-target', sessionId: 'native-session', pageEpoch: randomUUID(),
    frames: {'native-frame': {epoch: randomUUID(), role: 'source'}}};
  const permit = {phase: 'password_uncertain', page_epoch: binding.pageEpoch,
    frame_epoch: binding.frames['native-frame'].epoch, url: source.roles.password.url,
    method: 'POST', resource_type: 'XHR'};
  const nonce = authority.armPermit(handle, permit, 100, source);
  const action = {phase: permit.phase, pageEpoch: permit.page_epoch, frameEpoch: permit.frame_epoch,
    frameId: 'native-frame', url: permit.url, method: permit.method, resourceType: permit.resource_type, nonce};
  const event = {requestId: 'native-request', sessionId: binding.sessionId, frameId: action.frameId,
    pageEpoch: action.pageEpoch, frameEpoch: action.frameEpoch, resourceType: action.resourceType,
    request: {url: permit.url, method: permit.method}};
  const journal = () => parse(fs.readFileSync(path.join(handle.directory, 'journal.yaml'), 'utf8'));
  return {allocation, authority, handle, source, binding, permit, nonce, action, event, journal};
}

for (const value of ['https://www.boursedirect.fr', 'http://localhost:48123', 'http://127.0.0.2:48123',
  'http://127.0.0.1:0', 'http://127.0.0.1:80', 'http://127.0.0.1:65536', 'http://127.0.0.1:048123',
  'http://127.0.0.1:48123/', 'http://127.0.0.1:48123?x', 'http://user@127.0.0.1:48123',
  'http://2130706433:48123', 'http://127.0.0.1:48123#x']) {
  test('synthetic factory refuses noncanonical origin ' + value, () => {
    assert.throws(() => nativeComposition(value, randomUUID()), /SYNTHETIC_POLICY_INVALID/);
  });
}
test('forged internal policy cannot create authority', () => {
  assert.throws(() => authorityForPolicy({kind: 'synthetic-cdp-v1', origin, allocation: randomUUID()}), /SOURCE_POLICY_INVALID/);
});
test('native permit and controller consume same unchanged loopback metadata exactly once', () => isolated(async () => {
  const f = fixture(); let dispatch = 0;
  const controller = f.authority.controller(f.handle, {binding: f.binding, source: f.source,
    continueRequest: id => {
      assert.equal(id, f.event.requestId);
      assert.equal(f.journal().attempts[f.handle.attempt].permit.consumed, true);
      dispatch++;
    }, cancelAuth: () => {}, stop: () => true, now: () => 101});
  controller.arm(f.action);
  const status = await controller.paused(f.event);
  assert.equal(status.continued, 1); assert.equal(status.online_ready, false); assert.equal(dispatch, 1);
  assert.equal(f.journal().attempts[f.handle.attempt].permit.url, f.event.request.url);
  await assert.rejects(controller.paused({...f.event, requestId: 'second-native-request'}), /REQUEST_REJECTED/);
  assert.equal(dispatch, 1); f.authority.releasePrincipal(f.handle);
}));
test('nested source and frame mutation cannot replace native authorization after construction', () => isolated(async () => {
  const f = fixture(); let dispatch = 0;
  const controller = f.authority.controller(f.handle, {binding: f.binding, source: f.source,
    reads: [{role: 'source', url: origin + '/document', method: 'GET', resourceType: 'Document'}],
    continueRequest: () => {dispatch++;}, cancelAuth: () => {}, stop: () => true, now: () => 101});
  f.source.roles.password.url = origin + '/forbidden'; f.binding.frames['native-frame'].epoch = randomUUID();
  controller.arm(f.action); await controller.paused(f.event); assert.equal(dispatch, 1);
  f.authority.releasePrincipal(f.handle);
}));
test('default broker source, read controller and command cannot enable loopback policy', () => isolated(() => {
  const f = fixture();
  assert.throws(() => broker.validateSourceContract(f.source), /SOURCE_CONTRACT_INVALID/);
  assert.throws(() => broker.brokerUrl(origin + '/allowed'), /BROKER_URL_INVALID/);
  assert.throws(() => broker.command(JSON.stringify({action: 'login', origin})), /COMMAND_INVALID/);
  const source = {schema_version: 1, origin: broker.ORIGIN, roles: {password: null, app_method: null, otp: null}};
  assert.throws(() => requestController({binding: f.binding, source,
    reads: [{role: 'source', url: origin + '/document', method: 'GET', resourceType: 'Document'}],
    consume: () => true, continueRequest: () => {}, cancelAuth: () => {}, stop: () => true, now: () => 101}), /REQUEST_CONFIG_INVALID/);
  f.authority.releasePrincipal(f.handle);
}));
test('copied broker and lab journals refuse opposite readers without schema migration', () => isolated(() => {
  const f = fixture(); broker.enroll('SYNTHETIC'); const bh = broker.acquirePrincipal('SYNTHETIC');
  const bfile = path.join(bh.directory, 'journal.yaml'), lfile = path.join(f.handle.directory, 'journal.yaml');
  const original = fs.readFileSync(bfile), lab = fs.readFileSync(lfile);
  assert.equal(parse(original.toString()).schema_version, 1);
  assert.equal(f.journal().schema_version, 2); assert.equal(f.journal().allocation_id, f.allocation);
  assert.throws(() => broker.validateJournal(f.journal(), f.handle.principal));
  assert.throws(() => f.authority.validateJournal(parse(original.toString()), bh.principal));
  fs.writeFileSync(bfile, lab); assert.throws(() => broker.startAttempt(bh, 101));
  fs.writeFileSync(lfile, original); assert.throws(() => f.authority.consumePermit(f.handle, {...f.permit, nonce: f.nonce, redirect: false}, 101));
  fs.writeFileSync(bfile, original); fs.writeFileSync(lfile, lab);
  assert.deepEqual(fs.readFileSync(bfile), original);
  broker.releasePrincipal(bh); f.authority.releasePrincipal(f.handle);
}));
test('foreign, copied and broker handles cannot mutate or release lab authority', () => isolated(() => {
  const f = fixture(), same = nativeComposition(origin, f.allocation);
  broker.enroll('SYNTHETIC'); const bh = broker.acquirePrincipal('SYNTHETIC');
  for (const handle of [{...f.handle}, bh, {}]) {
    assert.throws(() => f.authority.startAttempt(handle, 102), /AUTH_HANDLE_CLOSED/);
    assert.throws(() => f.authority.releasePrincipal(handle), /AUTH_HANDLE_CLOSED/);
    assert.throws(() => f.authority.controller(handle, {}), /AUTH_HANDLE_CLOSED/);
  }
  assert.throws(() => same.releasePrincipal(f.handle), /AUTH_HANDLE_CLOSED/);
  assert.throws(() => broker.releasePrincipal(f.handle), /AUTH_HANDLE_CLOSED/);
  assert.throws(() => {f.handle.directory = bh.directory;}, TypeError);
  assert.equal(fs.existsSync(f.handle.lock), true);
  broker.releasePrincipal(bh); f.authority.releasePrincipal(f.handle);
}));
test('wrong origin or allocation cannot reopen retained journal', () => isolated(() => {
  const f = fixture(); f.authority.releasePrincipal(f.handle);
  for (const authority of [nativeComposition('http://127.0.0.1:48124', f.allocation), nativeComposition(origin, randomUUID())]) {
    assert.throws(() => authority.acquirePrincipal(), /AUTH_STATE_INVALID/);
    assert.throws(() => authority.enroll(), /AUTH_ALREADY_ENROLLED/);
  }
  assert.throws(() => f.authority.enroll('real-login'), /LOGIN_IDENTITY_INVALID/);
}));
for (const failure of ['none', 'fsync', 'continuation']) {
  test('native composition ' + failure + ' retains uncertainty in a fresh isolated process', () => isolated(async home => {
    const f = fixture(); let dispatch = 0;
    const controller = f.authority.controller(f.handle, {binding: f.binding, source: f.source,
      continueRequest: () => {dispatch++; if (failure === 'continuation') throw new Error('invented secret');},
      cancelAuth: () => {}, stop: () => true, now: () => 101});
    controller.arm(f.action);
    const fsync = fs.fsyncSync;
    if (failure === 'fsync') fs.fsyncSync = () => {throw new Error('invented private path');};
    try {
      if (failure === 'none') await controller.paused(f.event);
      else await assert.rejects(controller.paused(f.event), /REQUEST_REJECTED/);
    } finally {fs.fsyncSync = fsync; f.authority.releasePrincipal(f.handle);}
    assert.equal(dispatch, failure === 'fsync' ? 0 : 1);
    fs.writeFileSync(path.join(home, 'native-restart.json'), JSON.stringify({origin, allocation: f.allocation}), {mode: 0o600});
    const result = spawnSync(process.execPath, ['--import', path.resolve('tests/no-network.mjs'), path.resolve('tests/principal-child.mjs')],
      {env: {HOME: home, PATH: '/usr/bin:/bin'}, encoding: 'utf8', timeout: 5000});
    assert.equal(result.status, 0, result.stderr); assert.match(result.stdout, /AUTH_PRINCIPAL_FENCED/);
  }));
}
test('lab composition refuses caller-selected consume and real-origin read tuples', () => isolated(() => {
  const f = fixture();
  assert.throws(() => f.authority.controller(f.handle, {consume: () => true}), /REQUEST_CONFIG_INVALID/);
  assert.throws(() => f.authority.controller(f.handle, {binding: f.binding, source: f.source,
    reads: [{role: 'source', url: broker.ORIGIN + '/document', method: 'GET', resourceType: 'Document'}],
    continueRequest: () => {}, cancelAuth: () => {}, stop: () => true, now: () => 101}), /REQUEST_CONFIG_INVALID/);
  f.authority.releasePrincipal(f.handle);
}));
