// Source-owned seam to an already provisioned, durably owned CLI container.
// Infra supplies runtime/access facts; no host, SSH, SOPS or network wiring here.
import fs from 'node:fs';
import {isIP} from 'node:net';
import {providerConfiguration} from './vault-worker.mjs';
import {selectNamedWorkerItem, inspectNamedVaultItem} from './credential-provider.mjs';
import {executePrivate} from './private-process.mjs';

const shim = fs.readFileSync(new URL('./bitwarden-cli.sh', import.meta.url), 'utf8');
const base = {PATH: '/usr/bin:/bin', HOME: '/data', BITWARDENCLI_APPDATA_DIR: '/data'};

export function sshCliTransport(destination, execute = executePrivate) {
  if (typeof destination !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.@-]{0,252}$/.test(destination)
      || typeof execute !== 'function') throw new Error('CLI_ADAPTER_INVALID');
  const quote = value => "'" + value.replaceAll("'", "'\\''") + "'";
  return (executable, args, env, timeout, input) => {
    if (executable !== '/usr/bin/docker') throw new Error('CLI_ADAPTER_INVALID');
    return execute('/usr/bin/ssh', ['-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
      '-o', 'StrictHostKeyChecking=yes', '--', destination, [executable, ...args].map(quote).join(' ')],
    env, timeout, input);
  };
}

export function bitwardenCli({configuration, containerId, attest, stopOwned, transport = executePrivate, egressProxy}) {
  const config = providerConfiguration(configuration);
  if (config.cli.path !== '/usr/local/bin/bw' || !/^[0-9a-f]{64}$/.test(containerId)
      || [attest, stopOwned, transport].some(x => typeof x !== 'function')) throw new Error('CLI_ADAPTER_INVALID');
  if (egressProxy !== undefined) {
    let proxy;
    try {proxy = new URL(egressProxy);} catch {throw new Error('CLI_ADAPTER_INVALID');}
    if (typeof egressProxy !== 'string' || isIP(proxy.hostname) !== 4
        || egressProxy !== 'http://' + proxy.hostname + ':8080') throw new Error('CLI_ADAPTER_INVALID');
  }
  // A literal independently attested endpoint needs no worker DNS. Infrastructure
  // must deny every direct route; setting a proxy alone is never confinement.
  const executionEnv = {...base, ...(egressProxy === undefined ? {} : {https_proxy: egressProxy})};
  const steps = [
    [['--version'], 'version', []],
    [['config', 'server', config.vaultOrigin], 'server', []],
    [['login', '--apikey'], 'login', ['BW_CLIENTID', 'BW_CLIENTSECRET']],
    [['unlock', '--passwordenv', 'BW_PASSWORD', '--raw'], 'unlock', ['BW_PASSWORD']],
    [['sync'], 'sync', ['BW_SESSION']],
    [config.schema_version === 1 ? ['get', 'item', config.binding.itemId]
      : ['list', 'items', '--search', config.binding.name], config.schema_version === 1 ? 'item' : 'lookup', ['BW_SESSION']],
    [['get', 'totp', config.binding.itemId], 'totp', ['BW_SESSION']],
  ];
  if (config.schema_version === 3) {
    steps[6] = [['logout'], 'logout', []];
    steps.push([['status'], 'status', []]); // No TOTP command in inspection mode.
  }
  let index = 0, verified = false, busy = false, failed = false, stopping;
  async function refuse() {
    failed = true;
    stopping ??= Promise.resolve().then(() => stopOwned(containerId));
    try {await stopping;} catch { /* Owner retains uncertain receipt. */ }
    throw new Error('CLI_ADAPTER_FAILED');
  }
  async function invoke(args, input) {
    // Trusted owner must prove full-ID receipt, image/CLI pin, private appdata,
    // minimal container env, disabled logs/core dumps and qualified egress.
    if (await attest(containerId, config.cli) !== true || failed) throw new Error();
    const result = await transport('/usr/bin/docker', ['exec', '-i', containerId, '/usr/bin/env', '-i',
      ...Object.entries(executionEnv).map(([name, value]) => name + '=' + value), ...args],
    {PATH: '/usr/bin:/bin'}, 45000, input);
    if (failed || !result || result.status !== 0 || typeof result.stdout !== 'string'
        || typeof result.stderr !== 'string' || Buffer.byteLength(result.stdout) > 262144
        || Buffer.byteLength(result.stderr) > 32768) throw new Error();
    return result;
  }
  async function verifyExecutable(pin) {
    if (verified || busy || failed || JSON.stringify(pin) !== JSON.stringify(config.cli)) return refuse();
    busy = true;
    try {
      const result = await invoke(['/usr/bin/sha256sum', '/usr/local/bin/bw'], Buffer.alloc(0));
      if (result.stdout.trim() !== config.cli.sha256 + '  /usr/local/bin/bw') throw new Error();
      verified = true; return true;
    } catch {return refuse();} finally {busy = false;}
  }
  async function execute(path, args, env) {
    if (!verified || busy || failed) return refuse();
    busy = true;
    try {
      const step = steps[index++]; // Reserve before attestation/transport awaits.
      if (!step || path !== config.cli.path || JSON.stringify(args) !== JSON.stringify(step[0])
          || !env || Object.keys(env).length !== 3 + step[2].length
          || Object.entries(base).some(([key, value]) => env[key] !== value)) throw new Error();
      const input = step[2].map(key => {
        const value = env[key];
        if (typeof value !== 'string' || !value || Buffer.byteLength(value) > 4096 || /[\x00-\x1f\x7f]/.test(value)) throw new Error();
        return Buffer.from(value).toString('base64') + '\n';
      }).join('');
      const extra = step[1] === 'server' ? [config.vaultOrigin] : step[1] === 'lookup' ? [config.binding.name]
        : ['item', 'totp'].includes(step[1]) ? [step[0][2]] : [];
      const result = await invoke(['/bin/sh', '-c', shim, 'vault-cli', step[1], ...extra], Buffer.from(input));
      if (step[1] === 'lookup' && config.schema_version !== 3) {
        steps[6][0][2] = selectNamedWorkerItem(JSON.parse(result.stdout), config.binding, config.cli.defaultsVerified).itemId;
      } else if (step[1] === 'lookup') {
        inspectNamedVaultItem(JSON.parse(result.stdout), config.binding, config.cli.defaultsVerified);
      }
      return result;
    } catch {return refuse();} finally {busy = false;}
  }
  return {verifyExecutable, execute};
}
