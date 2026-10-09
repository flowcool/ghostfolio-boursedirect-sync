import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {capabilityPipe, PIPE_LIMITS} from '../capability-pipe.mjs';
import {orderingExperiment} from '../capability-ordering.mjs';
import {requestExperiment, FIXTURE} from '../capability-policy.mjs';
import * as core from '../core.mjs';
import {bootstrapExperiment} from '../capability-bootstrap.mjs';

test('pipe timeout fences guard initialization before any resume or pipe closure', async () => {
  const writes = [], lifecycle = [], timers = new Map(); let id = 0, stopped;
  const pipe = capabilityPipe({write: raw => {writes.push(JSON.parse(raw.subarray(0, -1)));},
    onEvent: () => {}, fence: () => {stopped = ordering.abort();},
    schedule: (fn, ms) => {const key = ++id; timers.set(key, {fn, ms}); return key;}, cancel: key => timers.delete(key)});
  pipe.registerSession(FIXTURE.session);
  const ordering = orderingExperiment({send: pipe.send, installRoutes: () => {pipe.armEvents();},
    stopOwned: async () => {lifecycle.push('exit'); return true;}, closePipe: () => {lifecycle.push('close');}});
  const run = ordering.initialize(FIXTURE.session, true), rejection = assert.rejects(run, /INITIALIZATION_FAILED/);
  await Promise.resolve();
  const timeout = [...timers.values()].find(v => v.ms === PIPE_LIMITS.commandMs); assert.ok(timeout);
  timeout.fn(); assert.equal(ordering.fenced(), true);
  await rejection; await stopped;
  assert.deepEqual(writes.map(v => v.method), ['Target.setAutoAttach']);
  assert.deepEqual(lifecycle, ['exit', 'close']);
});

test('startup and ordered guards compose through actual NUL frame parsing', async () => {
  const commands = [], lifecycle = [];
  let bootstrap, ordering;
  const reply = value => pipe.receive(Buffer.from(JSON.stringify(value) + '\0'));
  const pipe = capabilityPipe({write: bytes => {
    const command = JSON.parse(bytes.subarray(0, -1)); commands.push(command);
    let result = {};
    if (command.method === 'Browser.getVersion') result = {product: 'Chrome/148.0.7778.97'};
    if (command.method === 'Target.createTarget') {
      reply({method: 'Target.attachedToTarget', params: {sessionId: FIXTURE.session,
        waitingForDebugger: true, targetInfo: {type: 'page', targetId: FIXTURE.target, url: 'about:blank'}}});
      result = {targetId: FIXTURE.target};
    }
    reply({id: command.id, result, ...(command.sessionId ? {sessionId: command.sessionId} : {})});
  }, onEvent: value => bootstrap.event(value), fence: () => {void ordering.abort();}});
  ordering = orderingExperiment({send: pipe.send, installRoutes: () => lifecycle.push('routes'),
    stopOwned: async () => {lifecycle.push('exit'); return true;}, closePipe: () => lifecycle.push('close')});
  bootstrap = bootstrapExperiment({send: pipe.send, registerSession: pipe.registerSession,
    initialize: ordering.initialize, stop: ordering.abort});
  pipe.armEvents();
  assert.deepEqual(await bootstrap.start(), {targetId: FIXTURE.target, sessionId: FIXTURE.session, browser_proven: false});
  assert.equal(commands.at(-1).method, 'Runtime.runIfWaitingForDebugger');
  assert.equal(commands.at(-1).sessionId, FIXTURE.session);
  assert.equal(commands.find(v => v.method === 'Fetch.enable').params.handleAuthRequests, true);
  assert.deepEqual(lifecycle, ['routes']);
  await bootstrap.abort(); pipe.lost(); assert.deepEqual(lifecycle, ['routes', 'exit', 'close']);
});

async function isolated(run) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'bd-capability-auth-'));
  const originalHomedir = os.homedir; os.homedir = () => directory;
  try { await run(directory); }
  finally {
    os.homedir = originalHomedir;
    fs.rmSync(directory, {recursive: true, force: true});
  }
}
function authority() {
  // Synthetic metadata required by the existing offline core; no request is sent.
  const source = {schema_version: 1, origin: core.ORIGIN, roles: {
    password: {url: core.ORIGIN + '/synthetic-capability-password', method: 'POST', resource_type: 'Document', evidence: 'invented offline fixture'},
    app_method: null, otp: null,
  }};
  core.enroll('SYNTHETIC-CAPABILITY'); const handle = core.acquirePrincipal('SYNTHETIC-CAPABILITY');
  core.startAttempt(handle, 100); core.transition(handle, 'password_uncertain', 100);
  const permit = {phase: 'password_uncertain', page_epoch: randomUUID(), frame_epoch: randomUUID(),
    url: source.roles.password.url, method: 'POST', resource_type: 'Document'};
  const nonce = core.armPermit(handle, permit, 100, source);
  return {handle, request: {...permit, nonce, redirect: false}};
}
const paused = id => ({requestId: id, sessionId: FIXTURE.session, frameId: FIXTURE.frame,
  pageEpoch: 1, frameEpoch: 1, resourceType: 'Document', request: {url: FIXTURE.auth, method: 'POST'}});

test('concurrent fixture requests compose with real private durable core consumption', async () => isolated(async () => {
  const {handle, request} = authority(); let continued = 0;
  const experiment = requestExperiment({consume: () => core.consumePermit(handle, request, 101),
    continueRequest: () => {continued++;}, stop: () => {}}); experiment.arm();
  try {
    const outcomes = await Promise.allSettled([experiment.paused(paused('a')), experiment.paused(paused('b'))]);
    assert.equal(outcomes.filter(v => v.status === 'fulfilled').length, 1); assert.equal(continued, 1);
    assert.throws(() => core.consumePermit(handle, request, 101), /AUTH_REQUEST_REJECTED/);
    const file = path.join(handle.directory, 'journal.yaml');
    assert.equal(fs.statSync(file).mode & 0o777, 0o600);
    assert.equal(fs.statSync(handle.directory).mode & 0o777, 0o700);
  } finally {core.releasePrincipal(handle);}
}));

test('real durable-core fsync failure prevents trusted continuation', async () => isolated(async () => {
  const {handle, request} = authority(); let continued = 0;
  const real = fs.fsyncSync;
  const experiment = requestExperiment({consume: () => core.consumePermit(handle, request, 101),
    continueRequest: () => {continued++;}, stop: () => {}}); experiment.arm();
  fs.fsyncSync = () => {throw new Error('synthetic fsync failure');};
  try {await assert.rejects(experiment.paused(paused('a')), /CAPABILITY_REQUEST_REJECTED/);}
  finally {fs.fsyncSync = real; core.releasePrincipal(handle);}
  assert.equal(continued, 0); assert.equal(experiment.fenced(), true);
}));

test('continuation failure plus controller restart cannot reset durable uncertainty', async () => isolated(async () => {
  const {handle, request} = authority(); let continued = 0;
  const experiment = requestExperiment({consume: () => core.consumePermit(handle, request, 101),
    continueRequest: () => {continued++; throw new Error('synthetic crash');}, stop: () => {}}); experiment.arm();
  try {await assert.rejects(experiment.paused(paused('a')), /CAPABILITY_REQUEST_REJECTED/);}
  finally {core.releasePrincipal(handle);}
  const restarted = core.acquirePrincipal('SYNTHETIC-CAPABILITY');
  try {assert.throws(() => core.startAttempt(restarted, 102), /AUTH_PRINCIPAL_FENCED/);}
  finally {core.releasePrincipal(restarted);}
  assert.equal(continued, 1);
}));
