// Synthetic-only ordering experiment. No browser launch, sources or credentials.
export const GUARDS = Object.freeze([
  ['Target.setAutoAttach', {autoAttach: true, waitForDebuggerOnStart: true, flatten: true}],
  ['Network.enable', {}],
  ['Network.setBypassServiceWorker', {bypass: true}],
  ['Network.setCacheDisabled', {cacheDisabled: true}],
  ['Page.enable', {}],
  ['Page.setLifecycleEventsEnabled', {enabled: true}],
  ['Fetch.enable', {patterns: Object.freeze([Object.freeze({urlPattern: '*', requestStage: 'Request'})]), handleAuthRequests: true}],
].map(([method, params]) => Object.freeze([method, Object.freeze(params)])));

export function orderingExperiment({send, installRoutes, stopOwned, closePipe, beforeResume = () => {}}) {
  if ([send, installRoutes, stopOwned, closePipe, beforeResume].some(f => typeof f !== 'function')) {
    throw new Error('CAPABILITY_CALLBACK_REQUIRED');
  }
  let fenced = false, starting = false, ready = false, stop, ownedSession;
  function abort() {
    // Fence synchronously, including while a guard acknowledgement is pending.
    fenced = true; ready = false;
    if (!stop) stop = Promise.resolve().then(async () => {
      if (await stopOwned() !== true) throw new Error('CAPABILITY_EXIT_UNVERIFIED');
      await closePipe();
    });
    return stop;
  }
  function check() {
    if (fenced) throw new Error('CAPABILITY_FENCED');
  }
  async function initialize(sessionId, waitingForDebugger) {
    if (typeof sessionId !== 'string' || !sessionId || waitingForDebugger !== true || starting) {
      await abort(); throw new Error('CAPABILITY_ATTACHMENT_REJECTED');
    }
    starting = true;
    ownedSession = sessionId;
    try {
      check();
      await installRoutes(sessionId);
      for (const [method, params] of GUARDS) {
        check();
        // Fresh parameters prevent injected test callbacks from changing later runs.
        await send(method, structuredClone(params), sessionId);
      }
      check();
      await beforeResume(sessionId);
      check();
      await send('Runtime.runIfWaitingForDebugger', {}, sessionId);
      check(); ready = true;
      return {guarded: true, browser_proven: false};
    } catch {
      await abort();
      throw new Error('CAPABILITY_INITIALIZATION_FAILED');
    }
  }
  async function cancelHttpAuth(sessionId, requestId) {
    try {
      check();
      if (!ready || sessionId !== ownedSession || typeof requestId !== 'string' || !requestId) {
        throw new Error('CAPABILITY_AUTH_REJECTED');
      }
      await send('Fetch.continueWithAuth', {
        requestId, authChallengeResponse: {response: 'CancelAuth'},
      }, sessionId);
    } catch {
      throw new Error('CAPABILITY_AUTH_REJECTED');
    } finally {
      await abort();
    }
  }
  return {initialize, abort, cancelHttpAuth, fenced: () => fenced};
}
