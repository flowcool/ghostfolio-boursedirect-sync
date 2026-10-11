// Public output is fixed codes/counts only. Native credentials never reach stdout.
import fs from 'node:fs';
import {nativeVaultExecution, retainNativeBinding} from './native-vault.mjs';

process.umask(0o077);
const codes = new Set(['NATIVE_VAULT_CONFIG_INVALID', 'NATIVE_VAULT_BINDING_REFUSED',
  'VAULT_CONFIG_INVALID', 'VAULT_WORKER_FAILED', 'VAULT_CLEANUP_FAILED', 'SOURCE_AUTHENTICATED_REPLAY_NOT_QUALIFIED']);
try {
  const [action, ...extra] = process.argv.slice(2);
  if (!['inspect', 'connect'].includes(action) || extra.length) throw new Error('NATIVE_VAULT_CONFIG_INVALID');
  const pin = JSON.parse(fs.readFileSync('/opt/app/cli-pin.json', 'utf8'));
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith('BW_') || key.startsWith('BD_')));
  for (const key of Object.keys(env)) delete process.env[key];
  const appdata = fs.mkdtempSync('/data/session-');
  const selected = await nativeVaultExecution({env, pin, appdata});
  retainNativeBinding('/state', env, selected);
  // Actual source roles and the guarded broker driver remain qualification gates.
  // This command never treats vault access as authority to submit a broker password.
  if (action === 'connect') throw new Error('SOURCE_AUTHENTICATED_REPLAY_NOT_QUALIFIED');
  console.log(JSON.stringify({code: 'NATIVE_VAULT_INSPECTION_VERIFIED', matched_items: 1,
    broker_uri_count: selected.broker_uri_count, session_logged_out: true, online_ready: false}));
} catch (error) {
  const code = codes.has(error.message) ? error.message : 'NATIVE_VAULT_EXECUTION_FAILED';
  console.log(JSON.stringify({code, online_ready: false}));
  process.exitCode = code === 'SOURCE_AUTHENTICATED_REPLAY_NOT_QUALIFIED' ? 2 : 1;
}
