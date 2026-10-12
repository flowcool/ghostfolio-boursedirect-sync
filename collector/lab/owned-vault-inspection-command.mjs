// Anonymous private stdio only. The pinned supervisor owns SSH and resource facts.
import {privateChannel} from '../private-channel.mjs';
import {inspectOwnedVault} from '../owned-vault-inspection.mjs';
import {sshCliTransport} from '../bitwarden-cli.mjs';

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
    // CLI stdout, including the item/seed, stays inside this trusted worker.
    // The supervisor receives attestation/stop metadata and the final projection only.
    transport: sshCliTransport(input.destination)});
  await channel.send({action: 'complete', selected, session_logged_out: true, totp_requests: 0});
} catch {
  await channel.send({action: 'refused', code: 'OWNED_VAULT_INSPECTION_REFUSED'}).catch(() => {});
  process.exitCode = 1;
} finally {
  try {channel.releaseInput();} catch {process.exitCode = 1;}
  process.stdin.destroy();
}
