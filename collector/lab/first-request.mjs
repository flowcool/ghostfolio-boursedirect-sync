// Opt-in synthetic browser experiment. Copied into an owned network-none container.
// This establishes only the listed dispatch scenarios, never complete qualification.
import http from 'node:http';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {capabilityPipe} from './capability-pipe.mjs';
import {orderingExperiment} from './capability-ordering.mjs';
import {bootstrapExperiment} from './capability-bootstrap.mjs';

const mode = process.argv[2];
if (!['permitted', 'denied', 'negative', 'popup', 'popup-negative'].includes(mode)
    || process.version !== 'v20.19.2') throw new Error('FIXTURE_RUNTIME_REJECTED');
const counts = {}, trace = [];
let forbidden = 0, allowed = 0, consumed = false;
const popup = mode.startsWith('popup');
const negative = mode.endsWith('negative');
const server = http.createServer((request, response) => {
  if (request.url === '/root') {
    response.setHeader('content-type', 'text/html');
    response.end(popup
      ? '<form id=f method=POST action=/forbidden target=_blank><input name=x value=fixture></form><script>f.submit()</script>'
      : `<script>fetch('${mode === 'permitted' ? '/allowed' : '/forbidden'}',{method:'POST'})</script>`);
  } else {
    if (request.url === '/forbidden') forbidden++;
    if (request.url === '/allowed') allowed++;
    response.end('fixture');
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = 'http://127.0.0.1:' + server.address().port;
let bootstrap, ordering, exited = false, stopped, stderrBytes = 0;
const child = spawn('/opt/chrome-linux64/chrome', [
  '--headless=new', '--no-startup-window', '--remote-debugging-pipe',
  '--disable-background-networking', '--disable-extensions',
  '--disable-component-extensions-with-background-pages', '--disable-component-update',
  '--disable-default-apps', '--disable-popup-blocking', '--no-first-run', '--no-default-browser-check',
], {detached: true, env: {PATH: '/usr/bin:/bin', HOME: '/home/fixture'},
  stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe']});
const exit = once(child, 'exit').then(() => {exited = true;});
function stopOwned() {
  if (!stopped) stopped = (async () => {
    if (!exited) {
      process.kill(-child.pid, 'SIGTERM');
      let timer;
      await Promise.race([exit, new Promise(resolve => {timer = setTimeout(resolve, 5000);})]);
      clearTimeout(timer);
      if (!exited) {process.kill(-child.pid, 'SIGKILL'); await exit;}
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
    counts[event.method] = (counts[event.method] || 0) + 1;
    if (event.method.startsWith('Target.')) record({event: event.method,
      type: event.params.targetInfo?.type, waiting: event.params.waitingForDebugger});
    if (!event.sessionId && ['Target.targetCreated', 'Target.attachedToTarget'].includes(event.method)) {
      // Deliberately unsafe popup negative control, restricted to invented fixture.
      if (mode === 'popup-negative' && bootstrap.ready()) {
        if (event.method === 'Target.attachedToTarget') {
          pipe.registerSession(event.params.sessionId);
          void pipe.send('Runtime.runIfWaitingForDebugger', {}, event.params.sessionId).catch(() => {});
        }
      } else bootstrap.event(event);
    }
    if (event.method === 'Fetch.requestPaused') {
      const request = event.params.request;
      record({pause: new URL(request.url).pathname, method: request.method});
      const navigation = [origin + '/root', origin + '/favicon.ico'].includes(request.url) && request.method === 'GET';
      const permitted = request.url === origin + '/allowed' && request.method === 'POST' && !consumed;
      if (permitted) consumed = true;
      if (navigation || permitted) {
        void pipe.send('Fetch.continueRequest', {requestId: event.params.requestId}, event.sessionId).catch(() => {});
      } else void ordering.abort().catch(() => {});
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
ordering = orderingExperiment({
  send: (method, params, session) => negative && method === 'Fetch.enable'
    ? Promise.resolve({}) : pipe.send(method, params, session),
  installRoutes: () => {}, stopOwned,
  closePipe: () => {child.stdio[3].destroy(); child.stdio[4].destroy();},
});
bootstrap = bootstrapExperiment({send: pipe.send, registerSession: pipe.registerSession,
  initialize: ordering.initialize, stop: ordering.abort});
pipe.armEvents();
let failure;
try {
  const owner = await bootstrap.start();
  try {await pipe.send('Page.navigate', {url: origin + '/root'}, owner.sessionId);} catch { /* Rejection may stop navigation. */ }
  // Bounded observation is a fixture measurement, never uncertain-write resolution.
  await new Promise(resolve => setTimeout(resolve, 1000));
} catch {
  failure = 'FIXTURE_STARTUP_FAILED';
} finally {
  await ordering.abort();
  await new Promise(resolve => server.close(resolve));
}
const passed = !failure && (negative ? forbidden === 1 && allowed === 0
  : mode === 'permitted' ? allowed === 1 && forbidden === 0 : forbidden === 0 && allowed === 0);
console.log(JSON.stringify({mode, node: process.version, passed, failure, allowed, forbidden,
  owned_browser_exit: exited, counts, trace, browser_proven: false}));
if (!passed) process.exitCode = 1;
