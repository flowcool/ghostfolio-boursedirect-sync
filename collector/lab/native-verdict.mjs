// Pure final-code fixture evaluator; importing it cannot start any runtime.
export const NATIVE_MODES = Object.freeze(['permitted', 'denied', 'popup', 'frame', 'worker', 'shared-worker',
  'service-worker', 'redirect307', 'redirect308', 'second-auth', 'concurrent', 'held-auth', 'http-auth',
  'fsync-failure', 'browser-crash', 'pipe-loss', 'forced-stop', 'capture',
  'capture-wrong-account', 'capture-wrong-day', 'capture-wrong-role', 'capture-unknown-operation',
  'denied-negative', 'popup-negative', 'frame-negative', 'worker-negative', 'shared-worker-negative',
  'service-worker-negative', 'redirect307-negative', 'redirect308-negative', 'second-auth-negative', 'concurrent-negative']);

export function nativeVerdict(e) {
  const failures = [], check = (condition, code) => {if (!condition) failures.push(code);};
  if (!e || !NATIVE_MODES.includes(e.mode)) return {passed: false, failures: ['NATIVE_MODE_INVALID']};
  if (!Array.isArray(e.trace) || e.trace.length > 1000 || e.trace.some(value => !value || typeof value !== 'object')
      || !e.counts || typeof e.counts !== 'object' || Array.isArray(e.counts)) {
    return {passed: false, failures: ['NATIVE_METADATA_INVALID']};
  }
  const negative = e.mode.endsWith('-negative'), scenario = e.mode.replace(/-negative$/, '');
  const capture = scenario.startsWith('capture'), trace = e.trace ?? [], counts = e.counts ?? {};
  const expected = ['permitted', 'redirect307', 'redirect308', 'second-auth'].includes(scenario) ? 1 : 0;
  const expectedNegative = ['second-auth', 'concurrent'].includes(scenario) ? [2, 0] : scenario.startsWith('redirect') ? [1, 1] : [0, 1];
  check(!e.failure && e.node === 'v20.19.2', 'NATIVE_RUNTIME_INVALID');
  check(e.owned_browser_exit === true && e.restartFenced === true, 'NATIVE_EXIT_OR_AUTH_UNVERIFIED');
  const stop = trace.findIndex(value => value.lifecycle === 'stop-owned'), exit = trace.findIndex(value => value.lifecycle === 'owned-exit');
  const close = trace.findIndex(value => value.lifecycle === 'close-pipe');
  check(stop >= 0 && trace[stop].fenced === true && exit > stop && close > exit && trace[close].exited === true, 'NATIVE_TEARDOWN_ORDER');
  const commands = trace.filter(value => value.command).map(value => value.command);
  let cursor = -1;
  const guards = ['Browser.getVersion', 'Target.setAutoAttach', 'Target.setDiscoverTargets', 'Target.createTarget',
    'Target.setAutoAttach', 'Network.enable', 'Network.setBypassServiceWorker', 'Network.setCacheDisabled',
    'Page.enable', 'Page.setLifecycleEventsEnabled', ...(!negative ? ['Fetch.enable'] : []),
    'Page.getFrameTree', 'Runtime.runIfWaitingForDebugger'];
  for (const command of guards) {
    const next = commands.indexOf(command, cursor + 1);
    check(next > cursor, 'NATIVE_STARTUP_ORDER');
    if (next >= 0) cursor = next;
  }
  check(trace.some(value => value.event === 'Target.attachedToTarget' && value.type === 'page' && value.waiting === true), 'NATIVE_OWNED_ATTACH_MISSING');
  check(Number.isInteger(e.allowed) && Number.isInteger(e.forbidden)
    && (negative ? e.allowed === expectedNegative[0] && e.forbidden === expectedNegative[1]
      : e.forbidden === 0 && (scenario === 'concurrent' ? [0, 1].includes(e.allowed) : e.allowed === expected)), 'NATIVE_DISPATCH_COUNT');
  let stimulus;
  if (negative) stimulus = true; // Exact forbidden/duplicate server count above is discriminating.
  else if (scenario === 'permitted') stimulus = e.consumes === 1;
  else if (scenario === 'http-auth') stimulus = e.challenges === 1 && e.cancelled === 1
    && trace.filter(value => value.cancel === 'CancelAuth').length === 1;
  else if (capture) {
    if (scenario === 'capture') {
      const native = e.captureResult?.native;
      stimulus = e.captureResult?.fresh === true && Array.isArray(native) && native.length === 2
        && native.every(value => ['requestId', 'fetchRequestId', 'loaderId', 'sessionId', 'frameId', 'targetId'].every(k => typeof value[k] === 'string' && value[k])
          && /^[0-9a-f]{64}$/.test(value.body_sha256))
        && native[0].loaderId !== native[1].loaderId && native[0].requestId !== native[1].requestId
        && native[0].body_sha256 === native[1].body_sha256;
    } else stimulus = e.captureRefused === true && e.captureResult?.accepted === 0;
  } else if (scenario === 'popup') stimulus = (counts['Target.attachedToTarget'] || 0) >= 2;
  else if (scenario.includes('worker')) stimulus = trace.some(value => value.type === scenario.replace('-', '_'));
  else if (scenario === 'frame') stimulus = trace.some(value => value.pause === '/forbidden' && value.ownedFrame === false && value.method === 'POST' && value.resource === 'Document');
  else if (['second-auth', 'concurrent', 'held-auth'].includes(scenario)) stimulus = trace.filter(value => value.pause === '/allowed' && value.method === 'POST').length === 2;
  else if (scenario.startsWith('redirect')) stimulus = trace.some(value => value.pause === '/forbidden' && value.redirect === true);
  else stimulus = trace.some(value => value.pause === (['fsync-failure', 'browser-crash'].includes(scenario) ? '/allowed' : '/forbidden') && value.method === 'POST');
  check(stimulus, 'NATIVE_STIMULUS_MISSING');
  if (scenario === 'fsync-failure') check(e.fsyncFailed === true && e.consumes === 0, 'NATIVE_FSYNC_UNPROVED');
  if (scenario === 'browser-crash') check(e.crashed === true && e.consumes === 1, 'NATIVE_CRASH_UNPROVED');
  if (scenario === 'forced-stop') check(e.forceKilled === true, 'NATIVE_FORCE_STOP_UNPROVED');
  if (scenario === 'held-auth') check(e.held === true && e.consumes === 1, 'NATIVE_HELD_CALLBACK_UNPROVED');
  check(e.online_ready === false && e.browser_proven === false && e.import_ready === false, 'NATIVE_READINESS_INVALID');
  return {passed: failures.length === 0, failures};
}
