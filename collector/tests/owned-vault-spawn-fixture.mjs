// Test preload only. Stand in for SSH inside the worker; never create a process.
import fs from 'node:fs';
import child from 'node:child_process';
import {syncBuiltinESMExports} from 'node:module';
import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';

const trace = process.env.SYNTHETIC_VAULT_TRACE;
if (typeof trace !== 'string' || !trace.startsWith('/')) throw new Error('TEST_FIXTURE_INVALID');
const calls = [], fakePid = 100000000;
process.kill = () => {throw new Error('TEST_SIGNAL_FORBIDDEN');};
child.spawn = (executable, args) => {
  if (executable !== '/usr/bin/ssh' || JSON.stringify(args.slice(0, 10)) !== JSON.stringify([
    '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=yes', '--', 'vault-fixture', args[9]])
      || args.length !== 10 || typeof args[9] !== 'string') throw new Error('TEST_PROCESS_FORBIDDEN');
  const command = args[9];
  const mode = command.includes("'/usr/bin/sha256sum' '/usr/local/bin/bw'") ? 'hash'
    : /'vault-cli' '(version|server|login|unlock|sync|lookup|logout|status)'/.exec(command)?.[1];
  if (!mode || !command.startsWith("'/usr/bin/docker' 'exec' '-i' '" + 'a'.repeat(64) + "' '/usr/bin/env' '-i'"))
    throw new Error('TEST_PROCESS_FORBIDDEN');
  calls.push(mode); fs.writeFileSync(trace, JSON.stringify(calls), {mode: 0o600});
  const fault = process.env.SYNTHETIC_VAULT_FAULT;
  const item = {id: '11111111-1111-4111-8111-111111111111', name: 'boursedirect.fr', type: 1,
    login: {username: 'SYNTHETIC', password: 'SYNTHETIC_PASSWORD',
      uris: [{uri: 'https://www.boursedirect.fr/synthetic'}, {uri: 'https://alias.synthetic.invalid/'}],
      totp: 'otpauth://totp/Synthetic?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&algorithm=SHA1&digits=6&period=30'}};
  const output = {hash: (fault === 'hash' ? 'd' : 'c').repeat(64) + '  /usr/local/bin/bw\n',
    version: 'synthetic-1', unlock: 'SYNTHETIC_SESSION', lookup: JSON.stringify([item]),
    status: JSON.stringify({status: fault === 'status' ? 'locked' : 'unauthenticated'})}[mode] ?? '';
  const result = new EventEmitter(); result.pid = fakePid;
  result.stdin = new PassThrough(); result.stdout = new PassThrough(); result.stderr = new PassThrough();
  result.stdin.resume();
  result.stdin.on('finish', () => setImmediate(() => {
    result.stdout.end(output); result.stderr.end();
    result.emit('close', mode === 'logout' && fault === 'logout' ? 1 : 0);
  }));
  return result;
};
syncBuiltinESMExports();
