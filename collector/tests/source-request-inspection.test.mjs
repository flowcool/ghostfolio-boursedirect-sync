import test from 'node:test';
import assert from 'node:assert/strict';
import {inspectSourceRequest} from '../source-request-inspection.mjs';

function fixture(role = 'password_submit') {
  const owner = {sessionId: 'synthetic-session', frameId: 'synthetic-frame'};
  const expected = role === 'preliminary_verify' ? {branding: 'synthetic-brand'}
    : role === 'otp_submit' ? {code: '123456', branding: 'synthetic-brand'}
    : {login: 'SYNTHETIC_PRINCIPAL', password: 'SYNTHETIC_PASSWORD', branding: 'synthetic-brand'};
  const body = role === 'preliminary_verify' ? {...expected}
    : role === 'otp_submit' ? {...expected, trusted_device: false}
    : {username: expected.login, password: expected.password, branding: expected.branding, redirect: null};
  const candidate = {role, url: 'https://www.boursedirect.fr/synthetic/' + role,
    method: 'POST', resourceType: 'XHR', sourceSha256: 'a'.repeat(64)};
  const event = {requestId: 'synthetic-request', ...owner, resourceType: 'XHR', request: {
    url: candidate.url, method: 'POST', headers: {'Content-Type': 'application/json',
      Cookie: 'SYNTHETIC_COOKIE', Authorization: 'SYNTHETIC_TOKEN'}, postData: JSON.stringify(body)}};
  return {owner, expected, candidate, event};
}
for (const role of ['preliminary_verify', 'password_submit', 'otp_submit', 'password_finalize']) {
  test(`native ${role} evidence retains structure without credentials or dispatch authority`, () => {
    const f = fixture(role), before = JSON.stringify(f), observed = inspectSourceRequest(f);
    assert.equal(observed.role, role);
    assert.equal(observed.dispatch_authority, false);
    assert.equal(observed.online_ready, false);
    assert.equal(Object.isFrozen(observed), true);
    for (const secret of ['SYNTHETIC_PRINCIPAL', 'SYNTHETIC_PASSWORD', '123456', 'synthetic-brand',
      'SYNTHETIC_COOKIE', 'SYNTHETIC_TOKEN']) assert.equal(JSON.stringify(observed).includes(secret), false);
    assert.equal(JSON.stringify(f), before);
  });
}
for (const [name, mutate] of [
  ['foreign session', f => {f.event.sessionId = 'foreign';}],
  ['foreign frame', f => {f.event.frameId = 'foreign';}],
  ['redirect metadata', f => {f.event.redirectedRequestId = 'prior';}],
  ['changed destination', f => {f.event.request.url += '/other';}],
  ['wildcard origin', f => {f.candidate.url = 'https://foreign.invalid/synthetic';}],
  ['changed type', f => {f.event.resourceType = 'Fetch';}],
  ['changed method', f => {f.event.request.method = 'GET';}],
  ['ambiguous content type', f => {f.event.request.headers['content-type'] = 'application/json';}],
  ['wrong content type', f => {f.event.request.headers['Content-Type'] = 'text/plain';}],
  ['duplicate JSON key', f => {f.event.request.postData = '{"branding":"x","branding":"y"}';}],
  ['unbounded body', f => {f.event.request.postData = 'x'.repeat(8193);}],
  ['unlisted role', f => {f.candidate.role = 'order';}],
  ['wrong source pin', f => {f.candidate.sourceSha256 = 'missing';}],
  ['wrong principal', f => {f.expected.login = 'OTHER_PRINCIPAL';}],
  ['wrong credential', f => {f.expected.password = 'OTHER_PASSWORD';}],
  ['navigation injection', f => {const b = JSON.parse(f.event.request.postData); b.redirect = '/order';
    f.event.request.postData = JSON.stringify(b);}],
]) test(`request inspection refuses ${name} with a fixed diagnostic`, () => {
  const f = fixture(); mutate(f);
  assert.throws(() => inspectSourceRequest(f), /^Error: SOURCE_REQUEST_ENVELOPE_REFUSED$/);
});
test('OTP cannot trust the device, accept another code or change the schema', () => {
  for (const mutate of [b => {b.trusted_device = true;}, b => {b.code = '654321';}, b => {b.extra = true;}]) {
    const f = fixture('otp_submit'), body = JSON.parse(f.event.request.postData);
    mutate(body); f.event.request.postData = JSON.stringify(body);
    assert.throws(() => inspectSourceRequest(f), /^Error: SOURCE_REQUEST_ENVELOPE_REFUSED$/);
  }
});
test('exact source reads cannot accept a body or inherit a credential projection', () => {
  for (const role of ['app_method', 'frame_document', 'monthly_statement', 'contract_note']) {
    const f = fixture(); f.candidate.role = role; f.candidate.method = 'GET';
    f.candidate.resourceType = role === 'app_method' ? 'XHR' : 'Document';
    f.event.resourceType = f.candidate.resourceType;
    f.event.request = {url: f.candidate.url, method: 'GET'}; f.expected = {};
    assert.equal(inspectSourceRequest(f).role, role);
    f.expected = {password: 'SYNTHETIC_PASSWORD'};
    assert.throws(() => inspectSourceRequest(f), /^Error: SOURCE_REQUEST_ENVELOPE_REFUSED$/);
  }
});
