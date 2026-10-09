import test from 'node:test';
import assert from 'node:assert/strict';
import {GUARDS, orderingExperiment} from '../capability-ordering.mjs';

function deferred() {
  let resolve, reject;
  const promise = new Promise((ok, fail) => {resolve = ok; reject = fail;});
  return {promise, resolve, reject};
}
function fixture(overrides = {}) {
  const events = [];
  const callbacks = {
    send: async method => {events.push(method);},
    installRoutes: async () => {events.push('routes');},
    stopOwned: async () => {events.push('owned-exit'); return true;},
    closePipe: async () => {events.push('pipe-close');},
    ...overrides,
  };
  return {events, callbacks, experiment: orderingExperiment(callbacks)};
}

for (const [heldMethod] of GUARDS) {
  test(`resume waits for acknowledged ${heldMethod}`, async () => {
    const gate = deferred(), entered = deferred();
    let acknowledged = false, forbiddenDispatches = 0;
    const f = fixture({send: async method => {
      f.events.push(method);
      if (method === heldMethod) {entered.resolve(); await gate.promise; acknowledged = true;}
      if (method === 'Runtime.runIfWaitingForDebugger' && !acknowledged) forbiddenDispatches++;
    }});
    const run = f.experiment.initialize('owned-session', true);
    await entered.promise;
    assert.equal(f.events.includes('Runtime.runIfWaitingForDebugger'), false);
    assert.deepEqual(f.events, ['routes', ...GUARDS.map(([m]) => m).slice(0, GUARDS.findIndex(([m]) => m === heldMethod) + 1)]);
    gate.resolve();
    assert.deepEqual(await run, {guarded: true, browser_proven: false});
    assert.equal(forbiddenDispatches, 0);
    assert.equal(f.events.at(-1), 'Runtime.runIfWaitingForDebugger');
  });
}

test('negative control detects parallel resume before interception acknowledgement', async () => {
  const gate = deferred();
  let guarded = false, forbiddenDispatches = 0;
  const guard = gate.promise.then(() => {guarded = true;});
  const resume = Promise.resolve().then(() => {if (!guarded) forbiddenDispatches++;});
  await resume;
  assert.equal(forbiddenDispatches, 1);
  gate.resolve(); await Promise.all([guard, resume]);
});

test('abort fences pending initialization and waits for owned exit before closing pipe', async () => {
  const ack = deferred(), entered = deferred(), exit = deferred();
  const f = fixture({
    send: async method => {f.events.push(method); entered.resolve(); await ack.promise;},
    stopOwned: async () => {f.events.push('stop-request'); return exit.promise;},
  });
  const run = f.experiment.initialize('owned-session', true);
  const outcome = assert.rejects(run, /CAPABILITY_INITIALIZATION_FAILED/);
  await entered.promise;
  const stop = f.experiment.abort();
  assert.equal(f.experiment.fenced(), true);
  await Promise.resolve();
  assert.equal(f.events.includes('pipe-close'), false);
  ack.resolve(); exit.resolve(true); await stop; await outcome;
  assert.equal(f.events.at(-1), 'pipe-close');
  assert.equal(f.events.includes('Runtime.runIfWaitingForDebugger'), false);
  assert.equal(f.events.filter(v => v === 'stop-request').length, 1);
});

for (const [failedMethod] of GUARDS) {
  test(`failed ${failedMethod} never resumes and closes only after stop`, async () => {
    const f = fixture({send: async method => {
      f.events.push(method); if (method === failedMethod) throw new Error('private callback detail');
    }});
    await assert.rejects(f.experiment.initialize('owned-session', true), /CAPABILITY_INITIALIZATION_FAILED/);
    assert.equal(f.events.includes('Runtime.runIfWaitingForDebugger'), false);
    assert.deepEqual(f.events.slice(-2), ['owned-exit', 'pipe-close']);
  });
}

test('unverified owned exit prevents intentional pipe closure', async () => {
  const f = fixture({stopOwned: async () => false});
  await assert.rejects(f.experiment.abort(), /CAPABILITY_EXIT_UNVERIFIED/);
  assert.equal(f.experiment.fenced(), true);
  assert.equal(f.events.includes('pipe-close'), false);
});

test('unpaused attachment stops without setup or resume', async () => {
  const f = fixture();
  await assert.rejects(f.experiment.initialize('owned-session', false), /CAPABILITY_ATTACHMENT_REJECTED/);
  assert.deepEqual(f.events, ['owned-exit', 'pipe-close']);
});

test('HTTP authentication cancels explicitly and then stops', async () => {
  const commands = [];
  const f = fixture({send: async (...args) => {commands.push(args);}});
  await f.experiment.initialize('owned-session', true);
  await f.experiment.cancelHttpAuth('owned-session', 'challenge');
  assert.deepEqual(commands.at(-1), ['Fetch.continueWithAuth', {
    requestId: 'challenge', authChallengeResponse: {response: 'CancelAuth'},
  }, 'owned-session']);
  assert.deepEqual(f.events.slice(-2), ['owned-exit', 'pipe-close']);
  assert.equal(f.experiment.fenced(), true);
});

test('unknown auth session never sends cancellation or credentials', async () => {
  const f = fixture();
  await f.experiment.initialize('owned-session', true);
  const prior = f.events.length;
  await assert.rejects(f.experiment.cancelHttpAuth('other-session', 'challenge'), /CAPABILITY_AUTH_REJECTED/);
  assert.deepEqual(f.events.slice(prior), ['owned-exit', 'pipe-close']);
});

test('HTTP-auth cancellation failure still stops before pipe closure', async () => {
  const f = fixture({send: async method => {
    f.events.push(method);
    if (method === 'Fetch.continueWithAuth') throw new Error('synthetic cancellation failure');
  }});
  await f.experiment.initialize('owned-session', true);
  await assert.rejects(f.experiment.cancelHttpAuth('owned-session', 'challenge'), /CAPABILITY_AUTH_REJECTED/);
  assert.deepEqual(f.events.slice(-2), ['owned-exit', 'pipe-close']);
  assert.equal(f.experiment.fenced(), true);
});
