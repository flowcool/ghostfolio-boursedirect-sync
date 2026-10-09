import test from 'node:test';
import assert from 'node:assert/strict';
import {bootstrapExperiment} from '../capability-bootstrap.mjs';

const attach = (type = 'page', extra = {}) => ({method: 'Target.attachedToTarget', params: {
  sessionId: 's', waitingForDebugger: true, targetInfo: {type, targetId: 'owned', url: 'about:blank'}, ...extra,
}});
function fixture(overrides = {}) {
  const actions = [];
  const experiment = bootstrapExperiment({send: async (method, params) => {
    actions.push(method);
    if (method === 'Browser.getVersion') return {product: 'Chrome/148.0.7778.97'};
    if (method === 'Target.createTarget') {experiment.event(attach()); return {targetId: 'owned'};}
    return {};
  }, registerSession: id => actions.push('register:' + id),
  initialize: async id => actions.push('initialize:' + id), stop: () => actions.push('stop'), ...overrides});
  return {experiment, actions};
}
test('early attachment remains paused until create reply binds its exact target', async () => {
  let resolve, entered;
  const reply = new Promise(ok => {resolve = ok;}), creating = new Promise(ok => {entered = ok;});
  const f = fixture({send: async method => {
    if (method === 'Browser.getVersion') return {product: 'Chrome/148.0.7778.97'};
    if (method === 'Target.createTarget') {f.experiment.event(attach()); entered(); return reply;}
    return {};
  }});
  const run = f.experiment.start(); await creating;
  assert.deepEqual(f.actions, []); assert.equal(f.experiment.ready(), false);
  resolve({targetId: 'owned'});
  assert.deepEqual(await run, {targetId: 'owned', sessionId: 's', browser_proven: false});
  assert.deepEqual(f.actions, ['register:s', 'initialize:s']);
});
test('normal mock startup orders version, browser guard, discovery, creation and target initialization', async () => {
  const f = fixture(); await f.experiment.start();
  assert.deepEqual(f.actions, ['Browser.getVersion', 'Target.setAutoAttach', 'Target.setDiscoverTargets',
    'Target.createTarget', 'register:s', 'initialize:s']);
});
for (const type of ['worker', 'service_worker', 'shared_worker', 'iframe']) {
  test(`unexpected ${type} never registers or initializes`, async () => {
    const f = fixture({send: async method => {
      if (method === 'Browser.getVersion') return {product: 'Chrome/148.0.7778.97'};
      if (method === 'Target.createTarget') f.experiment.event(attach(type)); return {};
    }});
    await assert.rejects(f.experiment.start(), /CAPABILITY_BOOTSTRAP_FAILED/);
    assert.deepEqual(f.actions, ['stop']);
  });
}
test('unpaused new target immediately fences startup', async () => {
  const f = fixture({send: async method => {
    if (method === 'Browser.getVersion') return {product: 'Chrome/148.0.7778.97'};
    if (method === 'Target.createTarget') f.experiment.event(attach('page', {waitingForDebugger: false})); return {};
  }});
  await assert.rejects(f.experiment.start(), /CAPABILITY_BOOTSTRAP_FAILED/); assert.deepEqual(f.actions, ['stop']);
});
test('same URL is insufficient when attachment target differs from create reply', async () => {
  const f = fixture({send: async method => {
    if (method === 'Browser.getVersion') return {product: 'Chrome/148.0.7778.97'};
    if (method === 'Target.createTarget') {f.experiment.event(attach()); return {targetId: 'other'};} return {};
  }});
  await assert.rejects(f.experiment.start(), /CAPABILITY_BOOTSTRAP_FAILED/); assert.deepEqual(f.actions, ['stop']);
});
test('version mismatch creates no page or guard commands', async () => {
  const f = fixture({send: async () => ({product: 'Chrome/other'})});
  await assert.rejects(f.experiment.start(), /CAPABILITY_BOOTSTRAP_FAILED/); assert.deepEqual(f.actions, ['stop']);
});
test('pre-existing page is rejected before bootstrap', async () => {
  const f = fixture(); assert.throws(() => f.experiment.event(attach()), /CAPABILITY_TARGET_REJECTED/);
  await assert.rejects(f.experiment.start(), /CAPABILITY_TARGET_REJECTED/);
});
test('second popup while binding first page aborts without registration', async () => {
  const f = fixture({send: async method => {
    if (method === 'Browser.getVersion') return {product: 'Chrome/148.0.7778.97'};
    if (method === 'Target.createTarget') {f.experiment.event(attach()); f.experiment.event(attach());} return {};
  }});
  await assert.rejects(f.experiment.start(), /CAPABILITY_BOOTSTRAP_FAILED/); assert.deepEqual(f.actions, ['stop']);
});
test('popup after ready fences previously accepted target without initializing popup', async () => {
  const f = fixture(); await f.experiment.start();
  assert.throws(() => f.experiment.event(attach()), /CAPABILITY_TARGET_REJECTED/);
  await f.experiment.abort(); assert.equal(f.experiment.ready(), false);
  assert.equal(f.actions.filter(v => v.startsWith('initialize')).length, 1);
});

test('abort releases an attachment wait without registering or initializing', async () => {
  let created;
  const waiting = new Promise(resolve => {created = resolve;});
  const f = fixture({send: async method => {
    if (method === 'Browser.getVersion') return {product: 'Chrome/148.0.7778.97'};
    if (method === 'Target.createTarget') {created(); return {targetId: 'owned'};}
    return {};
  }});
  const run = f.experiment.start(), failure = assert.rejects(run, /BOOTSTRAP_FAILED/);
  await waiting; await f.experiment.abort(); await failure;
  assert.deepEqual(f.actions, ['stop']);
});
