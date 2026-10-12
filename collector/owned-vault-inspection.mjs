// Metadata-only composition over the existing owned CLI adapter. No broker or TOTP.
import {bitwardenCli} from './bitwarden-cli.mjs';
import {vaultWorker} from './vault-worker.mjs';

export async function inspectOwnedVault({configuration, containerId, egressProxy, credentials,
  attest, stopOwned, transport, now = () => Math.floor(Date.now() / 1000)}) {
  if (configuration?.schema_version !== 3) throw new Error('OWNED_VAULT_INSPECTION_REFUSED');
  const adapter = bitwardenCli({configuration, containerId, egressProxy, attest, stopOwned, transport});
  const worker = vaultWorker({configuration, ...adapter, appdata: '/data', now});
  try {return await worker.initialize(credentials);}
  catch {throw new Error('OWNED_VAULT_INSPECTION_REFUSED');}
  finally {await worker.close();}
}
