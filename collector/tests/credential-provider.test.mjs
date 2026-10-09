import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {ORIGIN, principal, otpFromEnvironment} from '../core.mjs';
import {validateWorkerTotp, selectWorkerItem, credentialMode, validateProviderCode, delayedOtpProvider} from '../credential-provider.mjs';
const SECRET = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'; // RFC synthetic key only.
const PROFILE = {algorithm: 'SHA1', period: 30, digits: 6};
const uri = () => `otpauth://totp/synthetic?secret=${SECRET}&algorithm=SHA1&period=30&digits=6`;
function bound() {
  const binding = {itemId: randomUUID(), name: 'synthetic selected item', uri: ORIGIN + '/synthetic-login',
    principalHash: principal('SYNTHETIC'), accountConfig: {path: '/synthetic/import.yaml', sha256: 'a'.repeat(64)}};
  const item = {id: binding.itemId, name: binding.name, type: 1, login: {username: 'SYNTHETIC',
    password: 'SYNTHETIC_PASSWORD', totp: uri(), uris: [{uri: binding.uri}]}};
  return {binding, item};
}
function code() {
  const expected = {runNonce: randomUUID(), stageNonce: randomUUID()};
  return {expected, response: {...expected, code: '123456', startedAt: 120, completedAt: 121, profile: {...PROFILE}}};
}
test('worker accepts only qualified profile and exports neither seed nor raw URI', () => {
  assert.deepEqual(validateWorkerTotp(uri()), PROFILE);
  assert.deepEqual(validateWorkerTotp(SECRET, true), PROFILE);
  assert.deepEqual(validateWorkerTotp(`otpauth://totp/synthetic?secret=${SECRET}`, true), PROFILE);
  const {binding, item} = bound(), selected = selectWorkerItem(item, binding);
  assert.equal(selected.login, 'SYNTHETIC'); assert.equal(selected.password, 'SYNTHETIC_PASSWORD');
  assert.equal(selected.online_ready, false); assert.deepEqual(selected.profile, PROFILE);
  assert.equal(JSON.stringify(selected).includes(SECRET), false); assert.equal(JSON.stringify(selected).includes('otpauth:'), false);
  binding.accountConfig.sha256 = 'b'.repeat(64); assert.equal(selected.accountConfig.sha256, 'a'.repeat(64));
});
for (const [name, value, defaults] of [
  ['unproved raw defaults', SECRET, false], ['unproved URI defaults', `otpauth://totp/synthetic?secret=${SECRET}`, false],
  ['HOTP', uri().replace('totp/', 'hotp/'), true], ['SHA256', uri().replace('SHA1', 'SHA256'), true],
  ['8digits', uri().replace('digits=6', 'digits=8'), true], ['60s', uri().replace('period=30', 'period=60'), true],
  ['duplicate secret', uri() + '&secret=' + SECRET, true], ['duplicate digits', uri() + '&digits=6', true],
  ['counter', uri() + '&counter=0', true], ['unknown parameter', uri() + '&extra=true', true],
  ['bad Base32', uri().replace(SECRET, 'INVALID0SECRET'), true], ['missing secret', 'otpauth://totp/s?algorithm=SHA1&digits=6&period=30', true],
  ['userinfo', uri().replace('totp/', 'user@totp/'), true], ['fragment', uri() + '#x', true],
  ['control', SECRET + '\n', true],
]) test(`worker refuses ${name} without secret-bearing exception`, () => {
  assert.throws(() => validateWorkerTotp(value, defaults), /^Error: PROVIDER_PROFILE_INVALID$/);
});
for (const [name, change] of [
  ['wrong item ID', x => {x.item.id = randomUUID();}], ['wrong name', x => {x.item.name = 'other';}],
  ['non-login item', x => {x.item.type = 2;}], ['deleted item', x => {x.item.deletedDate = 'synthetic';}],
  ['wrong principal', x => {x.item.login.username = 'OTHER';}], ['empty password', x => {x.item.login.password = '';}],
  ['two URIs', x => {x.item.login.uris.push({uri: x.binding.uri});}],
  ['mismatched URI', x => {x.item.login.uris[0].uri = ORIGIN + '/other';}],
  ['missing TOTP', x => {delete x.item.login.totp;}], ['unproved config hash', x => {x.binding.accountConfig.sha256 = 'bad';}],
  ['foreign binding origin', x => {x.binding.uri = 'https://foreign.invalid/';}],
]) test(`item ${name} cannot deliver credentials`, () => {
  const value = bound(); change(value); assert.throws(() => selectWorkerItem(value.item, value.binding), /^Error: PROVIDER_ITEM_INVALID$/);
});
test('provider selection refuses even partial/empty competing initial-mode fields', () => {
  for (const key of ['BD_OTP', 'BD_OTP_ISSUED_AT', 'BD_TOTP_SECRET']) {
    assert.throws(() => credentialMode({[key]: ''}, true), /PROVIDER_MODE_CONFLICT/);
  }
  assert.equal(credentialMode({}, true), 'provider');
  assert.equal(credentialMode({BD_OTP: '123456'}, false), 'initial-environment');
  assert.equal(otpFromEnvironment({BD_OTP: '123456', BD_OTP_ISSUED_AT: '120'}, 121), '123456');
});
test('bounded code result binds exact stage and conservative issued step', () => {
  const {expected, response} = code();
  assert.deepEqual(validateProviderCode(response, expected, 122), {code: '123456', otp: {issuedAt: 120, step: 4}, online_ready: false});
});
for (const [name, change, receipt] of [
  ['wrong run', x => {x.runNonce = randomUUID();}, 122], ['wrong stage', x => {x.stageNonce = randomUUID();}, 122],
  ['invalid code', x => {x.code = 'PRIVATE_SYNTHETIC_SENTINEL';}, 122],
  ['wrong profile', x => {x.profile.period = 60;}, 122], ['extra secret field', x => {x.seed = SECRET;}, 122],
  ['reversed start', x => {x.startedAt = 123;}, 122], ['future completion', x => {x.completedAt = 123;}, 122],
  ['CLI rollover', x => {x.completedAt = 150;}, 151], ['receipt rollover', () => {}, 150],
  ['stale receipt', () => {}, 141], ['near-expiry receipt', x => {x.startedAt = 140; x.completedAt = 141;}, 146],
]) test(`provider result ${name} refuses with fixed error`, () => {
  const {expected, response} = code(); change(response);
  assert.throws(() => validateProviderCode(response, expected, receipt), /^Error: PROVIDER_CODE_INVALID$/);
});
test('one delayed request obtains a code once, while repeated request cannot refresh', async () => {
  const {expected, response} = code(); let calls = 0;
  const p = delayedOtpProvider({...expected, now: () => 121, fetchCode: input => {
    calls++; assert.deepEqual(input, expected); return {...response, startedAt: 121};
  }});
  assert.equal((await p.request(expected)).code, '123456');
  await assert.rejects(p.request(expected), /PROVIDER_REQUEST_REJECTED/); assert.equal(calls, 1);
});
test('concurrent request permanently fences the held first response rather than refreshing', async () => {
  const {expected, response} = code(); let release, entered;
  const held = new Promise(done => {release = done;}), entry = new Promise(done => {entered = done;});
  let calls = 0;
  const p = delayedOtpProvider({...expected, now: () => 120, fetchCode: () => {calls++; entered(); return held;}});
  const first = Promise.allSettled([p.request(expected)]); await entry;
  await assert.rejects(p.request(expected), /PROVIDER_REQUEST_REJECTED/); release(response);
  assert.equal((await first)[0].status, 'rejected'); assert.equal(calls, 1); assert.equal(p.status().fenced, true);
});
test('invalid request cannot call provider and permanently disables later valid request', async () => {
  const {expected} = code(); let calls = 0;
  const p = delayedOtpProvider({...expected, now: () => 120, fetchCode: () => {calls++;}});
  await assert.rejects(p.request({...expected, stageNonce: randomUUID()}), /PROVIDER_REQUEST_REJECTED/);
  await assert.rejects(p.request(expected), /PROVIDER_REQUEST_REJECTED/); assert.equal(calls, 0);
});
test('late callback, timeout, secret exception and reversed provider start cannot retry', async () => {
  for (const kind of ['timeout', 'error', 'old', 'rollover']) {
    const {expected, response} = code(); let calls = 0, samples = 0;
    const p = delayedOtpProvider({...expected, timeoutMs: 10,
      now: () => {samples++; return kind === 'rollover' && samples > 1 ? 150 : 121;},
      fetchCode: () => {calls++;
        if (kind === 'timeout') return new Promise(() => {});
        if (kind === 'error') throw new Error(SECRET);
        return {...response, startedAt: kind === 'old' ? 120 : 121};
      }});
    await assert.rejects(p.request(expected), /^Error: PROVIDER_REQUEST_REJECTED$/);
    await assert.rejects(p.request(expected), /^Error: PROVIDER_REQUEST_REJECTED$/); assert.equal(calls, 1);
  }
});
test('near-rollover request and conflicting initialization never fetch', async () => {
  const {expected} = code(); let calls = 0;
  const p = delayedOtpProvider({...expected, now: () => 146, fetchCode: () => {calls++;}});
  await assert.rejects(p.request(expected), /PROVIDER_REQUEST_REJECTED/); assert.equal(calls, 0);
  assert.throws(() => delayedOtpProvider({...expected, now: () => 120, fetchCode: () => {}, env: {BD_OTP: ''}}), /PROVIDER_CONFIG_INVALID/);
});
