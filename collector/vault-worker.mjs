// Fixed-command worker engine. Only its trusted launcher can supply execution.
import {selectWorkerItem, selectAliasedWorkerItem, selectNamedWorkerItem, inspectNamedVaultItem, inspectConfiguredVaultItem, validateProviderCode} from './credential-provider.mjs';
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
    if (![1, 2, 3, 4, 5].includes(value.schema_version)) throw new Error();
    const url = new URL(value.vaultOrigin);
    if (url.protocol !== 'https:' || url.origin !== value.vaultOrigin || url.username || url.password) throw new Error();
    if ([1, 4].includes(value.schema_version)) {
      exact(value.binding, value.schema_version === 4
        ? ['itemId', 'name', 'uri', 'principalHash', 'uriAliasesSha256', 'accountConfig']
        : ['itemId', 'name', 'uri', 'principalHash', 'accountConfig']);
      uuid(value.binding.itemId); boundedText(value.binding.name); brokerUrl(value.binding.uri); hash(value.binding.principalHash);
      if (value.schema_version === 4) hash(value.binding.uriAliasesSha256);
    } else {
      exact(value.binding, [3, 5].includes(value.schema_version) ? ['name'] : ['name', 'accountConfig']);
      if (value.schema_version === 5) boundedText(value.binding.name);
      else if (value.binding.name !== 'boursedirect.fr') throw new Error();
    }
    if (![3, 5].includes(value.schema_version)) {
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

export function vaultWorker({configuration, execute, verifyExecutable, now, appdata, bindAcquisition}) {
  const config = providerConfiguration(configuration);
  if ([execute, verifyExecutable, now].some(x => typeof x !== 'function')
      || typeof appdata !== 'string' || !appdata.startsWith('/')
      || bindAcquisition!==undefined&&(config.schema_version!==5||typeof bindAcquisition!=='function')) throw new Error('VAULT_CONFIG_INVALID');
  let initialized = false, used = false, failed = false, session, selected, clock, acquisitionBound = false;
  let closing = false, closed = false, cleanupAttempted = false, cleanupVerified = false;
  let operationPending = false, loginReserved = false;
  const base = {PATH: '/usr/bin:/bin', HOME: appdata, BITWARDENCLI_APPDATA_DIR: appdata};
  function sample() {
    const time = now();
    if (!Number.isSafeInteger(time) || time < 0 || (clock !== undefined && time < clock)) throw new Error();
    clock = time; return time;
  }
  async function command(args, env) {
    if (failed && !closing) throw new Error();
    const result = await execute(config.cli.path, args, env);
    if (failed && !closing || !result || result.status !== 0 || typeof result.stdout !== 'string'
        || typeof result.stderr !== 'string' || Buffer.byteLength(result.stdout) > 262144
        || Buffer.byteLength(result.stderr) > 32768) throw new Error();
    return result.stdout.trim();
  }
  async function initialize(credentials) {
    if (initialized || failed || closing || closed) {failed = true; throw new Error('VAULT_WORKER_FAILED');}
    initialized = true;
    operationPending = true;
    try {
      exact(credentials, ['BW_CLIENTID', 'BW_CLIENTSECRET', 'BW_PASSWORD']);
      Object.values(credentials).forEach(boundedText);
      if (await verifyExecutable(config.cli) !== true) throw new Error();
      if (await command(['--version'], base) !== config.cli.version) throw new Error();
      await command(['config', 'server', config.vaultOrigin], base);
      loginReserved = true;
      await command(['login', '--apikey'], {...base, BW_CLIENTID: credentials.BW_CLIENTID, BW_CLIENTSECRET: credentials.BW_CLIENTSECRET});
      session = await command(['unlock', '--passwordenv', 'BW_PASSWORD', '--raw'], {...base, BW_PASSWORD: credentials.BW_PASSWORD});
      boundedText(session);
      await command(['sync'], {...base, BW_SESSION: session});
      const raw = await command([1, 4].includes(config.schema_version) ? ['get', 'item', config.binding.itemId]
        : ['list', 'items', '--search', config.binding.name], {...base, BW_SESSION: session});
      // Full item/seed is scoped to worker memory and is never sent through IPC.
      const items=JSON.parse(raw);
      if(bindAcquisition!==undefined) {
        const metadata=inspectConfiguredVaultItem(items,config.binding,config.cli.defaultsVerified);
        const binding=await bindAcquisition(structuredClone(metadata));
        const checked=providerConfiguration({...config,schema_version:4,binding});
        selected=selectAliasedWorkerItem(items.find(item=>item?.id===metadata.itemId),checked.binding,config.cli.defaultsVerified);
        acquisitionBound=true;
      } else {
      selected = (config.schema_version === 4 ? selectAliasedWorkerItem : config.schema_version === 1 ? selectWorkerItem
        : config.schema_version === 2 ? selectNamedWorkerItem : config.schema_version === 5 ? inspectConfiguredVaultItem : inspectNamedVaultItem)(
        items, config.binding, config.cli.defaultsVerified);
      }
      if ([3, 5].includes(config.schema_version)&&!acquisitionBound) {
        cleanupAttempted = true;
        await command(['logout'], base);
        session = undefined;
        const status = JSON.parse(await command(['status'], base));
        if (status?.status !== 'unauthenticated' || ['userId', 'userEmail', 'lastSync'].some(
          key => status[key] !== undefined && status[key] !== null)) throw new Error();
        cleanupVerified = true;
      }
      return structuredClone(selected);
    } catch {failed = true; selected = session = undefined; throw new Error('VAULT_WORKER_FAILED');}
    finally {operationPending = false;}
  }
  async function code(request, expected) {
    if ([3, 5].includes(config.schema_version)&&!acquisitionBound || !initialized || !selected || used || failed || closing || closed) {
      failed = true; selected = session = undefined; throw new Error('VAULT_WORKER_FAILED');
    }
    used = true;
    operationPending = true;
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
    finally {selected = session = undefined; operationPending = false;}
  }
  async function close() {
    if (closed && cleanupVerified) return;
    if (closing || operationPending || cleanupAttempted && !cleanupVerified) throw new Error('VAULT_CLEANUP_FAILED');
    closing = true;
    try {
      if (!cleanupVerified && loginReserved) {
        cleanupAttempted = true;
        await command(['logout'], base);
        const status = JSON.parse(await command(['status'], base));
        if (status?.status !== 'unauthenticated' || ['userId', 'userEmail', 'lastSync'].some(
          key => status[key] !== undefined && status[key] !== null)) throw new Error();
      }
      cleanupVerified = true;
    } catch {failed = true; throw new Error('VAULT_CLEANUP_FAILED');}
    finally {session = selected = undefined; closed = true; closing = false;}
  }
  return {initialize, code, close, status: () => ({initialized, used, failed, online_ready: false})};
}
