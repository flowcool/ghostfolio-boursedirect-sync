// Final-code synthetic proof: real guarded Chromium, fake login site, delayed
// OTP IPC. Network-none container, no broker endpoints or live credentials.
import fs from 'node:fs';
import http from 'node:http';
import {spawn} from 'node:child_process';
import {randomUUID, createHash} from 'node:crypto';
import {once} from 'node:events';
import {parse} from 'yaml';
import {principal} from '../core.mjs';
import {nativeComposition} from './native-composition.mjs';
import {capabilityPipe} from '../capability-pipe.mjs';
import {orderingExperiment} from '../capability-ordering.mjs';
import {bootstrapExperiment} from '../capability-bootstrap.mjs';
import {privateChannel} from '../private-channel.mjs';
import {delayedOtpProvider, validateProviderCode} from '../credential-provider.mjs';

process.umask(0o077);
let fenced = false, child, exit, exited = false, stopping, pipe, ordering, handle, authority, controller;
const ipc = privateChannel({input: process.stdin, output: process.stdout, fence: () => {void fatal();}});
function now() {return Math.floor(Date.now() / 1000);}
async function stopOwned() {
  if (!stopping) stopping = (async () => {
    if (child && !exited) {
      try {process.kill(-child.pid, 'SIGTERM');} catch { /* Verify exit below. */ }
      let timer;
      await Promise.race([exit, new Promise(resolve => {timer = setTimeout(resolve, 3000);})]); clearTimeout(timer);
      if (!exited) {try {process.kill(-child.pid, 'SIGKILL');} catch { /* Exit verification remains required. */ }
        await Promise.race([exit, new Promise((_,reject) => {timer = setTimeout(() => reject(new Error()), 3000);})]); clearTimeout(timer);}
    }
    return exited;
  })();
  return stopping;
}
function fatal() {fenced = true; return ordering ? ordering.abort() : stopOwned();}
const tasks = new Set();
function track(promise) {tasks.add(promise); void promise.catch(() => fatal()).catch(() => {}).finally(() => tasks.delete(promise));}
let server, passwordPosts = 0, otpPosts = 0, challenge = false, authenticated = false;
let result = {passed: false, stage: 'initialize', online_ready: false, browser_proven: false, import_ready: false};
try {
  const input = await ipc.receive(), {expected, allocation, scenario} = input;
  if (!['success','wrong-stage','expired','fsync','pipe-loss','browser-crash'].includes(scenario)
      || principal(process.env.BD_LOGIN) !== input.binding.principalHash
      || process.env.BD_LOGIN !== 'SYNTHETIC' || process.env.BD_PASSWORD !== 'SYNTHETIC_PASSWORD') throw new Error();
  const config = input.binding.accountConfig;
  const fd = fs.openSync(config.path, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
  try {
    const stat = fs.fstatSync(fd);
    if (!stat.isFile() || stat.nlink !== 1 || stat.uid !== process.getuid() || (stat.mode & 0o077)
        || stat.size > 1048576 || createHash('sha256').update(fs.readFileSync(fd)).digest('hex') !== config.sha256) throw new Error();
  } finally {fs.closeSync(fd);}
  server = http.createServer((request,response) => {
    if (request.url === '/login' && request.method === 'GET') {
      response.setHeader('Content-Type','text/html');
      response.end('<link rel=icon href="data:,"><input id=login><input id=password><input id=otp><main id=state>login</main>'); return;
    }
    let raw = ''; request.on('data', bytes => {raw += bytes; if (raw.length > 4096) request.destroy();});
    request.on('end', () => {
      if (request.url === '/password' && request.method === 'POST') {
        passwordPosts++; challenge = raw === JSON.stringify({login: 'SYNTHETIC', password: 'SYNTHETIC_PASSWORD'});
        response.end(challenge ? 'challenge' : 'refused'); return;
      }
      if (request.url === '/otp' && request.method === 'POST') {
        otpPosts++; authenticated = challenge && raw === '123456'; response.end(authenticated ? 'authenticated' : 'refused'); return;
      }
      response.writeHead(403); response.end('refused');
    });
  });
  await new Promise(resolve => server.listen(48123, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:48123';
  authority = nativeComposition(origin, allocation);
  // Enrollment must already exist in the restored canonical root; no enroll here.
  handle = authority.acquirePrincipal(); authority.startAttempt(handle, now());
  child = spawn('/opt/chrome-headless-shell-linux64/chrome-headless-shell', ['--no-startup-window','--remote-debugging-pipe',
    '--disable-background-networking','--disable-extensions','--disable-component-extensions-with-background-pages',
    '--disable-component-update','--disable-default-apps','--disable-popup-blocking','--no-first-run','--no-default-browser-check'],
    {detached: true, env: {PATH: '/usr/bin:/bin', HOME: '/home/fixture'}, stdio: ['ignore','ignore','pipe','pipe','pipe']});
  exit = once(child, 'exit').then(() => {exited = true;});
  let stderrBytes = 0; child.stderr.on('data', bytes => {
    stderrBytes += bytes.length;
    if (/Operation not permitted|No usable sandbox|Failed to move to new namespace/.test(bytes.toString())) result.sandboxUnavailable = true;
    if (stderrBytes > 1048576) void fatal();
  });
  const pageEpoch = randomUUID(), frameEpoch = randomUUID(); let frameId, owner;
  const source = {schema_version: 1, origin, roles: {password: {url: origin + '/password', method: 'POST', resource_type: 'XHR', evidence: 'invented'},
    app_method: null, otp: {url: origin + '/otp', method: 'POST', resource_type: 'XHR', evidence: 'invented'}}};
  function send(method, params = {}, session) {
    if (fenced) throw new Error(); result.lastCommand = method;
    return pipe.send(method, params, session);
  }
  pipe = capabilityPipe({write: bytes => new Promise((resolve,reject) => child.stdio[3].write(bytes, error => error ? reject(error) : resolve())),
    fence: () => {void fatal();}, onEvent: event => {
      if (fenced) return;
      if (['Target.targetCreated','Target.attachedToTarget'].includes(event.method)) {
        const type = event.params.targetInfo?.type;
        if (['browser','tab','page','worker','service_worker','shared_worker','iframe'].includes(type)) result.lastTargetType = type;
        bootstrap.event(event);
      }
      if (event.method === 'Fetch.authRequired') track(controller.authRequired({sessionId: event.sessionId, requestId: event.params.requestId}));
      if (event.method === 'Fetch.requestPaused') {
        const p = event.params;
        if (['Document','XHR','Fetch'].includes(p.resourceType)) result.lastResourceType = p.resourceType;
        track(controller.paused({requestId: p.requestId, sessionId: event.sessionId, frameId: p.frameId, pageEpoch, frameEpoch,
          resourceType: p.resourceType, request: {url: p.request.url, method: p.request.method},
          ...(Object.hasOwn(p,'redirectedRequestId') ? {redirectedRequestId: p.redirectedRequestId} : {})}));
      }
    }});
  let startupBytes = Buffer.alloc(0);
  child.stdio[4].on('data', bytes => {
    if (result.stage === 'bootstrap' && startupBytes.length + bytes.length <= 1048576) {
      startupBytes = Buffer.concat([startupBytes, bytes]);
      fs.writeFileSync('/home/fixture/bootstrap-protocol.bytes', startupBytes, {mode: 0o600});
    }
    try {pipe.receive(bytes);} catch { /* Already fenced. */ }
  });
  child.stdio[4].on('end', pipe.lost); child.stdio[4].on('close', pipe.lost);
  function makeController(session) {
    return authority.controller(handle, {binding: {targetId: owner.targetId, sessionId: session, pageEpoch,
      frames: {[frameId]: {epoch: frameEpoch, role: 'source'}}}, source,
      reads: [{role:'source', url:origin + '/login', method:'GET', resourceType:'Document'}],
      now, continueRequest: requestId => send('Fetch.continueRequest',{requestId},session),
      cancelAuth: requestId => pipe.send('Fetch.continueWithAuth',{requestId,authChallengeResponse:{response:'CancelAuth'}},session),
      stop: fatal});
  }
  ordering = orderingExperiment({send, installRoutes: () => {}, stopOwned,
    closePipe: () => {child.stdio[3].destroy(); child.stdio[4].destroy();}, beforeResume: async session => {
      result.stage = 'frame-binding';
      const tree = (await send('Page.getFrameTree',{},session)).frameTree;
      if (!['', 'about:blank'].includes(tree.frame.url) || tree.childFrames?.length) throw new Error();
      frameId = tree.frame.id;
      result.stage = 'controller-binding';
      controller = makeController(session);
    }});
  const bootstrap = bootstrapExperiment({send, registerSession: pipe.registerSession, expectedVersion: input.chromeVersion, product: 'HeadlessChrome',
    initialize: (session, waiting, targetId) => {owner = {targetId}; return ordering.initialize(session, waiting);}, stop: fatal});
  pipe.armEvents();
  result.stage = 'bootstrap';
  owner = await bootstrap.start();
  result.stage = 'version';
  const version = await send('Browser.getVersion');
  if (version.product !== 'HeadlessChrome/' + input.chromeVersion) throw new Error();
  await send('Page.navigate',{url:origin + '/login'},owner.sessionId);
  result.stage = 'navigation';
  async function evaluate(expression) {
    const value = await send('Runtime.evaluate',{expression, awaitPromise:true, returnByValue:true},owner.sessionId);
    if (value.exceptionDetails) throw new Error(); return value.result.value;
  }
  const deadline = Date.now() + 5000;
  while (!await evaluate('!!document.querySelector("#state")')) {if (Date.now() > deadline) throw new Error(); await new Promise(resolve=>setTimeout(resolve,10));}
  function arm(phase, otp) {
    const role = phase === 'password_uncertain' ? source.roles.password : source.roles.otp;
    const nonce = authority.armPermit(handle, {phase,page_epoch:pageEpoch,frame_epoch:frameEpoch,url:role.url,method:'POST',resource_type:role.resource_type},now(),source);
    controller.arm({phase,nonce,pageEpoch,frameEpoch,frameId,url:role.url,method:'POST',resourceType:role.resource_type,...(otp ? {otp} : {})});
  }
  authority.transition(handle,'password_uncertain',now()); arm('password_uncertain');
  result.stage = 'password';
  const loginBody = JSON.stringify({login:process.env.BD_LOGIN,password:process.env.BD_PASSWORD});
  const seen = await evaluate(`fetch('/password',{method:'POST',body:${JSON.stringify(loginBody)}}).then(r=>r.text()).then(s=>{document.querySelector('#state').textContent=s;return s;})`);
  if (seen !== 'challenge' || !challenge || passwordPosts !== 1) throw new Error();
  authority.transition(handle,'password_accepted',now()); controller = makeController(owner.sessionId);
  // One deliberate request starts early in a step; no code has been fetched yet.
  if (now() % 30 > 20) await new Promise(resolve => setTimeout(resolve, (30 - now()%30)*1000 + 50));
  const provider = delayedOtpProvider({...expected, now, fetchCode: async request => {
    const waiting = ipc.receive(); await ipc.send(request); return waiting;
  }});
  result.stage = 'provider';
  const response = await provider.request(expected);
  if (scenario === 'expired') await new Promise(resolve=>setTimeout(resolve,(30-now()%30)*1000+50));
  // Revalidate timing after the awaited provider before transition and fill.
  validateProviderCode({...expected,code:response.code,startedAt:response.otp.issuedAt,completedAt:now(),profile:input.binding.profile}, expected, now());
  const realFsync = fs.fsyncSync;
  if (scenario === 'fsync') fs.fsyncSync = () => {throw new Error('SYNTHETIC_FSYNC_FAILURE');};
  try {authority.transition(handle,'otp_uncertain',now()); arm('otp_uncertain',response.otp);} finally {fs.fsyncSync = realFsync;}
  validateProviderCode({...expected,code:response.code,startedAt:response.otp.issuedAt,completedAt:now(),profile:input.binding.profile}, expected, now());
  if (scenario === 'pipe-loss') {child.stdio[4].destroy(); await fatal(); throw new Error();}
  if (scenario === 'browser-crash') {process.kill(-child.pid,'SIGKILL'); await exit; throw new Error();}
  const outcome = await evaluate(`fetch('/otp',{method:'POST',body:${JSON.stringify(response.code)}}).then(r=>r.text()).then(s=>{document.querySelector('#state').textContent=s;return s;})`);
  if (outcome !== 'authenticated' || !authenticated || otpPosts !== 1) throw new Error();
  authority.transition(handle,'authenticated',now());
  // Retain authenticated uncertainty (not a claim of an actual broker success).
  result.passed = true;
  result.stage = 'complete';
} catch (error) {
  result.error = 'SYNTHETIC_COMPOSITION_REFUSED';
  if (typeof error?.message === 'string' && /^(CAPABILITY|AUTH|REQUEST|PROVIDER)_[A-Z_]+$/.test(error.message)) result.code = error.message;
}
finally {
  await fatal().catch(() => {}); await Promise.allSettled([...tasks]);
  if (handle) {
    const state = parse(fs.readFileSync(handle.directory + '/journal.yaml','utf8'));
    result.retainedState = state.attempts[handle.attempt]?.state;
    authority.releasePrincipal(handle);
    const reopened = authority.acquirePrincipal();
    try {authority.startAttempt(reopened,now()); result.restartFenced = false;} catch {result.restartFenced = true;}
    authority.releasePrincipal(reopened);
  }
  if (server) await new Promise(resolve=>server.close(resolve));
  result.passwordPosts = passwordPosts; result.otpPosts = otpPosts; result.browserExited = exited;
  await ipc.send(result).catch(() => {}); process.stdin.destroy();
}
