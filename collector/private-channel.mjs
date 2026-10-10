// Anonymous trusted stdio only. No socket/path selection or public logging.
import {parseDocument} from 'yaml';
export const PRIVATE_LIMIT = 32768;

export function privateChannel({input, output, fence, timeoutMs = 45000}) {
  if (!input?.on || !output?.write || typeof fence !== 'function'
      || !Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 45000) throw new Error('PRIVATE_CHANNEL_INVALID');
  let buffer = Buffer.alloc(0), waiting, failed = false, closed = false;
  const decoder = new TextDecoder('utf-8', {fatal: true});
  function die() {
    if (!failed) {
      failed = true; buffer = Buffer.alloc(0);
      if (waiting) {clearTimeout(waiting.timer); waiting.reject(new Error('PRIVATE_CHANNEL_FAILED')); waiting = undefined;}
      try {fence();} catch { /* No transport revival after cleanup failure. */ }
    }
  }
  function data(bytes) {
    try {
      if (failed || closed || !Buffer.isBuffer(bytes) || buffer.length + bytes.length > PRIVATE_LIMIT) throw new Error();
      buffer = Buffer.concat([buffer, bytes]);
      const end = buffer.indexOf(10);
      if (end < 0) return;
      // Exactly one expected frame. Unsolicited, coalesced or trailing input fences.
      if (!waiting || end !== buffer.length - 1 || end === 0) throw new Error();
      const raw = decoder.decode(buffer.subarray(0, end));
      const doc = parseDocument(raw, {uniqueKeys: true});
      if (doc.errors.length || doc.warnings.length) throw new Error();
      const value = JSON.parse(raw);
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error();
      const item = waiting; waiting = undefined; buffer = Buffer.alloc(0);
      clearTimeout(item.timer); item.resolve(value);
    } catch {die();}
  }
  input.on('data', data);
  const lost = () => {if (!closed) die();};
  for (const event of ['error', 'end', 'close']) input.on(event, lost);
  output.on?.('error', die);
  function receive() {
    if (failed || closed || waiting) {die(); return Promise.reject(new Error('PRIVATE_CHANNEL_FAILED'));}
    return new Promise((resolve, reject) => {
      waiting = {resolve, reject, timer: setTimeout(die, timeoutMs)};
    });
  }
  async function send(value) {
    try {
      if (failed || closed) throw new Error();
      const raw = Buffer.from(JSON.stringify(value) + '\n');
      if (raw.length > PRIVATE_LIMIT) throw new Error();
      await new Promise((resolve, reject) => output.write(raw, error => error ? reject(error) : resolve()));
      if (failed) throw new Error();
    } catch {die(); throw new Error('PRIVATE_CHANNEL_FAILED');}
  }
  // Caller must verify owned process exit before closing its live pipe.
  function close(exited) {
    if (exited !== true || waiting) {die(); throw new Error('PRIVATE_CHANNEL_CLOSE_REJECTED');}
    closed = true; buffer = Buffer.alloc(0); output.end(); input.destroy();
  }
  function releaseInput() {
    if (failed || closed || waiting || buffer.length) throw new Error('PRIVATE_CHANNEL_FAILED');
    input.removeListener('data', data);
    for (const event of ['error', 'end', 'close']) input.removeListener(event, lost);
    closed = true;
  }
  return {receive, send, failed: () => failed, close, releaseInput};
}
