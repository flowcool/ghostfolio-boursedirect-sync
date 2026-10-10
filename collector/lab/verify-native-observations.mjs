// Pure bounded saved-evidence recheck; cannot launch a browser or Docker.
import fs from 'node:fs';
import {nativeVerdict} from './native-verdict.mjs';
let result;
try {
  const buffer = Buffer.alloc(1048577);
  let used = 0, count;
  while (used < buffer.length && (count = fs.readSync(0, buffer, used, buffer.length - used, null)) > 0) used += count;
  if (used > 1048576) throw new Error();
  const raw = buffer.subarray(0, used);
  const value = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(raw));
  result = nativeVerdict(value);
} catch {result = {passed: false, failures: ['NATIVE_EVIDENCE_INVALID']};}
console.log(JSON.stringify(result));
if (!result.passed) process.exitCode = 1;
