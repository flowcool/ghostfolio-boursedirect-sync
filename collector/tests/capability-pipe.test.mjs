import test from 'node:test';
import assert from 'node:assert/strict';
import {capabilityPipe, PIPE_LIMITS} from '../capability-pipe.mjs';

const frame = data => Buffer.from(JSON.stringify(data) + '\0');
function fixture(overrides = {}) {
  const writes = [], events = [], fences = [], timers = new Map();
  let tick = 0;
  const pipe = capabilityPipe({
    write: bytes => {writes.push(bytes);}, onEvent: event => {events.push(event);},
    fence: code => {fences.push(code);},
    schedule: (fn, ms) => {const id = ++tick; timers.set(id, {fn, ms}); return id;},
    cancel: id => timers.delete(id), ...overrides,
  });
  return {pipe, writes, events, fences, timers};
}
test('fragmented pipe replies route by monotonic command ID and exact session', async () => {
  const f = fixture(); f.pipe.registerSession('s');
  const a = f.pipe.send('Browser.getVersion'), b = f.pipe.send('Network.enable', {}, 's');
  assert.deepEqual(f.writes.map(bytes => JSON.parse(bytes.subarray(0, -1)).id), [1, 2]);
  const reply = frame({id: 2, result: {}, sessionId: 's'});
  f.pipe.receive(reply.subarray(0, 7)); f.pipe.receive(reply.subarray(7));
  f.pipe.receive(frame({id: 1, result: {product: 'Chrome/148.0.7778.97'}}));
  assert.deepEqual(await b, {}); assert.equal((await a).product, 'Chrome/148.0.7778.97');
  assert.deepEqual(f.fences, []);
});
test('startup events are retained until handlers are armed, in pipe order', () => {
  const f = fixture();
  f.pipe.receive(Buffer.concat([frame({method: 'Target.created', params: {n: 1}}), frame({method: 'Target.created', params: {n: 2}})]));
  assert.equal(f.events.length, 0); f.pipe.armEvents();
  assert.deepEqual(f.events.map(v => v.params.n), [1, 2]);
});
for (const [name, raw] of [
  ['malformed JSON', Buffer.from('{broken\0')], ['invalid UTF8', Buffer.from([255, 0])],
  ['array', frame([])], ['unknown reply', frame({id: 8, result: {}})],
  ['unknown session', frame({method: 'Fetch.requestPaused', params: {}, sessionId: 'foreign'})],
]) test(`${name} synchronously fences and rejects pending commands`, async () => {
  const f = fixture(); const request = f.pipe.send('Browser.getVersion');
  const rejection = assert.rejects(request, /^Error: CAPABILITY_/);
  assert.throws(() => f.pipe.receive(raw), /^Error: CAPABILITY_/);
  assert.equal(f.pipe.failed(), true); assert.equal(f.fences.length, 1);
  await rejection; assert.equal(f.timers.size, 0);
  await assert.rejects(f.pipe.send('Runtime.runIfWaitingForDebugger'), /FENCED/);
  assert.equal(f.writes.length, 1);
});
test('duplicate reply cannot resolve or trigger any next command', async () => {
  const f = fixture(); const a = f.pipe.send('Browser.getVersion');
  const reply = frame({id: 1, result: {}}); f.pipe.receive(reply); await a;
  assert.throws(() => f.pipe.receive(reply), /CAPABILITY_REPLY_REJECTED/);
});
test('response session must match the exact command session', async () => {
  const f = fixture(); f.pipe.registerSession('a'); f.pipe.registerSession('b');
  const request = f.pipe.send('Network.enable', {}, 'a'); const failure = assert.rejects(request, /REPLY_REJECTED/);
  assert.throws(() => f.pipe.receive(frame({id: 1, result: {}, sessionId: 'b'})), /REPLY_REJECTED/);
  await failure;
});
test('protocol errors use fixed diagnostics without retaining remote error details', async () => {
  const f = fixture(); const request = f.pipe.send('Browser.getVersion');
  f.pipe.receive(frame({id: 1, error: {message: 'private synthetic detail'}}));
  await assert.rejects(request, /^Error: CAPABILITY_COMMAND_REJECTED$/);
  assert.deepEqual(f.fences, ['CAPABILITY_COMMAND_REJECTED']);
});
test('command timeout fences all work; late response cannot authorize replay', async () => {
  const f = fixture(); const request = f.pipe.send('Browser.getVersion');
  const failure = assert.rejects(request, /COMMAND_TIMEOUT/);
  [...f.timers.values()].find(v => v.ms === PIPE_LIMITS.commandMs).fn();
  await failure; assert.throws(() => f.pipe.receive(frame({id: 1, result: {}})), /FENCED/);
});
test('session timeout fences idle transport', () => {
  const f = fixture(); [...f.timers.values()].find(v => v.ms === PIPE_LIMITS.sessionMs).fn();
  assert.equal(f.pipe.failed(), true); assert.equal(f.timers.size, 0);
});
test('incomplete frame bytes count toward the message limit', () => {
  const f = fixture({limits: {...PIPE_LIMITS, messageBytes: 16}});
  f.pipe.receive(Buffer.alloc(16, 65));
  assert.throws(() => f.pipe.receive(Buffer.from('A')), /MESSAGE_LIMIT/);
});
test('startup queue cannot grow past its event-count budget', () => {
  const f = fixture({limits: {...PIPE_LIMITS, startupEvents: 1}});
  f.pipe.receive(frame({method: 'Target.created', params: {}}));
  assert.throws(() => f.pipe.receive(frame({method: 'Target.created', params: {}})), /EVENT_LIMIT/);
});
test('pending commands are bounded before the next write', async () => {
  const f = fixture({limits: {...PIPE_LIMITS, pending: 1}});
  const a = f.pipe.send('Browser.getVersion'); const failure = assert.rejects(a, /OUTPUT_LIMIT/);
  await assert.rejects(f.pipe.send('Target.setDiscoverTargets'), /OUTPUT_LIMIT/); await failure;
  assert.equal(f.writes.length, 1);
});
test('queued output bytes include writes that have not completed', async () => {
  let release;
  const f = fixture({limits: {...PIPE_LIMITS, queuedBytes: 90}, write: () => new Promise(ok => {release = ok;})});
  const a = f.pipe.send('Browser.getVersion'); const failure = assert.rejects(a, /OUTPUT_LIMIT/);
  await assert.rejects(f.pipe.send('Browser.getVersion'), /OUTPUT_LIMIT/); await failure; release();
});
test('pipe loss fences synchronously and rejects every pending command once', async () => {
  const f = fixture(); const a = f.pipe.send('Browser.getVersion'), b = f.pipe.send('Target.setDiscoverTargets');
  const failures = [assert.rejects(a, /PIPE_LOST/), assert.rejects(b, /PIPE_LOST/)];
  f.pipe.lost(); f.pipe.lost(); assert.equal(f.fences.length, 1); await Promise.all(failures);
});
test('write rejection has no retry', async () => {
  let calls = 0;
  const f = fixture({write: async () => {calls++; throw new Error('private write error');}});
  await assert.rejects(f.pipe.send('Browser.getVersion'), /PIPE_LOST/); assert.equal(calls, 1);
});
test('session budget prevents an unknown target from registering indefinitely', () => {
  const f = fixture({limits: {...PIPE_LIMITS, sessions: 1}}); f.pipe.registerSession('a');
  assert.throws(() => f.pipe.registerSession('b'), /SESSION_REJECTED/);
});

test('asynchronous event routing cannot silently defer the fence', () => {
  const f = fixture({onEvent: async () => {throw new Error('synthetic handler failure');}});
  f.pipe.armEvents();
  assert.throws(() => f.pipe.receive(frame({method: 'Target.created', params: {}})), /EVENT_REJECTED/);
  assert.deepEqual(f.fences, ['CAPABILITY_EVENT_REJECTED']);
});
