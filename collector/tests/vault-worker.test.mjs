import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {PassThrough} from 'node:stream';
import {ORIGIN, principal} from '../core.mjs';
import {vaultWorker, providerConfiguration} from '../vault-worker.mjs';
import {workerUriAliasesHash} from '../credential-provider.mjs';
import {privateChannel, PRIVATE_LIMIT} from '../private-channel.mjs';
import {collectorEnvironment} from '../private-process.mjs';

function fixture(fault, aliasMode = false) {
  const id = randomUUID(), expected = {runNonce: randomUUID(), stageNonce: randomUUID()}, calls = [];
  const config = {schema_version: 1, vaultOrigin: 'https://vault.synthetic.invalid',
    binding: {itemId: id, name: 'invented', uri: ORIGIN + '/synthetic', principalHash: principal('SYNTHETIC'),
      accountConfig: {path: '/synthetic/account.yaml', sha256: 'a'.repeat(64)}},
    cli: {path: '/opt/bw', sha256: 'b'.repeat(64), version: 'synthetic-1', defaultsVerified: false}};
  const item = {id, type: 1, name: 'invented', login: {username: 'SYNTHETIC', password: 'SYNTHETIC_PASSWORD',
    uris: [{uri: config.binding.uri}], totp: 'otpauth://totp/invented?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&algorithm=SHA1&digits=6&period=30'}};
  if (aliasMode) {
    config.schema_version = 4;
    item.login.uris.push({uri: 'https://alias.synthetic.invalid/', match: null});
    config.binding.uriAliasesSha256 = workerUriAliasesHash(item.login.uris);
  }
  let clock = 120;
  const worker = vaultWorker({configuration: config, appdata: '/synthetic/tmpfs', now: () => clock,
    verifyExecutable: () => fault !== 'pin', execute: async (path, args, env) => {
      calls.push({path, args, env});
      if (fault === args[0]) throw new Error('PRIVATE_SYNTHETIC_SENTINEL');
      if (fault === 'rollover' && args[1] === 'totp') clock = 150;
      const stdout = args[0] === '--version' ? 'synthetic-1' : args[0] === 'unlock' ? 'SYNTHETIC_SESSION'
        : args[1] === 'item' ? JSON.stringify(item) : args[1] === 'totp' ? '123456' : '';
      return {status: 0, stdout, stderr: ''};
    }});
  return {config, item, calls, worker, expected, setClock: value => {clock = value;}};
}
const credentials = {BW_CLIENTID: 'SYNTHETIC_CLIENT', BW_CLIENTSECRET: 'SYNTHETIC_API', BW_PASSWORD: 'SYNTHETIC_UNLOCK'};
test('alias mode reads fixed UUID and delays the same UUID TOTP until challenge', async () => {
  const f = fixture(undefined, true);
  const selected = await f.worker.initialize(credentials);
  assert.equal(selected.itemId, f.item.id);
  assert.deepEqual(f.calls.at(-1).args, ['get', 'item', f.item.id]);
  assert.equal(f.calls.some(row => row.args[0] === 'list'), false);
  assert.equal(f.calls.some(row => row.args[1] === 'totp'), false);
  await f.worker.code(f.expected, f.expected);
  assert.deepEqual(f.calls.at(-1).args, ['get', 'totp', f.item.id]);
});
test('changed alias after immutable config capture fences delivery without retry', async () => {
  const f = fixture(undefined, true);
  f.item.login.uris[1].uri = 'https://changed.synthetic.invalid/';
  await assert.rejects(f.worker.initialize(credentials), /^Error: VAULT_WORKER_FAILED$/);
  const count = f.calls.length;
  await assert.rejects(f.worker.initialize(credentials), /^Error: VAULT_WORKER_FAILED$/);
  assert.equal(f.calls.length, count);
});
test('fixed worker sequence and delayed one-use TOTP keep secret seed inside worker', async () => {
  const f = fixture(), selected = await f.worker.initialize(credentials);
  assert.deepEqual(f.calls.map(x => x.args), [['--version'], ['config','server',f.config.vaultOrigin],
    ['login','--apikey'], ['unlock','--passwordenv','BW_PASSWORD','--raw'], ['sync'], ['get','item',f.config.binding.itemId]]);
  assert.equal(f.calls.filter(x => x.args[1] === 'totp').length, 0);
  assert.equal(JSON.stringify(selected).includes('otpauth'), false);
  assert.deepEqual(Object.keys(f.calls[2].env).sort(), ['BITWARDENCLI_APPDATA_DIR','BW_CLIENTID','BW_CLIENTSECRET','HOME','PATH']);
  assert.equal(f.calls[3].env.BW_CLIENTSECRET, undefined);
  assert.equal(f.calls[4].env.BW_PASSWORD, undefined);
  assert.deepEqual(collectorEnvironment(selected, '/synthetic'), {HOME: '/synthetic', PATH: '/usr/bin:/bin',
    BD_LOGIN: 'SYNTHETIC', BD_PASSWORD: 'SYNTHETIC_PASSWORD'});
  f.config.binding.itemId = randomUUID(); // Mutating caller config cannot replace the fixed selected UUID.
  assert.equal((await f.worker.code(f.expected, f.expected)).code, '123456');
  assert.equal(f.calls.at(-1).args[2], f.item.id);
  await assert.rejects(f.worker.code(f.expected, f.expected), /^Error: VAULT_WORKER_FAILED$/);
  assert.equal(f.calls.filter(x => x.args[1] === 'totp').length, 1);
});
for (const fault of ['pin','config','login','unlock','sync','get']) test('failure at ' + fault + ' never retries or exposes raw CLI error', async () => {
  const f = fixture(fault);
  await assert.rejects(f.worker.initialize(credentials), /^Error: VAULT_WORKER_FAILED$/);
  const count = f.calls.length;
  await assert.rejects(f.worker.initialize(credentials), /^Error: VAULT_WORKER_FAILED$/);
  assert.equal(f.calls.length, count);
});
for (const change of [f => {f.item.id = randomUUID();}, f => {f.item.login.uris.push({uri: f.config.binding.uri});},
  f => {f.item.login.username = 'OTHER';}, f => {f.item.login.totp += '&period=60';}]) {
  test('unbound or ambiguous item cannot export login/password', async () => {
    const f = fixture(); change(f); await assert.rejects(f.worker.initialize(credentials), /^Error: VAULT_WORKER_FAILED$/);
  });
}
test('wrong nonce consumes worker opportunity before calling CLI', async () => {
  const f = fixture(); await f.worker.initialize(credentials);
  await assert.rejects(f.worker.code({...f.expected, stageNonce: randomUUID()}, f.expected), /VAULT_WORKER_FAILED/);
  await assert.rejects(f.worker.code(f.expected, f.expected), /VAULT_WORKER_FAILED/);
  assert.equal(f.calls.filter(x => x.args[1] === 'totp').length, 0);
});
test('worker rollover rejects result without a replacement code', async () => {
  const f = fixture('rollover'); await f.worker.initialize(credentials);
  await assert.rejects(f.worker.code(f.expected, f.expected), /VAULT_WORKER_FAILED/);
  assert.equal(f.calls.filter(x => x.args[1] === 'totp').length, 1);
});
test('worker clock reversal refuses before command', async () => {
  const f = fixture(); await f.worker.initialize(credentials); f.setClock(-1);
  await assert.rejects(f.worker.code(f.expected, f.expected), /VAULT_WORKER_FAILED/);
  assert.equal(f.calls.filter(x => x.args[1] === 'totp').length, 0);
});
test('concurrent code request fences the held first CLI result with no second call', async () => {
  const f = fixture(); let release, entered, calls = 0;
  const held = new Promise(resolve => {release = resolve;}), entry = new Promise(resolve => {entered = resolve;});
  const worker = vaultWorker({configuration:f.config, appdata:'/synthetic', verifyExecutable:()=>true, now:()=>120,
    execute:async (path,args) => {
      let stdout = args[0] === '--version' ? 'synthetic-1' : args[0] === 'unlock' ? 'SYNTHETIC_SESSION'
        : args[1] === 'item' ? JSON.stringify(f.item) : '';
      if (args[1] === 'totp') {calls++; entered(); stdout = await held;}
      return {status:0,stdout,stderr:''};
    }});
  await worker.initialize(credentials);
  const first = assert.rejects(worker.code(f.expected,f.expected), /VAULT_WORKER_FAILED/);
  await entry; await assert.rejects(worker.code(f.expected,f.expected), /VAULT_WORKER_FAILED/);
  release('123456'); await first; assert.equal(calls,1);
});
test('strict provider configuration refuses extra secret fields or relative account refs', () => {
  const f = fixture(); assert.throws(() => providerConfiguration({...f.config, password: 'SECRET'}), /VAULT_CONFIG_INVALID/);
  f.config.binding.accountConfig.path = 'relative'; assert.throws(() => providerConfiguration(f.config), /VAULT_CONFIG_INVALID/);
});
function channel(timeoutMs = 30) {
  const input = new PassThrough(), output = new PassThrough(); let fenced = 0;
  const transport = privateChannel({input, output, timeoutMs, fence: () => {fenced++;}});
  return {input, output, transport, fences: () => fenced};
}
test('private transport handles split UTF8 frame and bounded reply', async () => {
  const f = channel(); const wait = f.transport.receive();
  f.input.write(Buffer.from('{"code":')); f.input.write(Buffer.from('"123456"}\n'));
  assert.deepEqual(await wait, {code: '123456'}); f.transport.close(true);
});
for (const raw of ['{"a":1,"a":2}\n', '{}\n{}\n', '{bad}\n', '[]\n', '{}\ntrailing', 'x'.repeat(PRIVATE_LIMIT + 1)]) {
  test('malformed or oversized private input fences once with fixed error', async () => {
    const f = channel(), wait = f.transport.receive(); f.input.write(Buffer.from(raw));
    await assert.rejects(wait, /^Error: PRIVATE_CHANNEL_FAILED$/); assert.equal(f.fences(), 1);
    await assert.rejects(f.transport.receive(), /PRIVATE_CHANNEL_FAILED/);
  });
}
test('private pipe timeout/disconnect and live-close are failures', async () => {
  const f = channel(5); await assert.rejects(f.transport.receive(), /PRIVATE_CHANNEL_FAILED/);
  const g = channel(), waiting = g.transport.receive(); g.input.end(); await assert.rejects(waiting, /PRIVATE_CHANNEL_FAILED/);
  const h = channel(); assert.throws(() => h.transport.close(false), /PRIVATE_CHANNEL_CLOSE_REJECTED/);
});
