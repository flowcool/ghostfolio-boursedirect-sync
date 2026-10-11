import test from 'node:test';
import assert from 'node:assert/strict';
import {inspectSourceAuthenticationResponse as inspect} from '../source-authentication-response.mjs';
import {BROKER_POLICY} from '../internal/source-policy.mjs';
const initial = {phase: 'password_uncertain', status: 401, body: '{"error":"2FA required"}', base64Encoded: false};
test('known initial challenge retains only outcome and status', () => {
  assert.deepEqual(inspect(BROKER_POLICY, initial), {outcome: 'known_totp_challenge', status: 401});
});
for (const [name, values] of [
  ['wrong credentials', {body:'{"error":"bad-credentials"}'}],
  ['locked user', {body:'{"error":"locked_user"}'}],
  ['successful password without known challenge', {status:200}],
  ['HTTP redirect', {status:302}],
  ['duplicate key', {body:'{"error":"bad-credentials","error":"2FA required"}'}],
  ['malformed base64', {base64Encoded:true, body:'notcanonical'}],
]) test(`response refuses ${name}`, () => assert.throws(() => inspect(BROKER_POLICY, {...initial,...values}), /SOURCE_AUTHENTICATION_RESPONSE_REFUSED/));
test('OTP acceptance is distinct from finalized credentials and does not export backend data', () => {
  assert.deepEqual(inspect(BROKER_POLICY,{phase:'otp_uncertain',status:200,body:'{"success":true,"opaque":"SYNTHETIC_TOKEN"}',base64Encoded:false}),{outcome:'otp_accepted',status:200});
  assert.throws(() => inspect(BROKER_POLICY,{phase:'otp_uncertain',status:200,body:'{"error":"invalid"}',base64Encoded:false}), /SOURCE_AUTHENTICATION_RESPONSE_REFUSED/);
});
test('final response pins only one same-origin source page destination', () => {
  const input={phase:'finalization_uncertain',status:200,body:'{"redirect":"/fr/page/mes-comptes","opaque":"SYNTHETIC_TOKEN"}',base64Encoded:false};
  assert.deepEqual(inspect(BROKER_POLICY,input),{outcome:'credentials_finalized',status:200,document_url:'https://www.boursedirect.fr/fr/page/mes-comptes'});
  for(const redirect of ['https://other.invalid/fr/page/mes-comptes','/fr/login','/fr/page/mes-comptes?retry=1','/fr/page/mes-comptes#fragment','https://user@www.boursedirect.fr/fr/page/mes-comptes'])
    assert.throws(() => inspect(BROKER_POLICY,{...input,body:JSON.stringify({redirect})}), /SOURCE_AUTHENTICATION_RESPONSE_REFUSED/);
});

test('native base64 response decodes internally without returning its body', () => {
  assert.deepEqual(inspect(BROKER_POLICY, {...initial, body:Buffer.from(initial.body).toString('base64'),base64Encoded:true}), {outcome:'known_totp_challenge',status:401});
});
