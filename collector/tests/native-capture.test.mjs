import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {nativeCapture} from '../lab/native-capture.mjs';

function fixture(loaderId = 'native-loader') {
  const binding = {targetId: 'native-target', sessionId: 'native-session', frameId: 'native-frame',
    pageEpoch: randomUUID(), frameEpoch: randomUUID()};
  const url = 'http://127.0.0.1:48123/document';
  let current = {...binding, url, loaderId};
  const markers = {account: 'invented-account', day: '2026-09-17', role: 'statement', operation: 'known', body: 'identical invented bytes'};
  const options = {binding, url, account: markers.account, day: markers.day, role: markers.role,
    active: () => current, serialize: () => JSON.stringify(markers)};
  const event = (method, params) => ({method, sessionId: binding.sessionId, params});
  const events = [event('Network.requestWillBeSent', {requestId: 'native-request-' + loaderId, loaderId,
    frameId: binding.frameId, type: 'Document', request: {url, method: 'GET'}}),
  event('Fetch.requestPaused', {requestId: 'native-fetch-' + loaderId, networkId: 'native-request-' + loaderId,
    frameId: binding.frameId, resourceType: 'Document', request: {url, method: 'GET'}}),
  event('Page.frameNavigated', {frame: {id: binding.frameId, loaderId, url}}),
  event('Page.lifecycleEvent', {frameId: binding.frameId, loaderId, name: 'load'})];
  const reply = {frameId: binding.frameId, loaderId};
  function loaded(optionsOverride = {}) {
    const capture = nativeCapture({...options, ...optionsOverride}); capture.arm(); capture.navigation(reply);
    events.forEach(capture.event); return capture;
  }
  return {options, events, reply, loaded, markers, change: value => {current = {...current, ...value};}};
}
test('native capture retains real loader/request/frame/session IDs and allows identical fresh bytes', async () => {
  const a = fixture('native-loader-a'), b = fixture('native-loader-b');
  const first = await a.loaded().capture(), second = await b.loaded().capture();
  assert.equal(first.body, second.body); assert.notEqual(first.loaderId, second.loaderId);
  assert.notEqual(first.requestId, second.requestId); assert.equal(first.sessionId, a.options.binding.sessionId);
  assert.equal(first.browser_proven, false);
});
for (const [name, change] of [
  ['missing network loader', events => {delete events[0].params.loaderId;}],
  ['wrong Fetch network correlation', events => {events[1].params.networkId = 'stale-request';}],
  ['stale native commit', events => {events[2].params.frame.loaderId = 'stale-loader';}],
  ['wrong native URL', events => {events[0].params.request.url += '?other';}],
  ['wrong native frame', events => {events[0].params.frameId = 'foreign-frame';}],
  ['wrong session', events => {events[1].sessionId = 'foreign-session';}],
  ['redirected capture', events => {events[1].params.redirectedRequestId = 'old-fetch';}],
  ['load before commit', events => {[events[2], events[3]] = [events[3], events[2]];}],
  ['non-loader-bound load', events => {events[3].params.name = 'DOMContentLoaded';}],
]) test('native capture refuses ' + name, () => {
  const f = fixture(), capture = nativeCapture(f.options); capture.arm(); capture.navigation(f.reply);
  change(f.events); assert.throws(() => f.events.forEach(capture.event), /NATIVE_CAPTURE_REJECTED/);
});
for (const key of ['account', 'day', 'role', 'operation']) test('capture refuses wrong synthetic ' + key, async () => {
  const f = fixture(); f.markers[key] = 'invented-wrong';
  await assert.rejects(f.loaded().capture(), /NATIVE_CAPTURE_REJECTED/);
});
for (const change of [{loaderId: 'intervening-loader'}, {pageEpoch: randomUUID()}, {frameEpoch: randomUUID()}, {url: 'http://127.0.0.1:48123/other'}]) {
  test('capture refuses changed active navigation/ownership', async () => {
    const f = fixture(); f.change(change); await assert.rejects(f.loaded().capture(), /NATIVE_CAPTURE_REJECTED/);
  });
}
test('capture fences an intervening native event while serialization is held', async () => {
  const f = fixture(); let release, entered;
  const hold = new Promise(resolve => {release = resolve;}), ready = new Promise(resolve => {entered = resolve;});
  const capture = f.loaded({serialize: () => {entered(); return hold;}});
  const pending = capture.capture(); await ready;
  assert.throws(() => capture.event(f.events[0]), /NATIVE_CAPTURE_REJECTED/);
  release(JSON.stringify(f.markers)); await assert.rejects(pending, /NATIVE_CAPTURE_REJECTED/);
});
test('capture requires arming, complete native chain and bounded serialization', async () => {
  const f = fixture(), capture = nativeCapture(f.options);
  assert.throws(() => capture.event(f.events[0]), /NATIVE_CAPTURE_REJECTED/);
  const incomplete = nativeCapture(f.options); incomplete.arm(); incomplete.navigation(f.reply);
  await assert.rejects(incomplete.capture(), /NATIVE_CAPTURE_REJECTED/);
  const timeout = f.loaded({timeoutMs: 5, serialize: () => new Promise(() => {})});
  await assert.rejects(timeout.capture(), /NATIVE_CAPTURE_REJECTED/);
});
