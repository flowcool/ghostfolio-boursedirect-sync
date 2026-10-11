import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {nativeVaultEnvironment, nativeVaultExecution, retainNativeBinding} from '../native-vault.mjs';
import {vaultWorker} from '../vault-worker.mjs';

const env = {BW_SERVER: 'https://vault.bitwarden.com', BW_ITEM_NAME: 'My broker',
  BW_CLIENTID: 'SYNTHETIC_ID', BW_CLIENTSECRET: 'SYNTHETIC_API_SECRET', BW_PASSWORD: 'SYNTHETIC_MASTER'};
const pin = {path: '/usr/local/bin/bw', sha256: 'a'.repeat(64), version: 'synthetic', defaultsVerified: true};
const item = {id: '00000000-0000-4000-8000-000000000001', name: env.BW_ITEM_NAME, type: 1,
  login: {username: 'SYNTHETIC_LOGIN', password: 'SYNTHETIC_PASSWORD',
    uris: [{uri: 'https://www.boursedirect.fr/fr/login'}, {uri: 'https://boursedirect.fr'}],
    totp: 'otpauth://totp/synthetic?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&algorithm=SHA1&digits=6&period=30'}};
function fixture(fault) {
  const calls = [];
  const execute = async (executable, args, childEnv) => {
    calls.push({executable, args, env: childEnv});
    if (args[0] === fault) return {status: 1, stdout: '', stderr: 'PRIVATE_SYNTHETIC_ERROR'};
    const stdout = args[0] === '--version' ? pin.version : args[0] === 'unlock' ? 'SYNTHETIC_SESSION'
      : args[0] === 'list' ? JSON.stringify([item]) : args[1] === 'item' ? JSON.stringify(item)
        : args[1] === 'totp' ? '123456' : args[0] === 'status' ? JSON.stringify({status: 'unauthenticated'}) : '';
    return {status: 0, stdout, stderr: ''};
  };
  return {calls, options: {env, pin, appdata: '/synthetic/appdata', execute, verify: () => true, now: () => 120}};
}
test('native ENV resolves configured exact name and logs out without credential export', async () => {
  const f = fixture(), selected = await nativeVaultExecution(f.options);
  assert.equal(selected.itemId, item.id); assert.equal(selected.uri_count, 2);
  assert.equal(selected.login, undefined); assert.equal(selected.password, undefined);
  assert.deepEqual(f.calls.map(x => x.args[0]), ['--version', 'config', 'login', 'unlock', 'sync', 'list', 'logout', 'status']);
  assert.deepEqual(f.calls[5].args, ['list', 'items', '--search', env.BW_ITEM_NAME]);
  assert.ok(f.calls.every(x => !JSON.stringify(x.args).includes('SYNTHETIC_MASTER')));
  assert.ok(f.calls.every(x => !Object.hasOwn(x.env, 'BW_CLIENTSECRET') || x.args[0] === 'login'));
});
for (const fault of ['login', 'unlock', 'sync', 'list']) test('native failure at ' + fault + ' cleans session once without retry', async () => {
  const f = fixture(fault);
  await assert.rejects(nativeVaultExecution(f.options), /^Error: VAULT_WORKER_FAILED$/);
  assert.equal(f.calls.filter(x => x.args[0] === 'login').length, 1);
  assert.equal(f.calls.filter(x => x.args[0] === 'logout').length, 1);
  assert.equal(f.calls.at(-1).args[0], 'status');
});
test('failed executable verification never invokes an unverified binary for cleanup', async () => {
  const f = fixture(); f.options.verify = () => false;
  await assert.rejects(nativeVaultExecution(f.options), /VAULT_WORKER_FAILED/);
  assert.equal(f.calls.length, 0);
});
test('uncertain logout is fenced without retry', async () => {
  const f = fixture('logout');
  await assert.rejects(nativeVaultExecution(f.options), /^Error: VAULT_CLEANUP_FAILED$/);
  assert.equal(f.calls.filter(x => x.args[0] === 'logout').length, 1);
});
test('qualified in-process consumer receives pinned credentials and one delayed code with final logout', async () => {
  const f = fixture(), metadata = await nativeVaultExecution(f.options);
  f.calls.length = 0;
  const binding = {vaultOrigin: env.BW_SERVER, name: env.BW_ITEM_NAME, ...metadata};
  const nonce = {runNonce: '00000000-0000-4000-8000-000000000002', stageNonce: '00000000-0000-4000-8000-000000000003'};
  const result = await nativeVaultExecution({...f.options, binding,
    accountConfig: {path: '/synthetic/accounts.yaml', sha256: 'b'.repeat(64)},
    consume: async (selected, code) => {
      assert.equal(selected.login, item.login.username); assert.equal(selected.password, item.login.password);
      assert.equal(f.calls.filter(x => x.args[1] === 'totp').length, 0);
      assert.equal((await code(nonce, nonce)).code, '123456');
      return {accepted: true};
    }});
  assert.deepEqual(result, {accepted: true});
  assert.deepEqual(f.calls.filter(x => x.args[0] === 'get').map(x => x.args), [['get', 'item', item.id], ['get', 'totp', item.id]]);
  assert.deepEqual(f.calls.slice(-2).map(x => x.args[0]), ['logout', 'status']);
});
test('consumer failure still logs out and does not request a TOTP', async () => {
  const f = fixture(), metadata = await nativeVaultExecution(f.options); f.calls.length = 0;
  await assert.rejects(nativeVaultExecution({...f.options,
    binding: {vaultOrigin: env.BW_SERVER, name: env.BW_ITEM_NAME, ...metadata},
    accountConfig: {path: '/synthetic/accounts.yaml', sha256: 'b'.repeat(64)},
    consume: () => {throw new Error('SYNTHETIC_CONSUMER_FAILED');}}), /SYNTHETIC_CONSUMER_FAILED/);
  assert.equal(f.calls.filter(x => x.args[1] === 'totp').length, 0);
  assert.equal(f.calls.at(-1).args[0], 'status');
});
test('changed aliases refuse credential delivery and still log out', async () => {
  const f = fixture(), metadata = await nativeVaultExecution(f.options); f.calls.length = 0;
  await assert.rejects(nativeVaultExecution({...f.options,
    binding: {vaultOrigin: env.BW_SERVER, name: env.BW_ITEM_NAME, ...metadata, uriAliasesSha256: 'c'.repeat(64)},
    accountConfig: {path: '/synthetic/accounts.yaml', sha256: 'b'.repeat(64)}, consume: () => assert.fail('delivered')}), /VAULT_WORKER_FAILED/);
  assert.equal(f.calls.at(-1).args[0], 'status');
});
test('native environment rejects conflicting sessions, noncanonical origins and missing secrets', () => {
  for (const changed of [{...env, BW_SESSION: ''}, {...env, BW_SERVER: env.BW_SERVER + '/'},
    {...env, BW_PASSWORD: ''}, {...env, BW_ITEM_NAME: 'bad\nname'}, {...env, BD_LOGIN: 'foreign'}])
    assert.throws(() => nativeVaultEnvironment(changed, pin), /NATIVE_VAULT_CONFIG_INVALID/);
});
test('persistent identity binding accepts repeat metadata and refuses changed identity or concurrent owner', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'native-vault-'));
  try {
    fs.chmodSync(directory, 0o700);
    const selected = await nativeVaultExecution(fixture().options);
    const first = retainNativeBinding(directory, env, selected);
    assert.deepEqual(retainNativeBinding(directory, env, selected), first);
    const before = fs.readFileSync(path.join(directory, 'vault-binding.yaml'));
    for (const change of [{itemId: '00000000-0000-4000-8000-000000000009'}, {principalHash: 'd'.repeat(64)}, {uriAliasesSha256: 'e'.repeat(64)}])
      assert.throws(() => retainNativeBinding(directory, env, {...selected, ...change}), /NATIVE_VAULT_BINDING_REFUSED/);
    assert.deepEqual(fs.readFileSync(path.join(directory, 'vault-binding.yaml')), before);
    fs.writeFileSync(path.join(directory, 'vault.lock'), 'other owner', {mode: 0o600});
    assert.throws(() => retainNativeBinding(directory, env, selected), /NATIVE_VAULT_BINDING_REFUSED/);
    assert.equal(fs.readFileSync(path.join(directory, 'vault.lock'), 'utf8'), 'other owner');
  } finally {fs.rmSync(directory, {recursive: true, force: true});}
});
test('close during initialization refuses without overlapping CLI commands', async () => {
  const f = fixture(); let release;
  const wait = new Promise(resolve => {release = resolve;});
  const worker = vaultWorker({configuration: nativeVaultEnvironment(env, pin).configuration,
    appdata: '/synthetic', now: () => 120, verifyExecutable: () => wait, execute: f.options.execute});
  const init = worker.initialize(nativeVaultEnvironment(env, pin).credentials);
  await assert.rejects(worker.close(), /VAULT_CLEANUP_FAILED/);
  release(true); await init; await worker.close();
  assert.equal(f.calls.filter(x => x.args[0] === 'logout').length, 1);
});

test('failed first binding publication retains an exclusion lock and cannot be adopted on retry', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'native-vault-publication-'));
  const sync = fs.fsyncSync;
  try {
    fs.chmodSync(directory, 0o700);
    const selected = await nativeVaultExecution(fixture().options);
    let calls = 0;
    fs.fsyncSync = (...args) => {if (++calls === 3) throw new Error('SYNTHETIC_SYNC_FAILURE'); return sync(...args);};
    assert.throws(() => retainNativeBinding(directory, env, selected), /NATIVE_VAULT_BINDING_REFUSED/);
    fs.fsyncSync = sync;
    assert.ok(fs.existsSync(path.join(directory, 'vault.lock')));
    assert.throws(() => retainNativeBinding(directory, env, selected), /NATIVE_VAULT_BINDING_REFUSED/);
  } finally {fs.fsyncSync = sync; fs.rmSync(directory, {recursive: true, force: true});}
});

test('concurrent initialization fences the first pending attempt before CLI delivery', async () => {
  const f = fixture(); let release;
  const waiting = new Promise(resolve => {release = resolve;});
  const worker = vaultWorker({configuration: nativeVaultEnvironment(env, pin).configuration,
    appdata: '/synthetic', now: () => 120, verifyExecutable: () => waiting, execute: f.options.execute});
  const first = assert.rejects(worker.initialize(nativeVaultEnvironment(env, pin).credentials), /VAULT_WORKER_FAILED/);
  await assert.rejects(worker.initialize(nativeVaultEnvironment(env, pin).credentials), /VAULT_WORKER_FAILED/);
  release(true); await first; await worker.close();
  assert.equal(f.calls.length, 0);
});
