import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeVerdict, NATIVE_MODES} from '../lab/native-verdict.mjs';
import {orderingExperiment, GUARDS} from '../capability-ordering.mjs';

function positive() {
  const commands = ['Browser.getVersion', 'Target.setAutoAttach', 'Target.setDiscoverTargets', 'Target.createTarget',
    ...GUARDS.map(([method]) => method), 'Page.getFrameTree', 'Runtime.runIfWaitingForDebugger'];
  return {mode: 'permitted', node: 'v20.19.2', allowed: 1, forbidden: 0, consumes: 1,
    trace: [...commands.map(command => ({command})),
      {event: 'Target.attachedToTarget', type: 'page', waiting: true},
      {lifecycle: 'stop-owned', fenced: true}, {lifecycle: 'owned-exit'}, {lifecycle: 'close-pipe', exited: true}],
    counts: {}, owned_browser_exit: true, restartFenced: true,
    online_ready: false, browser_proven: false, import_ready: false};
}
test('native evaluator requires the complete startup, one-use dispatch and exit proof', () => {
  assert.equal(nativeVerdict(positive()).passed, true); assert.equal(new Set(NATIVE_MODES).size, NATIVE_MODES.length);
});
for (const [name, change] of [
  ['missing guard', e => {e.trace = e.trace.filter(v => v.command !== 'Fetch.enable');}],
  ['late guard', e => {const at = e.trace.findIndex(v => v.command === 'Runtime.runIfWaitingForDebugger');
    const guard = e.trace.splice(e.trace.findIndex(v => v.command === 'Fetch.enable'), 1)[0]; e.trace.splice(at + 1, 0, guard);}],
  ['unpaused attachment', e => {e.trace.find(v => v.event).waiting = false;}],
  ['late stop', e => {const at = e.trace.findIndex(v => v.lifecycle === 'stop-owned'); [e.trace[at], e.trace[at + 1]] = [e.trace[at + 1], e.trace[at]];}],
  ['forbidden dispatch', e => {e.forbidden = 1;}],
  ['no real permit', e => {e.consumes = 0;}],
  ['unverified fresh process', e => {e.restartFenced = false;}],
  ['readiness claim', e => {e.online_ready = true;}],
]) test('native evaluator discriminates ' + name, () => {
  const e = positive(); change(e); e.passed = true; assert.equal(nativeVerdict(e).passed, false);
});
test('root attachment alone cannot prove denied/frame/worker/second-auth stimuli', () => {
  for (const mode of ['denied', 'frame', 'worker', 'second-auth', 'concurrent']) {
    const e = positive(); e.mode = mode; e.allowed = mode === 'second-auth' ? 1 : 0;
    assert.equal(nativeVerdict(e).passed, false, mode);
  }
});
test('negative control must dispatch its exact forbidden or duplicate count', () => {
  const e = positive(); e.mode = 'denied-negative'; e.allowed = 0; e.forbidden = 1;
  e.trace = e.trace.filter(value => value.command !== 'Fetch.enable');
  assert.equal(nativeVerdict(e).passed, true); e.forbidden = 0; assert.equal(nativeVerdict(e).passed, false);
});
test('native setup callback is acknowledged before resume and failure permanently fences', async () => {
  const calls = []; let release;
  const setup = new Promise(resolve => {release = resolve;});
  const ordering = orderingExperiment({send: async method => {calls.push(method);}, installRoutes: () => {},
    beforeResume: () => {calls.push('setup'); return setup;}, stopOwned: () => true, closePipe: () => calls.push('close')});
  const pending = ordering.initialize('native-session', true);
  while (!calls.includes('setup')) await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls.includes('Runtime.runIfWaitingForDebugger'), false);
  await ordering.abort(); release(); await assert.rejects(pending, /INITIALIZATION_FAILED/);
  assert.equal(calls.includes('Runtime.runIfWaitingForDebugger'), false);
});
