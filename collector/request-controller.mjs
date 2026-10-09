// Callback-only policy. No launcher, credentials, DOM, source loader or online CLI.
import {brokerUrl, evaluateRequest, validateSourceContract} from './core.mjs';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const TYPES = new Set(['Document', 'XHR', 'Fetch', 'Script', 'Stylesheet', 'Image', 'Font']);
export const REQUEST_LIMITS = Object.freeze({queue: 64, requests: 1000, callbackMs: 45000});

function exact(value, keys) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || Object.keys(value).length !== keys.length || keys.some(k => !Object.hasOwn(value, k))) {
    throw new Error('REQUEST_METADATA_INVALID');
  }
}
function identifier(value) {
  if (typeof value !== 'string' || !value || value.length > 256) throw new Error('REQUEST_METADATA_INVALID');
}
function epoch(value) {
  if (typeof value !== 'string' || !UUID.test(value)) throw new Error('REQUEST_METADATA_INVALID');
}

export function requestController({binding, source, reads = [], consume, continueRequest, cancelAuth, stop, now,
                                   limits = REQUEST_LIMITS}) {
  let owner, contract, roles, budget;
  try {
    if ([consume, continueRequest, cancelAuth, stop, now].some(f => typeof f !== 'function')) throw new Error();
    exact(binding, ['targetId', 'sessionId', 'pageEpoch', 'frames']);
    identifier(binding.targetId); identifier(binding.sessionId); epoch(binding.pageEpoch);
    if (!binding.frames || typeof binding.frames !== 'object' || Array.isArray(binding.frames)
        || !Object.keys(binding.frames).length || Object.keys(binding.frames).length > 1000) throw new Error();
    for (const [id, frame] of Object.entries(binding.frames)) {
      identifier(id); exact(frame, ['epoch', 'role']); epoch(frame.epoch); identifier(frame.role);
    }
    validateSourceContract(source);
    if (!Array.isArray(reads) || reads.length > 256) throw new Error();
    const tuples = new Set();
    for (const role of reads) {
      exact(role, ['role', 'url', 'method', 'resourceType']); identifier(role.role); brokerUrl(role.url);
      if (role.method !== 'GET' || !TYPES.has(role.resourceType)
          || Object.values(source.roles).some(auth => auth?.url === role.url)) throw new Error();
      const key = JSON.stringify([role.role, role.url, role.resourceType]);
      if (tuples.has(key)) throw new Error();
      tuples.add(key);
    }
    exact(limits, Object.keys(REQUEST_LIMITS));
    for (const [key, max] of Object.entries(REQUEST_LIMITS)) {
      if (!Number.isSafeInteger(limits[key]) || limits[key] < 1 || limits[key] > max) throw new Error();
    }
    owner = structuredClone(binding); contract = structuredClone(source);
    roles = structuredClone(reads); budget = {...limits};
  } catch { throw new Error('REQUEST_CONFIG_INVALID'); }

  let fenced = false, stopping, pending = 0, queue = Promise.resolve(), action, reserved = false, lastOtpClock;
  const seen = new Set(), challenges = new Set();
  function check() { if (fenced) throw new Error('REQUEST_FENCED'); }
  function bounded(callback) {
    let timer;
    const deadline = new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error('REQUEST_CALLBACK_TIMEOUT')), budget.callbackMs);
    });
    // Never leak injected callback errors or their secret-bearing causes.
    const operation = Promise.resolve().then(callback).catch(() => {throw new Error('REQUEST_CALLBACK_FAILED');});
    return Promise.race([operation, deadline]).finally(() => clearTimeout(timer));
  }
  function stopOnce() {
    if (!stopping) {
      stopping = bounded(stop).then(exited => {
        if (exited !== true) throw new Error('REQUEST_STOP_UNVERIFIED');
        return {stopped: true, online_ready: false, browser_proven: false, import_ready: false};
      }, () => {throw new Error('REQUEST_STOP_UNVERIFIED');});
      // Synchronous event callers may throw before their consumer awaits cleanup.
      void stopping.catch(() => {});
    }
    return stopping;
  }
  function abort() { fenced = true; return stopOnce(); }
  async function refuse() {
    await abort(); throw new Error('REQUEST_REJECTED');
  }
  function otpClock(value) {
    const time = now(), issued = value.otp.issuedAt;
    if (!Number.isSafeInteger(time) || time < 0 || !Number.isSafeInteger(issued) || issued < 0
        || !Number.isSafeInteger(value.otp.step) || value.otp.step !== Math.floor(issued / 30)
        || time < issued || (lastOtpClock !== undefined && time < lastOtpClock)
        || time - issued > 20 || Math.floor(time / 30) !== value.otp.step || 30 - time % 30 < 5) {
      throw new Error('REQUEST_OTP_EXPIRED');
    }
    lastOtpClock = time;
    return time;
  }
  function arm(value) {
    try {
      check();
      if (action) throw new Error();
      const keys = ['phase', 'nonce', 'pageEpoch', 'frameEpoch', 'frameId', 'url', 'method', 'resourceType'];
      exact(value, value?.phase === 'otp_uncertain' ? [...keys, 'otp'] : keys);
      epoch(value.nonce); epoch(value.pageEpoch); epoch(value.frameEpoch);
      if (!['password_uncertain', 'otp_uncertain'].includes(value.phase)
          || value.pageEpoch !== owner.pageEpoch || !Object.hasOwn(owner.frames, value.frameId)
          || value.frameEpoch !== owner.frames[value.frameId].epoch
          || !evaluateRequest(contract, value.phase, {
            url: value.url, method: value.method, resource_type: value.resourceType, redirect: false,
          })) throw new Error();
      if (value.phase === 'otp_uncertain') {
        exact(value.otp, ['issuedAt', 'step']); otpClock(value);
      }
      // Caller must already have durably armed this exact permit before any fill.
      action = structuredClone(value);
    } catch {
      void abort().catch(() => {}); throw new Error('REQUEST_ACTION_REJECTED');
    }
  }
  function paused(value) {
    let request, auth;
    try {
      check();
      const keys = ['requestId', 'sessionId', 'frameId', 'pageEpoch', 'frameEpoch', 'resourceType', 'request'];
      exact(value, Object.hasOwn(value ?? {}, 'redirectedRequestId') ? [...keys, 'redirectedRequestId'] : keys);
      exact(value.request, ['url', 'method']);
      identifier(value.requestId);
      if (value.sessionId !== owner.sessionId || !Object.hasOwn(owner.frames, value.frameId)
          || value.pageEpoch !== owner.pageEpoch || value.frameEpoch !== owner.frames[value.frameId].epoch
          || Object.hasOwn(value, 'redirectedRequestId') || !TYPES.has(value.resourceType)
          || seen.has(value.requestId) || seen.size >= budget.requests || pending >= budget.queue) throw new Error();
      request = structuredClone(value);
      auth = !!action && ['url', 'method'].every(k => request.request[k] === action[k])
        && request.resourceType === action.resourceType && request.frameId === action.frameId;
      const read = roles.some(role => role.role === owner.frames[request.frameId].role
        && role.url === request.request.url && role.method === request.request.method
        && role.resourceType === request.resourceType);
      if (!auth && !read) throw new Error();
      // Reserve at ingress, not after a queued/held durable callback completes.
      if (auth && reserved) throw new Error();
      if (auth) reserved = true;
      seen.add(request.requestId); pending++;
    } catch { return refuse(); }
    const task = queue.then(async () => {
      try {
        check();
        if (auth) {
          const time = action.phase === 'otp_uncertain' ? otpClock(action) : now();
          if (!Number.isSafeInteger(time) || time < 0) throw new Error();
          const permit = {phase: action.phase, page_epoch: action.pageEpoch, frame_epoch: action.frameEpoch,
            url: action.url, method: action.method, resource_type: action.resourceType,
            nonce: action.nonce, redirect: false};
          if (await bounded(() => {
            check();
            return consume(permit, action.phase === 'otp_uncertain' ? otpClock(action) : time);
          }) !== true) throw new Error();
          check();
          if (action.phase === 'otp_uncertain') otpClock(action);
        }
        await bounded(() => {
          check();
          if (auth && action.phase === 'otp_uncertain') otpClock(action);
          return continueRequest(request.requestId);
        });
        check();
        return {continued: 1, online_ready: false, browser_proven: false, import_ready: false};
      } catch { return refuse(); }
      finally { pending--; }
    });
    queue = task.catch(() => {});
    return task;
  }
  async function authRequired(value) {
    // Disable every ordinary action BEFORE sending or awaiting CancelAuth.
    fenced = true;
    let cancellation;
    try {
      exact(value, ['sessionId', 'requestId']); identifier(value.requestId);
      if (value.sessionId !== owner.sessionId || challenges.has(value.requestId)
          || challenges.size >= budget.requests) throw new Error();
      challenges.add(value.requestId);
      // Invoke once immediately; stop runs even if the acknowledgement never arrives.
      const sent = cancelAuth(value.requestId, {response: 'CancelAuth'});
      cancellation = bounded(() => sent);
    } catch { cancellation = Promise.reject(new Error('REQUEST_AUTH_REJECTED')); }
    const outcomes = await Promise.allSettled([cancellation, stopOnce()]);
    if (outcomes[1].status !== 'fulfilled') throw new Error('REQUEST_STOP_UNVERIFIED');
    throw new Error('REQUEST_AUTH_REJECTED');
  }
  return {arm, paused, authRequired, abort,
    status: () => ({fenced, pending, seen: seen.size, online_ready: false, browser_proven: false, import_ready: false})};
}
