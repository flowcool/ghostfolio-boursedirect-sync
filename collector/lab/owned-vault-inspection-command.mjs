// Anonymous private stdio only. The pinned supervisor owns SSH and resource facts.
import {privateChannel} from '../private-channel.mjs';
import {inspectOwnedVault} from '../owned-vault-inspection.mjs';

process.umask(0o077);
let fenced = false;
const channel = privateChannel({input: process.stdin, output: process.stdout,
  fence: () => {fenced = true; process.exitCode = 1;}});
async function request(operation) {
  if (fenced) throw new Error();
  const response = channel.receive();
  await channel.send(operation);
  const value = await response;
  if (fenced || JSON.stringify(Object.keys(value).sort()) !== '["result"]') throw new Error();
  return value.result;
}
try {
  const input = await channel.receive();
  const selected = await inspectOwnedVault({...input,
    attest: (containerId, pin) => request({action: 'attest', containerId, pin}),
    stopOwned: containerId => request({action: 'stop', containerId}),
    transport: (executable, args, env, timeout, bytes) => request({action: 'transport', executable, args, env, timeout,
      input: bytes.toString('base64')})});
  await channel.send({action: 'complete', selected, session_logged_out: true, totp_requests: 0});
} catch {
  await channel.send({action: 'refused', code: 'OWNED_VAULT_INSPECTION_REFUSED'}).catch(() => {});
  process.exitCode = 1;
} finally {
  try {channel.releaseInput();} catch {process.exitCode = 1;}
  process.stdin.destroy();
}
