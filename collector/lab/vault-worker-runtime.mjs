// Network-none synthetic runtime entry. Private stdout is exclusively IPC.
import fs from 'node:fs';
import {vaultWorker} from '../vault-worker.mjs';
import {privateChannel} from '../private-channel.mjs';
import {executePrivate, verifyExecutable} from '../private-process.mjs';

process.umask(0o077);
const ipc = privateChannel({input: process.stdin, output: process.stdout, fence: () => {process.exitCode = 1;}});
try {
  const input = await ipc.receive();
  fs.mkdirSync('/vault/appdata', {recursive: true, mode: 0o700});
  const worker = vaultWorker({configuration: input.configuration, appdata: '/vault/appdata',
    execute: executePrivate, verifyExecutable, now: () => Math.floor(Date.now() / 1000)});
  const selected = await worker.initialize(input.credentials);
  let next = ipc.receive(); await ipc.send({selected});
  const request = await next;
  const response = await worker.code(request, input.expected);
  next = ipc.receive(); await ipc.send(response);
  const finish = await next;
  if (JSON.stringify(finish) !== '{"finish":true}') throw new Error();
  const calls = JSON.parse(fs.readFileSync('/vault/appdata/calls.json'));
  await ipc.send({commands: calls.length, totpCalls: calls.filter(x => x[1] === 'totp').length, online_ready: false});
} catch {await ipc.send({error: 'VAULT_RUNTIME_FAILED'}).catch(() => {}); process.exitCode = 1;}
process.stdin.destroy();
