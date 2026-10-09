// Invented fixture identities only; not a configurable broker request driver.
export const FIXTURE = Object.freeze({
  session: 'synthetic-session', target: 'synthetic-page', frame: 'synthetic-frame',
  origin: 'http://127.0.0.1:48123', auth: 'http://127.0.0.1:48123/auth',
  document: 'http://127.0.0.1:48123/document', account: 'synthetic-account', day: '2026-09-17',
});

export function requestExperiment({consume, continueRequest, stop}) {
  if ([consume, continueRequest, stop].some(f => typeof f !== 'function')) throw new Error('CAPABILITY_CALLBACK_REQUIRED');
  let queue = Promise.resolve(), fenced = false, used = false, armed = false, stopped;
  const ids = new Set();
  function abort() {
    fenced = true;
    if (!stopped) stopped = Promise.resolve().then(() => stop());
    return stopped;
  }
  function arm() {
    if (fenced || armed) throw new Error('CAPABILITY_PERMIT_REJECTED');
    armed = true;
  }
  function paused(event) {
    // Detach metadata before queuing; a callback cannot change queued authority.
    let capture;
    try { capture = structuredClone(event); } catch { capture = null; }
    const task = queue.then(async () => {
      try {
        if (fenced || !armed || used || !capture || typeof capture.requestId !== 'string'
            || !capture.requestId || ids.has(capture.requestId)
            || capture.sessionId !== FIXTURE.session || capture.frameId !== FIXTURE.frame
            || capture.pageEpoch !== 1 || capture.frameEpoch !== 1
            || capture.resourceType !== 'Document' || capture.request?.url !== FIXTURE.auth
            || capture.request?.method !== 'POST' || capture.redirectedRequestId !== undefined) {
          throw new Error('CAPABILITY_REQUEST_REJECTED');
        }
        ids.add(capture.requestId);
        // Mark one-shot locally before any callback, then await durable authority.
        used = true;
        if (await consume() !== true || fenced) throw new Error('CAPABILITY_PERMIT_REJECTED');
        await continueRequest(capture.requestId);
        if (fenced) throw new Error('CAPABILITY_REQUEST_REJECTED');
        return {continued: 1, browser_proven: false};
      } catch {
        await abort(); throw new Error('CAPABILITY_REQUEST_REJECTED');
      }
    });
    queue = task.catch(() => {});
    return task;
  }
  return {arm, paused, abort, fenced: () => fenced};
}

export function captureExperiment() {
  let stage = 'empty', ticket, requestId, loaderId;
  function reject() { stage = 'failed'; throw new Error('CAPABILITY_CAPTURE_REJECTED'); }
  function arm(value) {
    if (stage !== 'empty' || !value || value.target !== FIXTURE.target || value.frame !== FIXTURE.frame
        || value.account !== FIXTURE.account || value.day !== FIXTURE.day || value.url !== FIXTURE.document
        || value.pageEpoch !== 1 || value.frameEpoch !== 1 || value.role !== 'statement') reject();
    ticket = structuredClone(value); stage = 'armed';
  }
  function request(value) {
    if (stage !== 'armed' || !value || value.sessionId !== FIXTURE.session
        || value.frameId !== ticket.frame || value.request?.url !== ticket.url
        || value.request?.method !== 'GET' || value.type !== 'Document' || value.redirectResponse !== undefined
        || typeof value.requestId !== 'string' || !value.requestId
        || typeof value.loaderId !== 'string' || !value.loaderId) reject();
    requestId = value.requestId; loaderId = value.loaderId; stage = 'requested';
  }
  function commit(value) {
    if (stage !== 'requested' || value?.sessionId !== FIXTURE.session || value.frame?.id !== ticket.frame
        || value.frame?.loaderId !== loaderId || value.frame?.url !== ticket.url) reject();
    stage = 'committed';
  }
  function load(value) {
    if (stage !== 'committed' || value?.sessionId !== FIXTURE.session || value.frameId !== ticket.frame
        || value.loaderId !== loaderId || value.name !== 'load') reject();
    stage = 'loaded';
  }
  function capture(value) {
    if (stage !== 'loaded' || value?.account !== ticket.account || value.day !== ticket.day
        || value.target !== ticket.target || value.pageEpoch !== ticket.pageEpoch || value.frameEpoch !== ticket.frameEpoch) reject();
    stage = 'captured';
    return {requestId, loaderId, browser_proven: false};
  }
  return {arm, request, commit, load, capture};
}
