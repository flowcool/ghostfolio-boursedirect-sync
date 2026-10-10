// Synthetic capability transport: injected pipe and lifecycle, no child startup.
export const PIPE_LIMITS = Object.freeze({
  messageBytes: 1048576, pending: 1000, sessions: 32, startupEvents: 1000,
  queuedBytes: 8388608, commandMs: 45000, sessionMs: 1800000,
});

export function capabilityPipe({write, onEvent, fence, schedule = setTimeout, cancel = clearTimeout,
                               limits = PIPE_LIMITS}) {
  const keys = Object.keys(PIPE_LIMITS);
  if ([write, onEvent, fence, schedule, cancel].some(f => typeof f !== 'function')
      || !limits || Object.keys(limits).length !== keys.length
      || keys.some(k => !Number.isSafeInteger(limits[k]) || limits[k] < 1 || limits[k] > PIPE_LIMITS[k])) {
    throw new Error('CAPABILITY_PIPE_CONFIG_INVALID');
  }
  const budget = {...limits}, pending = new Map(), sessions = new Set(), events = [];
  const decoder = new TextDecoder('utf-8', {fatal: true});
  let nextId = 0, buffer = Buffer.alloc(0), queued = 0, eventBytes = 0, armed = false, failed = false;
  let lifetime;
  function die(code) {
    if (!failed) {
      failed = true;
      // The lifecycle callback must fence synchronously; it owns stop-before-close.
      try { fence(code); } catch { /* A fence failure still cannot resume transport. */ }
      cancel(lifetime);
      for (const item of pending.values()) {
        cancel(item.timer); item.reject(new Error(code));
      }
      pending.clear(); events.length = 0; buffer = Buffer.alloc(0); eventBytes = 0;
    }
    return new Error(code);
  }
  lifetime = schedule(() => die('CAPABILITY_SESSION_TIMEOUT'), budget.sessionMs);
  lifetime?.unref?.();
  function registerSession(id) {
    if (failed) throw new Error('CAPABILITY_PIPE_FENCED');
    if (typeof id !== 'string' || !id || sessions.has(id) || sessions.size >= budget.sessions) {
      throw die('CAPABILITY_SESSION_REJECTED');
    }
    sessions.add(id);
  }
  function dispatch(event) {
    try {
      const result = onEvent(event);
      // Routing/fencing is synchronous; asynchronous handlers cannot acknowledge it.
      if (result && typeof result.then === 'function') {
        Promise.resolve(result).catch(() => {});
        throw new Error('CAPABILITY_EVENT_REJECTED');
      }
    } catch { throw die('CAPABILITY_EVENT_REJECTED'); }
  }
  function armEvents() {
    if (failed) throw new Error('CAPABILITY_PIPE_FENCED');
    if (armed) throw die('CAPABILITY_EVENT_STATE_INVALID');
    armed = true;
    while (events.length) {
      const event = events.shift(); eventBytes -= event.bytes;
      dispatch(event.message);
      if (failed) break;
    }
  }
  function message(raw) {
    let data;
    try { data = JSON.parse(decoder.decode(raw)); } catch { throw die('CAPABILITY_MESSAGE_INVALID'); }
    if (!data || typeof data !== 'object' || Array.isArray(data)) throw die('CAPABILITY_MESSAGE_INVALID');
    if (data.sessionId !== undefined && !sessions.has(data.sessionId)) throw die('CAPABILITY_SESSION_REJECTED');
    if (Object.hasOwn(data, 'id')) {
      const item = pending.get(data.id);
      if (!Number.isSafeInteger(data.id) || !item || data.sessionId !== item.sessionId
          || Object.hasOwn(data, 'method')
          || Object.hasOwn(data, 'result') === Object.hasOwn(data, 'error')) {
        throw die('CAPABILITY_REPLY_REJECTED');
      }
      pending.delete(data.id); cancel(item.timer);
      if (Object.hasOwn(data, 'error')) {
        item.reject(die('CAPABILITY_COMMAND_REJECTED'));
      } else item.resolve(data.result);
    } else {
      if (typeof data.method !== 'string' || !data.method || !data.params
          || typeof data.params !== 'object' || Array.isArray(data.params)) {
        throw die('CAPABILITY_EVENT_REJECTED');
      }
      if (armed) dispatch(data);
      else {
        if (events.length >= budget.startupEvents || eventBytes + raw.length > budget.queuedBytes) {
          throw die('CAPABILITY_EVENT_LIMIT');
        }
        events.push({message: data, bytes: raw.length}); eventBytes += raw.length;
      }
    }
  }
  function receive(chunk) {
    if (failed) throw new Error('CAPABILITY_PIPE_FENCED');
    if (!Buffer.isBuffer(chunk) || chunk.length + buffer.length + eventBytes > budget.queuedBytes) {
      throw die('CAPABILITY_INPUT_LIMIT');
    }
    buffer = Buffer.concat([buffer, chunk]);
    while (!failed) {
      const end = buffer.indexOf(0);
      if (end < 0) {
        if (buffer.length > budget.messageBytes) throw die('CAPABILITY_MESSAGE_LIMIT');
        break;
      }
      if (!end || end > budget.messageBytes) throw die('CAPABILITY_MESSAGE_LIMIT');
      const raw = buffer.subarray(0, end); buffer = buffer.subarray(end + 1);
      message(raw);
    }
  }
  function send(method, params = {}, sessionId) {
    if (failed) return Promise.reject(new Error('CAPABILITY_PIPE_FENCED'));
    if (typeof method !== 'string' || !method || !params || typeof params !== 'object' || Array.isArray(params)
        || (sessionId !== undefined && !sessions.has(sessionId)) || nextId === Number.MAX_SAFE_INTEGER) {
      return Promise.reject(die('CAPABILITY_COMMAND_INVALID'));
    }
    let bytes;
    const id = ++nextId;
    try { bytes = Buffer.from(JSON.stringify({id, method, params, ...(sessionId === undefined ? {} : {sessionId})}) + '\0'); }
    catch { return Promise.reject(die('CAPABILITY_COMMAND_INVALID')); }
    if (bytes.length - 1 > budget.messageBytes || queued + bytes.length > budget.queuedBytes
        || pending.size >= budget.pending) return Promise.reject(die('CAPABILITY_OUTPUT_LIMIT'));
    return new Promise((resolve, reject) => {
      const item = {resolve, reject, sessionId, timer: undefined};
      pending.set(id, item); queued += bytes.length;
      item.timer = schedule(() => die('CAPABILITY_COMMAND_TIMEOUT'), budget.commandMs);
      item.timer?.unref?.();
      try {
        Promise.resolve(write(bytes)).then(() => {queued -= bytes.length;}, () => die('CAPABILITY_PIPE_LOST'));
      } catch { die('CAPABILITY_PIPE_LOST'); }
    });
  }
  function lost() { die('CAPABILITY_PIPE_LOST'); }
  return {send, receive, registerSession, armEvents, lost, failed: () => failed};
}
