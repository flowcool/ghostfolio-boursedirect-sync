import test from 'node:test';
import assert from 'node:assert/strict';
import {PUBLIC_LOGIN_URL, publicLoginPolicy} from '../public-login-policy.mjs';
const owner = {sessionId: 'synthetic-session', frameId: 'synthetic-frame'};
const request = {requestId: 'synthetic-request', ...owner, resourceType: 'Document',
  request: {method: 'GET', url: PUBLIC_LOGIN_URL}};
test('public observation permits one initial document then blocks replay', () => {
  const decide = publicLoginPolicy(owner);
  assert.equal(decide(request), true);
  assert.equal(decide({...request, requestId: 'second'}), false);
  assert.throws(() => decide(request), /PUBLIC_OBSERVATION_REQUEST_REFUSED/);
});
for (const [name, change] of [
  ['password POST', {request: {method: 'POST', url: PUBLIC_LOGIN_URL}}],
  ['XHR', {resourceType: 'XHR'}], ['script', {resourceType: 'Script'}],
  ['other frame', {frameId: 'foreign'}], ['other session', {sessionId: 'foreign'}],
  ['redirect', {redirectedRequestId: 'redirect'}],
  ['query', {request: {method: 'GET', url: PUBLIC_LOGIN_URL + '?action=synthetic'}}],
  ['foreign URL', {request: {method: 'GET', url: 'https://foreign.invalid/fr/login'}}],
]) test('public observation blocks ' + name + ' without consuming the initial document', () => {
  const decide = publicLoginPolicy(owner);
  assert.equal(decide({...request, ...change}), false);
  assert.equal(decide({...request, requestId: 'initial-document'}), true);
});
test('binding is immutable and the observation budget refuses overflow', () => {
  const mutable = {...owner}, decide = publicLoginPolicy(mutable);
  mutable.frameId = 'foreign';
  for (let id = 0; id < 256; id++) assert.equal(decide({...request, requestId: String(id), resourceType: 'XHR'}), false);
  assert.throws(() => decide({...request, requestId: 'overflow'}), /PUBLIC_OBSERVATION_REQUEST_REFUSED/);
});

const asset = {url: 'https://www.boursedirect.fr/synthetic-app.js', resourceType: 'Script'};
const assetRequest = {...request, requestId: 'asset', request: {method: 'GET', url: asset.url}, resourceType: 'Script'};
test('observed asset GET is granted once after the public document with exact type/frame/session', () => {
  const decide = publicLoginPolicy(owner, [asset]);
  assert.equal(decide(assetRequest), false);
  assert.equal(decide(request), true);
  assert.equal(decide({...assetRequest, requestId: 'asset-after-document'}), true);
  assert.equal(decide({...assetRequest, requestId: 'asset-repeated'}), false);
});
for (const [name, change] of [
  ['POST', {request: {method: 'POST', url: asset.url}}], ['XHR type', {resourceType: 'XHR'}],
  ['redirect', {redirectedRequestId: 'redirect'}], ['foreign session', {sessionId: 'foreign'}],
  ['foreign frame', {frameId: 'foreign'}], ['unobserved URL', {request: {method: 'GET', url: asset.url + '?other'}}],
]) test('observed asset rejects ' + name, () => {
  const decide = publicLoginPolicy(owner, [asset]);decide(request);
  assert.equal(decide({...assetRequest, ...change}), false);
});
for (const [name, value] of [
  ['foreign origin', [{...asset, url: 'https://foreign.invalid/app.js'}]],
  ['authentication type', [{...asset, resourceType: 'XHR'}]], ['document type', [{...asset, resourceType: 'Document'}]],
  ['fragment', [{...asset, url: asset.url + '#fragment'}]], ['extra authority', [{...asset, password: true}]],
  ['duplicate', [asset, asset]], ['oversized', Array(33).fill(asset)],
]) test('public asset configuration refuses ' + name, () => {
  assert.throws(() => publicLoginPolicy(owner, value), /PUBLIC_OBSERVATION_ASSETS_REFUSED/);
});
