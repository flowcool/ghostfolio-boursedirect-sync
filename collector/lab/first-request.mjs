// Opt-in synthetic browser experiment. Copied into an owned network-none container.
// This establishes only the listed dispatch scenarios, never complete qualification.
import http from 'node:http';
import {parse} from 'yaml';
import {fixtureVerdict} from './verdict.mjs';
import fs from 'node:fs';
import {randomUUID} from 'node:crypto';
import * as core from './core.mjs';
import {spawn, spawnSync} from 'node:child_process';
import {once} from 'node:events';
import {capabilityPipe} from './capability-pipe.mjs';
import {orderingExperiment} from './capability-ordering.mjs';
import {proveCapture} from './capture-document.mjs';
import {bootstrapExperiment} from './capability-bootstrap.mjs';

const mode = process.argv[2];
const scenarios=parse(fs.readFileSync(new URL('./scenarios.yaml',import.meta.url),'utf8'));
const modes=Object.keys(scenarios);
if (!modes.includes(mode)
    || process.version !== 'v20.19.2') throw new Error('FIXTURE_RUNTIME_REJECTED');
const counts = {}, trace = [], documentEvents = [];
let captureEvidence, documentVariant=0, queuedForbidden=0, releaseQueued;
const queuedReady=new Promise(resolve=>{releaseQueued=resolve;});
let forbidden = 0, allowed = 0, durableConsumes = 0, consumed = false, challenges = 0, cancelled = 0, policyPauses = 0;
const popup = mode.startsWith('popup');
const negative = mode.endsWith('negative');
const scenario = mode.replace(/-negative$/, '');
function rootDocument() {
  if (scenario === 'capture') return '<main>invented replacement navigation</main>';
  if (scenario === 'late-guard') return `<script>fetch('/forbidden',{method:'POST'})</script>`;
  if (popup) return '<form id=f method=POST action=/forbidden target=_blank><input name=x value=fixture></form><script>f.submit()</script>';
  if (scenario === 'frame') return `<iframe srcdoc="<form id=f method=POST action=/forbidden></form><script>f.submit()</script>"></iframe>`;
  if (scenario === 'worker') return `<script>new Worker('/forbidden')</script>`;
  if (scenario === 'shared-worker') return `<script>new SharedWorker('/forbidden')</script>`;
  if (scenario === 'service-worker') return `<script>navigator.serviceWorker.register('/forbidden')</script>`;
  if (scenario.startsWith('redirect')) return `<script>fetch('/allowed',{method:'POST'})</script>`;
  if (scenario === 'second-auth') return `<script>fetch('/allowed',{method:'POST'}).then(()=>fetch('/allowed',{method:'POST'}))</script>`;
  if (scenario === 'concurrent') return `<script>fetch('/allowed',{method:'POST'});fetch('/allowed',{method:'POST'})</script>`;
  if (['fsync-failure','browser-crash'].includes(scenario)) return `<script>fetch('/allowed',{method:'POST'})</script>`;
  if (['pipe-loss','forced-stop'].includes(scenario)) return `<script>fetch('/forbidden',{method:'POST'});fetch('/forbidden',{method:'POST'})</script>`;
  if (scenario === 'http-auth') return `<script>fetch('/challenge')</script>`;
  return `<script>fetch('${mode === 'permitted' ? '/allowed' : '/forbidden'}',{method:'POST'})</script>`;
}
const server = http.createServer((request, response) => {
  if (request.url === '/document') {
    response.setHeader('content-type', 'text/html');
    const account=documentVariant===2?'invented-other-account':'synthetic-account';
    const day=documentVariant===3?'2026-09-18':'2026-09-17';
    const role=documentVariant===4?'invented-other-role':'statement';
    const operation=documentVariant===5?'unknown':'known';
    response.end(`<main data-account=${account} data-day=${day} data-role=${role} data-operation=${operation}>identical invented document</main>`);
  } else if (request.url === '/root') {
    response.setHeader('content-type', 'text/html');
    response.end(rootDocument());
  } else {
    if (request.url === '/forbidden') {forbidden++;response.setHeader('content-type','application/javascript');}
    if (request.url === '/challenge') {challenges++;response.writeHead(401, {'WWW-Authenticate': 'Basic realm=synthetic'});}
    if (request.url === '/allowed' && scenario.startsWith('redirect')) response.writeHead(Number(scenario.slice(8)), {Location: '/forbidden'});
    if (request.url === '/allowed') allowed++;
    response.end('fixture');
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = 'http://127.0.0.1:' + server.address().port;
let bootstrap, ordering, owner, rootFrame, authority, requestQueue=Promise.resolve(), restartedFenced=false, fsyncFailed=false, forceKilled=false, crashed=false, lost=false, exited = false, stopped, stderrBytes = 0;
const child = spawn('/opt/chrome-linux64/chrome', [
  '--headless=new', '--no-startup-window', '--remote-debugging-pipe',
  '--disable-background-networking', '--disable-extensions',
  '--disable-component-extensions-with-background-pages', '--disable-component-update',
  '--disable-default-apps', '--disable-popup-blocking', '--no-first-run', '--no-default-browser-check',
], {detached: true, env: {PATH: '/usr/bin:/bin', HOME: '/home/fixture'},
  stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe']});
const exit = once(child, 'exit').then(() => {exited = true; record({lifecycle:'owned-exit'});});
function stopOwned() {
  if (!stopped) stopped = (async () => {
    record({lifecycle:'stop-owned',fenced:ordering.fenced()});
    if (!exited) {
      if(mode==='forced-stop')process.kill(-child.pid,'SIGSTOP');
      process.kill(-child.pid, 'SIGTERM');
      let timer;
      await Promise.race([exit, new Promise(resolve => {timer = setTimeout(resolve, 5000);})]);
      clearTimeout(timer);
      if (!exited) {forceKilled=true;process.kill(-child.pid, 'SIGKILL'); await exit;}
    }
    return true;
  })();
  return stopped;
}
function record(item) {
  if (trace.length >= 1000) {void ordering.abort().catch(() => {}); throw new Error('FIXTURE_TRACE_LIMIT');}
  trace.push(item);
}
const pipe = capabilityPipe({
  write: bytes => {
    record({command: JSON.parse(bytes.toString().slice(0, -1)).method});
    return new Promise((resolve, reject) => child.stdio[3].write(bytes, error => error ? reject(error) : resolve()));
  },
  onEvent: event => {
    if (ordering.fenced()) return;
    if (mode === 'capture' && ['Network.requestWillBeSent','Page.frameNavigated','Page.lifecycleEvent','Fetch.requestPaused'].includes(event.method)) {
      if(documentEvents.length>=1000)throw new Error('FIXTURE_DOCUMENT_LIMIT');
      documentEvents.push(structuredClone(event));
    }
    counts[event.method] = (counts[event.method] || 0) + 1;
    if (event.method.startsWith('Target.')) record({event: event.method,
      type: event.params.targetInfo?.type, waiting: event.params.waitingForDebugger});
    if (['Target.targetCreated', 'Target.attachedToTarget'].includes(event.method)) {
      // Deliberately unsafe popup negative control, restricted to invented fixture.
      if (negative && bootstrap.ready()) {
        if (event.method === 'Target.attachedToTarget') {
          pipe.registerSession(event.params.sessionId);
          void pipe.send('Runtime.runIfWaitingForDebugger', {}, event.params.sessionId).catch(() => {});
        }
      } else bootstrap.event(event);
    }
    if (event.method === 'Fetch.authRequired') {void ordering.cancelHttpAuth(event.sessionId,event.params.requestId).then(()=>cancelled++).catch(()=>{});}
    if (event.method === 'Fetch.requestPaused') {
      policyPauses++;
      const request = event.params.request;
      record({pause: new URL(request.url).pathname, method: request.method, resource: event.params.resourceType, ownedFrame: event.params.frameId === rootFrame, redirect: event.params.redirectedRequestId !== undefined});
      if(['pipe-loss','forced-stop'].includes(mode)&&new URL(request.url).pathname==='/forbidden'){
        queuedForbidden++;if(queuedForbidden===2)releaseQueued();
      }
      const params=structuredClone(event.params), session=event.sessionId;
      requestQueue=requestQueue.then(async()=>{
        if(ordering.fenced())return;
        const request=params.request;
        const navigation=session===owner.sessionId&&params.frameId===rootFrame&&[origin+'/root',origin+'/document',origin+'/favicon.ico',...(scenario==='http-auth'?[origin+'/challenge']:[])].includes(request.url)&&request.method==='GET'&&params.redirectedRequestId===undefined;
        const permitted=request.url===origin+'/allowed'&&request.method==='POST'&&!consumed&&params.resourceType==='XHR'&&params.redirectedRequestId===undefined&&session===owner.sessionId&&params.frameId===rootFrame;
        if(['pipe-loss','forced-stop'].includes(mode)&&request.url===origin+'/forbidden'){
          let timer;
          await Promise.race([queuedReady,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('FIXTURE_QUEUE_INCONCLUSIVE')),2000);})]);
          clearTimeout(timer);
        }
        if(navigation){await pipe.send('Fetch.continueRequest',{requestId:params.requestId},session);return;}
        if(permitted){
          consumed=true;
          if(authority){
            const realFsync=fs.fsyncSync;
            try{
              if(mode==='fsync-failure')fs.fsyncSync=()=>{fsyncFailed=true;throw new Error('FIXTURE_FSYNC_FAILURE');};
              core.consumePermit(authority.handle,{...authority.request,method:request.method,resource_type:params.resourceType},101);durableConsumes++;
            }finally{fs.fsyncSync=realFsync;}
          }
          if(mode==='browser-crash'){
            crashed=true;process.kill(-child.pid,'SIGKILL');await exit;
            await ordering.abort();return;
          }
          await pipe.send('Fetch.continueRequest',{requestId:params.requestId},session);
        }else if(mode==='pipe-loss'){
          lost=true;child.stdio[4].destroy();
        }else await ordering.abort();
      }).catch(async()=>{await ordering.abort();});
    }
  },
  fence: () => {void ordering.abort().catch(() => {});},
});
child.stderr.on('data', bytes => {
  stderrBytes += bytes.length;
  if (stderrBytes > 1048576) void ordering.abort().catch(() => {});
});
child.stdio[4].on('data', bytes => {try {pipe.receive(bytes);} catch { /* Pipe has already fenced. */ }});
child.stdio[4].on('end', () => pipe.lost());
child.stdio[4].on('close', () => pipe.lost());
ordering = orderingExperiment({
  send: (method, params, session) => negative && method === 'Fetch.enable'
    ? Promise.resolve({}) : pipe.send(method, params, session),
  installRoutes: () => {}, stopOwned,
  closePipe: () => {record({lifecycle:'close-pipe',exited});child.stdio[3].destroy(); child.stdio[4].destroy();},
});
bootstrap = bootstrapExperiment({send: pipe.send, registerSession: pipe.registerSession,
  initialize: ordering.initialize, stop: ordering.abort});
pipe.armEvents();
let failure;
try {
  owner = await bootstrap.start();
  rootFrame=(await pipe.send('Page.getFrameTree',{},owner.sessionId)).frameTree.frame.id;
  if(['concurrent','fsync-failure','browser-crash'].includes(mode)){
    core.enroll('SYNTHETIC-CAPABILITY');const handle=core.acquirePrincipal('SYNTHETIC-CAPABILITY');
    core.startAttempt(handle,100);core.transition(handle,'password_uncertain',100);
    const source={schema_version:1,origin:core.ORIGIN,roles:{password:{url:core.ORIGIN+'/synthetic-capability-password',method:'POST',resource_type:'XHR',evidence:'invented isolated loopback fixture'},app_method:null,otp:null}};
    const permit={phase:'password_uncertain',page_epoch:randomUUID(),frame_epoch:randomUUID(),url:source.roles.password.url,method:'POST',resource_type:'XHR'};
    const nonce=core.armPermit(handle,permit,100,source);authority={handle,request:{...permit,nonce,redirect:false}};
  }
  if(mode==='capture'){
    captureEvidence=await proveCapture({pipe,owner,rootFrame,origin,events:documentEvents,setDocumentVariant:value=>{documentVariant=value;}});
  }else{
    try {await pipe.send('Page.navigate', {url: origin + '/root'}, owner.sessionId);} catch { /* Rejection may stop navigation. */ }
    if(mode==='late-guard-negative'){
      await new Promise(resolve=>setTimeout(resolve,500));
      await pipe.send('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}],handleAuthRequests:true},owner.sessionId);
    }
  }
  // Bounded observation is a fixture measurement, never uncertain-write resolution.
  await new Promise(resolve => setTimeout(resolve, 1000));
} catch {
  failure = 'FIXTURE_STARTUP_FAILED';
} finally {
  await ordering.abort();await requestQueue;
  if(authority){
    core.releasePrincipal(authority.handle);
    const restarted=spawnSync(process.execPath,['/home/fixture/proof/restart-principal.mjs'],{env:{PATH:'/usr/bin:/bin',HOME:'/home/fixture'},encoding:'utf8',timeout:10000,maxBuffer:32768});
    restartedFenced=restarted.status===0&&restarted.stdout.trim()==='FIXTURE_RESTART_FENCED';
  }
  await new Promise(resolve => server.close(resolve));
}
const evidence={mode, node:process.version, failure, allowed, forbidden,
  owned_browser_exit:exited, durableConsumes, queuedForbidden, restartedFenced,
  fsyncFailed, forceKilled, crashed, lost, challenges, cancelled, policyPauses,
  counts, trace, captureEvidence, browser_proven:false};
const verdict=fixtureVerdict(evidence,scenarios[mode]);
console.log(JSON.stringify({...evidence,...verdict}));
if(!verdict.passed)process.exitCode=1;
