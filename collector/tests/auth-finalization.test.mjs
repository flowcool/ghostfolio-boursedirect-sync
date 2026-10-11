import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {parse} from 'yaml';
import * as core from '../core.mjs';
import {requestController} from '../request-controller.mjs';

const source = {schema_version: 2, origin: core.ORIGIN, roles: {
  password: {url: core.ORIGIN + '/synthetic-initial', method: 'POST', resource_type: 'XHR', evidence: 'synthetic'},
  app_method: null,
  otp: {url: core.ORIGIN + '/synthetic-code', method: 'POST', resource_type: 'XHR', evidence: 'synthetic'},
  finalize: {url: core.ORIGIN + '/synthetic-finalize', method: 'POST', resource_type: 'XHR', evidence: 'synthetic'},
}};
async function isolated(run) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'bd-finalization-'));
  const homedir = os.homedir; os.homedir = () => directory;
  core.enroll('SYNTHETIC'); const handle = core.acquirePrincipal('SYNTHETIC');
  try {await run(handle, directory);} finally {core.releasePrincipal(handle); os.homedir = homedir; fs.rmSync(directory, {recursive: true, force: true});}
}
function permit(phase) {
  const role = {password_uncertain: 'password', otp_uncertain: 'otp', finalization_uncertain: 'finalize'}[phase];
  return {phase, page_epoch: randomUUID(), frame_epoch: randomUUID(),
    ...Object.fromEntries(['url', 'method', 'resource_type'].map(key => [key, source.roles[role][key]]))};
}
function dispatch(handle, phase) {
  const value = permit(phase), nonce = core.armPermit(handle, value, 100, source);
  core.consumePermit(handle, {...value, nonce, redirect: false}, 100);
}
function prepare(handle) {
  core.startAttempt(handle, 100, 'post-2fa-finalization');
  core.transition(handle, 'password_uncertain', 100); dispatch(handle, 'password_uncertain');
  core.transition(handle, 'password_accepted', 100); core.transition(handle, 'otp_uncertain', 100);
}
test('post-2FA protocol needs three independently consumed permits before success', () => isolated(async handle => {
  prepare(handle);
  assert.throws(() => core.transition(handle, 'otp_accepted', 100), /AUTH_SUCCESS_WITHOUT_REQUEST/);
  dispatch(handle, 'otp_uncertain');
  assert.throws(() => core.transition(handle, 'authenticated', 100), /AUTH_TRANSITION_INVALID/);
  core.transition(handle, 'otp_accepted', 100);
  assert.throws(() => core.armPermit(handle, permit('finalization_uncertain'), 100, source), /AUTH_PERMIT_BLOCKED/);
  core.transition(handle, 'finalization_uncertain', 100);
  assert.throws(() => core.transition(handle, 'authenticated', 100), /AUTH_SUCCESS_WITHOUT_REQUEST/);
  dispatch(handle, 'finalization_uncertain'); core.transition(handle, 'authenticated', 100);
  core.transition(handle, 'closed_success', 100); core.startAttempt(handle, 101, 'post-2fa-finalization');
}));
test('protocol selection is persisted before credentials and cannot downgrade source contracts', () => isolated(async handle => {
  prepare(handle);
  const journal = parse(fs.readFileSync(path.join(handle.directory, 'journal.yaml'), 'utf8'));
  assert.equal(core.validateJournal(journal, handle.principal).attempts[handle.attempt].protocol, 'post-2fa-finalization');
  const legacy = structuredClone(source); legacy.schema_version = 1; delete legacy.roles.finalize;
  assert.throws(() => core.armPermit(handle, permit('otp_uncertain'), 100, legacy), /AUTH_SOURCE_ROLE_DISABLED/);
  const {url, method, resource_type} = source.roles.finalize;
  assert.equal(core.evaluateRequest(legacy, 'finalization_uncertain', {url, method, resource_type, redirect: false}), false);
}));
test('legacy attempts cannot acquire a finalization protocol through a later source change', () => isolated(async handle => {
  core.startAttempt(handle, 100); core.transition(handle, 'password_uncertain', 100);
  assert.throws(() => dispatch(handle, 'password_uncertain'), /AUTH_SOURCE_ROLE_DISABLED/);
  const legacy = structuredClone(source); legacy.schema_version = 1; delete legacy.roles.finalize;
  const value = permit('password_uncertain'), nonce = core.armPermit(handle, value, 100, legacy);
  core.consumePermit(handle, {...value, nonce, redirect: false}, 100);
  core.transition(handle, 'password_accepted', 100); core.transition(handle, 'otp_uncertain', 100);
  assert.throws(() => core.transition(handle, 'otp_accepted', 100), /AUTH_TRANSITION_INVALID/);
}));
for (const failure of ['none', 'fsync', 'continue']) test(`finalization controller ${failure} consumes once and fences a fresh process`, () => isolated(async (handle, directory) => {
  prepare(handle); dispatch(handle, 'otp_uncertain'); core.transition(handle, 'otp_accepted', 100);
  core.transition(handle, 'finalization_uncertain', 100);
  const value = permit('finalization_uncertain'), nonce = core.armPermit(handle, value, 100, source);
  let continued = 0;
  const controller = requestController({source, binding: {targetId: 'page', sessionId: 'session', pageEpoch: value.page_epoch,
    frames: {frame: {epoch: value.frame_epoch, role: 'source'}}}, now: () => 100,
    consume: (request, time) => core.consumePermit(handle, request, time),
    continueRequest: () => {continued++; if (failure === 'continue') throw new Error('PRIVATE_SENTINEL');},
    cancelAuth: () => {throw new Error();}, stop: () => true});
  controller.arm({phase: value.phase, nonce, pageEpoch: value.page_epoch, frameEpoch: value.frame_epoch,
    frameId: 'frame', url: value.url, method: value.method, resourceType: value.resource_type});
  const event = {requestId: 'request', sessionId: 'session', frameId: 'frame', pageEpoch: value.page_epoch,
    frameEpoch: value.frame_epoch, resourceType: value.resource_type, request: {url: value.url, method: value.method}};
  const sync = fs.fsyncSync;
  try {
    if (failure === 'fsync') fs.fsyncSync = () => {throw new Error('PRIVATE_SENTINEL');};
    if (failure === 'none') await controller.paused(event);
    else await assert.rejects(controller.paused(event), /^Error: REQUEST_REJECTED$/);
  } finally {fs.fsyncSync = sync;}
  assert.equal(continued, failure === 'fsync' ? 0 : 1);
  await assert.rejects(controller.paused({...event, requestId: 'duplicate'}), /REQUEST_REJECTED/);
  assert.equal(continued, failure === 'fsync' ? 0 : 1);
  core.releasePrincipal(handle);
  const child = spawnSync(process.execPath, ['--import', path.resolve('tests/no-network.mjs'), path.resolve('tests/principal-child.mjs')],
    {env: {HOME: directory, PATH: '/usr/bin:/bin'}, encoding: 'utf8', timeout: 5000});
  assert.equal(child.status, 0); assert.equal(child.stdout.trim(), 'AUTH_PRINCIPAL_FENCED');
}));
for (const state of ['otp_accepted', 'finalization_uncertain']) test(`interruption in ${state} keeps the principal fenced`, () => isolated(async (handle, directory) => {
  prepare(handle); dispatch(handle, 'otp_uncertain'); core.transition(handle, 'otp_accepted', 100);
  if (state === 'finalization_uncertain') core.transition(handle, state, 100);
  core.releasePrincipal(handle);
  const reopened = core.acquirePrincipal('SYNTHETIC');
  try {assert.throws(() => core.startAttempt(reopened, 101), /AUTH_PRINCIPAL_FENCED/);} finally {core.releasePrincipal(reopened);}
  const journal = parse(fs.readFileSync(path.join(handle.directory, 'journal.yaml'), 'utf8'));
  assert.equal(journal.attempts[handle.attempt].state, state);
}));
