// Opt-in network-none synthetic fixture. No source loader, credentials or broker CLI.
import http from 'node:http';
import fs from 'node:fs';
import {randomUUID, createHash} from 'node:crypto';
import {spawn, spawnSync} from 'node:child_process';
import {once} from 'node:events';
import {parse} from 'yaml';
import {nativeComposition} from './native-composition.mjs';
import {nativeCapture} from './native-capture.mjs';
import {capabilityPipe} from '../capability-pipe.mjs';
import {orderingExperiment} from '../capability-ordering.mjs';
import {bootstrapExperiment} from '../capability-bootstrap.mjs';

import {NATIVE_MODES, nativeVerdict} from './native-verdict.mjs';
const mode = process.argv[2], allocation = process.argv[3];
if (!NATIVE_MODES.includes(mode) || process.version !== 'v20.19.2') throw new Error('NATIVE_RUNTIME_REJECTED');
const negative = mode.endsWith('-negative'), scenario = mode.replace(/-negative$/, '');
const captureMode = scenario.startsWith('capture');
const trace = [], counts = {}, tasks = new Set();
let allowed = 0, forbidden = 0, challenges = 0, cancelled = 0, consumes = 0, captureResult, captureRefused = false;
let held = false, releaseHeld;
const heldRequest = new Promise(resolve => {releaseHeld = resolve;});
let rootFrame, nativeTarget, rootEpoch, pageEpoch, owner, controller, composition, handle, permitNonce, pipe, ordering, bootstrap, capture;
let fenced = false, exited = false, stopped, stderrBytes = 0, fsyncFailed = false, restartFenced = false, forceKilled = false, crashed = false, cancelAcknowledged = 0;
function record(value) {
  if (trace.length >= 1000) {void fatal().catch(() => {}); return;}
  trace.push(value);
}
function rootDocument() {
  if (scenario === 'popup') return '<form id=f method=POST action=/forbidden target=_blank></form><script>f.submit()</script>';
  if (scenario === 'frame') return '<iframe srcdoc="<form id=f method=POST action=/forbidden></form><script>f.submit()</script>"></iframe>';
  if (scenario === 'worker') return '<script>new Worker("/forbidden")</script>';
  if (scenario === 'shared-worker') return '<script>new SharedWorker("/forbidden")</script>';
  if (scenario === 'service-worker') return '<script>navigator.serviceWorker.register("/forbidden")</script>';
  if (scenario === 'http-auth') return '<script>fetch("/challenge")</script>';
  if (['concurrent','held-auth'].includes(scenario)) return '<script>fetch("/allowed",{method:"POST"});fetch("/allowed",{method:"POST"})</script>';
  if (scenario === 'second-auth') return '<script>fetch("/allowed",{method:"POST"}).then(()=>fetch("/allowed",{method:"POST"}))</script>';
  const path = ['permitted', 'redirect307', 'redirect308', 'fsync-failure', 'browser-crash'].includes(scenario) ? '/allowed' : '/forbidden';
  return '<script>fetch("' + path + '",{method:"POST"})</script>';
}
const server = http.createServer((request, response) => {
  if (request.url === '/root') {response.setHeader('Content-Type', 'text/html'); response.end('<link rel=icon href="data:,">' + rootDocument()); return;}
  if (request.url === '/document') {
    response.setHeader('Content-Type', 'text/html');
    const account = scenario === 'capture-wrong-account' ? 'invented-other' : 'invented-account';
    const day = scenario === 'capture-wrong-day' ? '2026-09-18' : '2026-09-17';
    const role = scenario === 'capture-wrong-role' ? 'invented-other' : 'statement';
    const operation = scenario === 'capture-unknown-operation' ? 'unknown' : 'known';
    response.end(`<link rel=icon href="data:,"><main data-account=${account} data-day=${day} data-role=${role} data-operation=${operation}>identical invented bytes</main>`); return;
  }
  if (request.url === '/allowed') {
    allowed++;
    if (scenario.startsWith('redirect')) response.writeHead(Number(scenario.slice(8)), {Location: '/forbidden'});
  }
  if (request.url === '/forbidden') {forbidden++; response.setHeader('Content-Type', 'application/javascript');}
  if (request.url === '/challenge') {challenges++; response.writeHead(401, {'WWW-Authenticate': 'Basic realm=synthetic'});}
  response.end('invented fixture');
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = 'http://127.0.0.1:' + server.address().port;
composition = nativeComposition(origin, allocation);
const child = spawn('/opt/chrome-linux64/chrome', ['--headless=new', '--no-startup-window', '--remote-debugging-pipe',
  '--disable-background-networking', '--disable-extensions', '--disable-component-extensions-with-background-pages',
  '--disable-component-update', '--disable-default-apps', '--disable-popup-blocking', '--no-first-run', '--no-default-browser-check'],
  {detached: true, env: {PATH: '/usr/bin:/bin', HOME: '/home/fixture'}, stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe']});
const exit = once(child, 'exit').then(() => {exited = true; record({lifecycle: 'owned-exit'});});
function stopOwned() {
  if (!stopped) stopped = (async () => {
    record({lifecycle: 'stop-owned', fenced});
    if (!exited) {
      if (scenario === 'forced-stop') process.kill(-child.pid, 'SIGSTOP');
      if (scenario === 'browser-crash') {crashed = true; process.kill(-child.pid, 'SIGKILL');}
      else process.kill(-child.pid, 'SIGTERM');
      let timer;
      await Promise.race([exit, new Promise(resolve => {timer = setTimeout(resolve, 5000);})]); clearTimeout(timer);
      if (!exited) {forceKilled = true; process.kill(-child.pid, 'SIGKILL');
        await Promise.race([exit, new Promise((_, reject) => setTimeout(() => reject(new Error('NATIVE_EXIT_UNVERIFIED')), 5000))]);}
    }
    return exited;
  })();
  return stopped;
}
function fatal() {
  fenced = true; releaseHeld();
  if (controller) void controller.abort().catch(() => {});
  return ordering ? ordering.abort() : stopOwned();
}
function track(promise) {
  tasks.add(promise);
  void promise.catch(() => fatal()).catch(() => {}).finally(() => tasks.delete(promise));
}
function send(method, params = {}, session) {
  if (fenced) return Promise.reject(new Error('NATIVE_FENCED'));
  return pipe.send(method, params, session);
}
pipe = capabilityPipe({write: raw => {
  const command = JSON.parse(raw.subarray(0, -1)); record({command: command.method});
  return new Promise((resolve, reject) => child.stdio[3].write(raw, error => error ? reject(error) : resolve()));
}, fence: () => {void fatal().catch(() => {});}, onEvent: event => {
  if (fenced) return;
  counts[event.method] = (counts[event.method] || 0) + 1;
  if (['Target.targetCreated', 'Target.attachedToTarget'].includes(event.method)) {
    record({event: event.method, type: event.params.targetInfo?.type, waiting: event.params.waitingForDebugger});
    if (negative && bootstrap.ready()) {
      if (event.method === 'Target.attachedToTarget') {
        pipe.registerSession(event.params.sessionId); track(pipe.send('Runtime.runIfWaitingForDebugger', {}, event.params.sessionId));
      }
    } else bootstrap.event(event);
  }
  if (capture) {
    const p = event.params;
    const relevant = (event.method === 'Network.requestWillBeSent' && p.type === 'Document' && p.frameId === rootFrame)
      || (event.method === 'Fetch.requestPaused' && p.resourceType === 'Document' && p.frameId === rootFrame)
      || (event.method === 'Page.frameNavigated' && p.frame?.id === rootFrame)
      || (event.method === 'Page.lifecycleEvent' && p.name === 'load' && p.frameId === rootFrame);
    if (relevant) capture.event(event);
  }
  if (event.method === 'Fetch.authRequired') {
    if (!controller) {void fatal().catch(() => {}); return;}
    track(controller.authRequired({sessionId: event.sessionId, requestId: event.params.requestId}));
    fenced = true; return;
  }
  if (event.method === 'Fetch.requestPaused') {
    const p = event.params;
    record({pause: new URL(p.request.url).pathname, method: p.request.method, resource: p.resourceType,
      ownedFrame: p.frameId === rootFrame, redirect: Object.hasOwn(p, 'redirectedRequestId')});
    if (!controller) {void fatal().catch(() => {}); return;}
    const metadata = {requestId: p.requestId, sessionId: event.sessionId, frameId: p.frameId,
      pageEpoch, frameEpoch: rootEpoch, resourceType: p.resourceType,
      request: {url: p.request.url, method: p.request.method},
      ...(Object.hasOwn(p, 'redirectedRequestId') ? {redirectedRequestId: p.redirectedRequestId} : {})};
    if (scenario === 'pipe-loss' && p.request.url === origin + '/forbidden') {
      child.stdio[4].destroy(); void fatal().catch(() => {}); return;
    }
    const realFsync = fs.fsyncSync;
    if (scenario === 'fsync-failure' && p.request.url === origin + '/allowed') {
      fs.fsyncSync = () => {fsyncFailed = true; throw new Error('NATIVE_FSYNC_FAILED');};
      const pending = controller.paused(metadata); track(pending.finally(() => {fs.fsyncSync = realFsync;}));
    } else track(controller.paused(metadata));
    if (controller.status().fenced) void fatal().catch(() => {});
  }
}});
child.stderr.on('data', bytes => {stderrBytes += bytes.length; if (stderrBytes > 1048576) void fatal().catch(() => {});});
child.stdio[4].on('data', bytes => {try {pipe.receive(bytes);} catch { /* Already fenced. */ }});
child.stdio[4].on('end', pipe.lost); child.stdio[4].on('close', pipe.lost);
ordering = orderingExperiment({send: (method, params, session) => negative && method === 'Fetch.enable'
  ? Promise.resolve({}) : send(method, params, session), installRoutes: () => {}, stopOwned,
  closePipe: () => {record({lifecycle: 'close-pipe', exited}); child.stdio[3].destroy(); child.stdio[4].destroy();},
  beforeResume: async session => {
    const tree = (await send('Page.getFrameTree', {}, session)).frameTree;
    if (!tree || tree.frame.url !== 'about:blank' || tree.childFrames?.length) throw new Error('NATIVE_ROOT_REJECTED');
    rootFrame = tree.frame.id; pageEpoch = randomUUID(); rootEpoch = randomUUID();
    composition.enroll(); handle = composition.acquirePrincipal();
    composition.startAttempt(handle, 100); composition.transition(handle, 'password_uncertain', 100);
    const source = {schema_version: 1, origin, roles: {password: {url: origin + '/allowed', method: 'POST',
      resource_type: 'XHR', evidence: 'invented owned native fixture'}, app_method: null, otp: null}};
    permitNonce = composition.armPermit(handle, {phase: 'password_uncertain', page_epoch: pageEpoch,
      frame_epoch: rootEpoch, url: origin + '/allowed', method: 'POST', resource_type: 'XHR'}, 100, source);
    const reads = ['/root', '/document'].map(path => ({role: 'source', url: origin + path, method: 'GET', resourceType: 'Document'}));
    if (scenario === 'http-auth') reads.push({role: 'source', url: origin + '/challenge', method: 'GET', resourceType: 'XHR'});
    controller = composition.controller(handle, {binding: {targetId: nativeTarget, sessionId: session, pageEpoch,
      frames: {[rootFrame]: {epoch: rootEpoch, role: 'source'}}}, source, reads, now: () => 101,
      continueRequest: async requestId => {
        const saved = parse(fs.readFileSync(handle.directory + '/journal.yaml', 'utf8'));
        // Count durable consumption only for the first consumed permit; no URL replacement.
        if (!consumes && saved.attempts[handle.attempt].permit?.consumed === true) consumes++;
        if (scenario === 'held-auth' && consumes) {held = true; await heldRequest;}
        if (scenario === 'browser-crash' && consumes) {await fatal(); throw new Error('NATIVE_SIMULATED_CRASH');}
        return send('Fetch.continueRequest', {requestId}, session);
      }, cancelAuth: requestId => {
        fenced = true;
        const result = pipe.send('Fetch.continueWithAuth', {requestId, authChallengeResponse: {response: 'CancelAuth'}}, session);
        record({cancel: 'CancelAuth'}); cancelled++;
        return result.then(value => {cancelAcknowledged++; return value;});
      }, stop: async () => {fenced = true; await ordering.abort(); return exited;}});
    controller.arm({phase: 'password_uncertain', nonce: permitNonce, pageEpoch, frameEpoch: rootEpoch,
      frameId: rootFrame, url: origin + '/allowed', method: 'POST', resourceType: 'XHR'});
  }});
bootstrap = bootstrapExperiment({send, registerSession: pipe.registerSession,
  initialize: (session, waiting, targetId) => {nativeTarget = targetId; return ordering.initialize(session, waiting);}, stop: fatal});
pipe.armEvents();
let failure;
try {
  owner = await bootstrap.start();
  if (captureMode) {
    const results = [];
    for (let index = 0; index < (scenario === 'capture' ? 2 : 1); index++) {
      capture = nativeCapture({binding: {targetId: owner.targetId, sessionId: owner.sessionId, frameId: rootFrame, pageEpoch, frameEpoch: rootEpoch},
        url: origin + '/document', account: 'invented-account', day: '2026-09-17', role: 'statement',
        active: async () => {
          const frame = (await send('Page.getFrameTree', {}, owner.sessionId)).frameTree.frame;
          return {...owner, frameId: frame.id, pageEpoch, frameEpoch: rootEpoch, url: frame.url, loaderId: frame.loaderId};
        }, serialize: async () => (await send('Runtime.evaluate', {
          expression: "JSON.stringify({account:document.querySelector('main')?.dataset.account,day:document.querySelector('main')?.dataset.day,role:document.querySelector('main')?.dataset.role,operation:document.querySelector('main')?.dataset.operation,body:document.body.innerHTML})",
          returnByValue: true}, owner.sessionId)).result.value});
      capture.arm(); capture.navigation(await send('Page.navigate', {url: origin + '/document'}, owner.sessionId));
      const deadline = Date.now() + 5000;
      while (!fenced && !capture.ready() && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 10));
      try {results.push(await capture.capture());} catch {captureRefused = true;}
      capture = undefined;
    }
    captureResult = {accepted: results.length, fresh: results.length === 2 && results[0].body === results[1].body
      && results[0].loaderId !== results[1].loaderId && results[0].requestId !== results[1].requestId,
      native: results.map(({body,...value}) => ({...value,body_sha256:createHash('sha256').update(body).digest('hex')}))};
  } else {
    try {await send('Page.navigate', {url: origin + '/root'}, owner.sessionId);} catch { /* Fatal request may interrupt navigation. */ }
  }
  await new Promise(resolve => setTimeout(resolve, 1000));
} catch {failure = 'NATIVE_EXECUTION_FAILED';}
finally {
  await fatal(); await Promise.allSettled([...tasks]);
  if (handle) {
    composition.releasePrincipal(handle);
    const result = spawnSync(process.execPath, ['/home/fixture/proof/lab/native-restart.mjs', origin, allocation],
      {env: {HOME: '/home/fixture', PATH: '/usr/bin:/bin'}, encoding: 'utf8', timeout: 5000, maxBuffer: 32768});
    restartFenced = result.status === 0 && result.stdout.trim() === 'FIXTURE_RESTART_FENCED';
  }
  await new Promise(resolve => server.close(resolve));
}
const evidence = {mode, node: process.version, failure, allowed, forbidden, consumes, held,
  challenges, cancelled, cancelAcknowledged, captureResult, captureRefused, restartFenced, fsyncFailed, forceKilled, crashed,
  trace, counts, owned_browser_exit: exited, online_ready: false, browser_proven: false, import_ready: false};
const verdict = nativeVerdict(evidence);
console.log(JSON.stringify({...evidence,...verdict}));
if (!verdict.passed) process.exitCode = 1;
