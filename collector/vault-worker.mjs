// Fixed-command worker engine. Only its trusted launcher can supply execution.
import {selectWorkerItem, selectAliasedWorkerItem, selectNamedWorkerItem, inspectNamedVaultItem, validateProviderCode} from './credential-provider.mjs';
import {brokerUrl} from './core.mjs';

function exact(value, keys) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || Object.keys(value).length !== keys.length || keys.some(k => !Object.hasOwn(value, k))) throw new Error();
}
function boundedText(value) {
  if (typeof value !== 'string' || !value || Buffer.byteLength(value) > 4096 || /[\x00-\x1f\x7f]/.test(value)) throw new Error();
}
function uuid(value) {if (typeof value !== 'string' || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value)) throw new Error();}
function hash(value) {if (typeof value !== 'string' || !/^[0-9a-f]{64}$/.test(value)) throw new Error();}
function freeze(value) {Object.values(value).forEach(x => {if (x && typeof x === 'object') freeze(x);}); return Object.freeze(value);}

export function providerConfiguration(value) {
  try {
    exact(value, ['schema_version', 'vaultOrigin', 'binding', 'cli']);
    if (![1, 2, 3, 4].includes(value.schema_version)) throw new Error();
    const url = new URL(value.vaultOrigin);
    if (url.protocol !== 'https:' || url.origin !== value.vaultOrigin || url.username || url.password) throw new Error();
    if ([1, 4].includes(value.schema_version)) {
      exact(value.binding, value.schema_version === 4
        ? ['itemId', 'name', 'uri', 'principalHash', 'uriAliasesSha256', 'accountConfig']
        : ['itemId', 'name', 'uri', 'principalHash', 'accountConfig']);
      uuid(value.binding.itemId); boundedText(value.binding.name); brokerUrl(value.binding.uri); hash(value.binding.principalHash);
      if (value.schema_version === 4) hash(value.binding.uriAliasesSha256);
    } else {
      exact(value.binding, value.schema_version === 3 ? ['name'] : ['name', 'accountConfig']);
      if (value.binding.name !== 'boursedirect.fr') throw new Error();
    }
    if (value.schema_version !== 3) {
      exact(value.binding.accountConfig, ['path', 'sha256']); boundedText(value.binding.accountConfig.path); hash(value.binding.accountConfig.sha256);
      if (!value.binding.accountConfig.path.startsWith('/')) throw new Error();
    }
    exact(value.cli, ['path', 'sha256', 'version', 'defaultsVerified']);
    if (typeof value.cli.path !== 'string' || !/^\/[A-Za-z0-9_./-]+$/.test(value.cli.path)) throw new Error();
    hash(value.cli.sha256); boundedText(value.cli.version);
    if (typeof value.cli.defaultsVerified !== 'boolean') throw new Error();
    return freeze(structuredClone(value));
  } catch {throw new Error('VAULT_CONFIG_INVALID');}
}

export function vaultWorker({configuration, execute, verifyExecutable, now, appdata}) {
  const config = providerConfiguration(configuration);
  if ([execute, verifyExecutable, now].some(x => typeof x !== 'function')
      || typeof appdata !== 'string' || !appdata.startsWith('/')) throw new Error('VAULT_CONFIG_INVALID');
  let initialized = false, used = false, failed = false, session, selected, clock;
  function sample() {
    const time = now();
    if (!Number.isSafeInteger(time) || time < 0 || (clock !== undefined && time < clock)) throw new Error();
    clock = time; return time;
  }
  async function command(args, env) {
    const result = await execute(config.cli.path, args, env);
    if (!result || result.status !== 0 || typeof result.stdout !== 'string'
        || typeof result.stderr !== 'string' || Buffer.byteLength(result.stdout) > 262144
        || Buffer.byteLength(result.stderr) > 32768) throw new Error();
    return result.stdout.trim();
  }
  async function initialize(credentials) {
    if (initialized || failed) {failed = true; throw new Error('VAULT_WORKER_FAILED');}
    initialized = true;
    try {
      exact(credentials, ['BW_CLIENTID', 'BW_CLIENTSECRET', 'BW_PASSWORD']);
      Object.values(credentials).forEach(boundedText);
      if (await verifyExecutable(config.cli) !== true) throw new Error();
      const base = {PATH: '/usr/bin:/bin', HOME: appdata, BITWARDENCLI_APPDATA_DIR: appdata};
      if (await command(['--version'], base) !== config.cli.version) throw new Error();
      await command(['config', 'server', config.vaultOrigin], base);
      await command(['login', '--apikey'], {...base, BW_CLIENTID: credentials.BW_CLIENTID, BW_CLIENTSECRET: credentials.BW_CLIENTSECRET});
      session = await command(['unlock', '--passwordenv', 'BW_PASSWORD', '--raw'], {...base, BW_PASSWORD: credentials.BW_PASSWORD});
      boundedText(session);
      await command(['sync'], {...base, BW_SESSION: session});
      const raw = await command([1, 4].includes(config.schema_version) ? ['get', 'item', config.binding.itemId]
        : ['list', 'items', '--search', config.binding.name], {...base, BW_SESSION: session});
      // Full item/seed is scoped to worker memory and is never sent through IPC.
      selected = (config.schema_version === 4 ? selectAliasedWorkerItem : config.schema_version === 1 ? selectWorkerItem
        : config.schema_version === 2 ? selectNamedWorkerItem : inspectNamedVaultItem)(
        JSON.parse(raw), config.binding, config.cli.defaultsVerified);
      if (config.schema_version === 3) {
        await command(['logout'], base);
        session = undefined;
        const status = JSON.parse(await command(['status'], base));
        if (status?.status !== 'unauthenticated' || ['userId', 'userEmail', 'lastSync'].some(
          key => status[key] !== undefined && status[key] !== null)) throw new Error();
      }
      return structuredClone(selected);
    } catch {failed = true; selected = session = undefined; throw new Error('VAULT_WORKER_FAILED');}
  }
  async function code(request, expected) {
    if (config.schema_version === 3 || !initialized || !selected || used || failed) {
      failed = true; selected = session = undefined; throw new Error('VAULT_WORKER_FAILED');
    }
    used = true;
    try {
      exact(request, ['runNonce', 'stageNonce']); exact(expected, ['runNonce', 'stageNonce']);
      uuid(expected.runNonce); uuid(expected.stageNonce);
      if (request.runNonce !== expected.runNonce || request.stageNonce !== expected.stageNonce) throw new Error();
      const startedAt = sample(); if (30 - startedAt % 30 < 5) throw new Error();
      const value = await command(['get', 'totp', selected.itemId],
        {PATH: '/usr/bin:/bin', HOME: appdata, BITWARDENCLI_APPDATA_DIR: appdata, BW_SESSION: session});
      if (failed) throw new Error();
      const completedAt = sample();
      const response = {...expected, code: value, startedAt, completedAt, profile: selected.profile};
      validateProviderCode(response, expected, completedAt);
      return response;
    } catch {failed = true; throw new Error('VAULT_WORKER_FAILED');}
    finally {selected = session = undefined;}
  }
  return {initialize, code, status: () => ({initialized, used, failed, online_ready: false})};
}
