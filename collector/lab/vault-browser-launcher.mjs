// Starts the collector with credentials in its initial environment, inside
// the isolated runtime. Container metadata and browser env remain secret-free.
import {spawn} from 'node:child_process';
import {privateChannel} from '../private-channel.mjs';
import {collectorEnvironment} from '../private-process.mjs';
const ipc = privateChannel({input: process.stdin, output: process.stdout, fence: () => {process.exitCode = 1;}});
try {
  const input = await ipc.receive();
  const child = spawn(process.execPath, ['/home/fixture/proof/lab/vault-collector-runtime.mjs'],
    {env: collectorEnvironment(input.selected, '/home/fixture'), stdio: ['pipe', 'inherit', 'inherit']});
  child.stdin.write(JSON.stringify({expected: input.expected, allocation: input.allocation, scenario: input.scenario,
    binding: input.selected, chromeVersion: input.chromeVersion}) + '\n');
  ipc.releaseInput();
  process.stdin.pipe(child.stdin);
  child.on('error', () => {process.exitCode = 1; process.stdin.destroy();});
  child.on('exit', code => {process.exitCode = code ?? 1; process.stdin.destroy();});
} catch {await ipc.send({error: 'COLLECTOR_LAUNCH_FAILED'}).catch(() => {}); process.exitCode = 1; process.stdin.destroy();}
