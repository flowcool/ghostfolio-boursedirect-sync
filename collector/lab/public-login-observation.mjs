// Opt-in single public GET. Stdout is a PRIVATE evidence envelope, never a log.
// Infra must attest the exact owned runtime and proxy-only namespace before exec.
import fs from 'node:fs';
import {spawn} from 'node:child_process';
import {capabilityPipe, PIPE_LIMITS} from '../capability-pipe.mjs';
import {bootstrapExperiment} from '../capability-bootstrap.mjs';
import {orderingExperiment} from '../capability-ordering.mjs';
import {ownedBrowserLifecycle, sandboxStatus} from './browser-sandbox-proof.mjs';
import {PUBLIC_LOGIN_URL, publicLoginPolicy, publicAssetDocumentPolicy} from '../public-login-policy.mjs';

let stage = 'input', pipe, lifecycle, ordering, timer;
let retained;
let requests = 0, permitted = 0, blocked = 0, failed = false;
async function run() {
  if (process.getuid() !== 1000 || Object.keys(process.env).some(key => !['PATH', 'HOME'].includes(key)))
    throw new Error('PUBLIC_OBSERVATION_RUNTIME_REFUSED');
  const input = await new Promise((resolve, reject) => {
    let raw = '';
    timer = setTimeout(() => reject(new Error()), 10000);
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', value => {raw += value; if (raw.length > 131072) reject(new Error());});
    process.stdin.on('end', () => {clearTimeout(timer); try {resolve(JSON.parse(raw));} catch {reject(new Error());}});
    process.stdin.on('error', reject);
  });
  const assetsMode = input && Object.hasOwn(input, 'observed_assets');
  const assetDocuments = input && Object.hasOwn(input, 'asset_documents');
  if (!input || (assetDocuments && (!assetsMode || input.asset_documents !== true))
      || Object.keys(input).length !== (assetDocuments ? 5 : assetsMode ? 4 : 2)
      || (assetsMode && (!/^[a-f0-9]{64}$/.test(input.reference_evidence_sha256) || !Array.isArray(input.observed_assets) || !input.observed_assets.length)) || !/^[a-f0-9]{64}$/.test(input.routing_receipt_sha256)
      || typeof input.proxy !== 'string' || !/^http:\/\/(?:\d{1,3}\.){3}\d{1,3}:8080$/.test(input.proxy)
      || new URL(input.proxy).origin !== input.proxy
      || new URL(input.proxy).hostname.split('.').some(value => Number(value) > 255)) throw new Error();
  publicLoginPolicy({sessionId: 'validate', frameId: 'validate'}, input.observed_assets ?? []);
  if (assetDocuments) publicAssetDocumentPolicy({sessionId: 'validate', frameId: 'validate'}, input.observed_assets);
  stage = 'chrome_launch';
  const profile = fs.mkdtempSync('/home/fixture/public-observation-');
  const child = spawn('/opt/chrome-headless-shell-linux64/chrome-headless-shell', [
    '--no-startup-window', '--remote-debugging-pipe', '--user-data-dir=' + profile,
    '--proxy-server=' + input.proxy, '--proxy-bypass-list=<-loopback>',
    '--disable-background-networking', '--disable-extensions', '--disable-component-extensions-with-background-pages',
    '--disable-component-update', '--disable-default-apps', '--no-first-run', '--no-default-browser-check'],
  {detached: true, env: {PATH: '/usr/bin:/bin', HOME: '/home/fixture'},
    stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe']});
  lifecycle = ownedBrowserLifecycle(child);
  const evidence = {schema_version: 1, kind: assetDocuments ? 'inert_public_asset_documents' : 'single_public_document_observation',
    routing_receipt_sha256: input.routing_receipt_sha256, chrome_version: '155.0.8059.39',
    authentication_requests: 0, credentials_read: false, scripts_disabled: !assetsMode || assetDocuments,
    reference_evidence_sha256: input.reference_evidence_sha256 ?? null,
    requests: [], responses: [], targets: [], online_ready: false};
  retained = evidence;
  let loaded = false;
  let expectedDocument = PUBLIC_LOGIN_URL;
  let decide, owner, frameId, primaryId, queue = Promise.resolve(), bytes = 0;
  const tasks = new Set();
  function fatal() {failed = true; return ordering ? ordering.abort() : lifecycle.stop();}
  function track(promise) {
    tasks.add(promise);
    void promise.catch(() => fatal()).catch(() => {}).finally(() => tasks.delete(promise));
  }
  function record(list, row) {
    if (list.length >= 256 || (bytes += Buffer.byteLength(JSON.stringify(row))) > 262144) throw new Error();
    list.push(row);
  }
  try {
    lifecycle.pin();
    let stderrBytes = 0;
    child.stderr.on('data', value => {stderrBytes += value.length; if (stderrBytes > 32768) track(fatal());});
    child.on('error', () => track(fatal()));
    pipe = capabilityPipe({limits: {...PIPE_LIMITS, commandMs: 10000, sessionMs: 60000},
      write: raw => new Promise((resolve, reject) => child.stdio[3].write(raw, error => error ? reject(error) : resolve())),
      fence: () => {void fatal().catch(() => {});}, onEvent: event => {
        if (failed) return;
        if (['Target.targetCreated', 'Target.attachedToTarget'].includes(event.method)) {
          const info = event.params.targetInfo;
          if (info && typeof info.url === 'string' && info.url.length <= 4096)
            record(evidence.targets, {type: info.type, url: info.url});
          bootstrap.event(event);
        }
        if (event.method === 'Fetch.authRequired') {
          track(ordering.cancelHttpAuth(event.sessionId, event.params.requestId)); return;
        }
        if (event.method === 'Fetch.requestPaused') {
          const p = event.params;
          if (!decide || ++requests > 256 || typeof p.request?.url !== 'string' || p.request.url.length > 4096) throw new Error();
          const allowed = decide({...p, sessionId: event.sessionId});
          if (allowed) permitted++; else blocked++;
          record(evidence.requests, {url: p.request.url, method: p.request.method,
            resource_type: p.resourceType, request_id: p.requestId, network_id: p.networkId,
            frame_id: p.frameId, session_id: event.sessionId, continued: allowed,
            redirect: Object.hasOwn(p, 'redirectedRequestId')});
          queue = queue.then(() => {
            if (failed) throw new Error();
            return pipe.send(allowed ? 'Fetch.continueRequest' : 'Fetch.failRequest',
              allowed ? {requestId: p.requestId} : {requestId: p.requestId, errorReason: 'BlockedByClient'}, event.sessionId);
          });
          track(queue);
        }
        if (event.method === 'Network.responseReceived' && event.sessionId === owner?.sessionId) {
          const p = event.params;
          if (p.type === 'Document' && p.response.url === expectedDocument) primaryId = p.requestId;
          record(evidence.responses, {request_id: p.requestId, url: p.response.url,
            status: p.response.status, resource_type: p.type, mime_type: p.response.mimeType});
        }
        if (event.method === 'Network.loadingFinished' && event.params.requestId === primaryId) loaded = true;
        if (event.method === 'Network.requestWillBeSent' && event.params.redirectResponse) {
          record(evidence.responses, {url: event.params.redirectResponse.url,
            status: event.params.redirectResponse.status, redirect_to: event.params.request.url});
        }
      }});
    child.stdio[4].on('data', value => {try {pipe.receive(value);} catch {void fatal().catch(() => {});}});
    child.stdio[4].on('end', () => {if (!lifecycle.exited()) void fatal().catch(() => {});});
    ordering = orderingExperiment({send: pipe.send, installRoutes: () => {}, stopOwned: lifecycle.stop,
      closePipe: () => {child.stdio[3].destroy(); child.stdio[4].destroy();}, beforeResume: async session => {
        await pipe.send('Emulation.setScriptExecutionDisabled', {value: !assetsMode || assetDocuments}, session);
        frameId = (await pipe.send('Page.getFrameTree', {}, session)).frameTree.frame.id;
        decide = assetDocuments ? publicAssetDocumentPolicy({sessionId: session, frameId}, input.observed_assets)
          : publicLoginPolicy({sessionId: session, frameId}, input.observed_assets ?? []);
      }});
    const bootstrap = bootstrapExperiment({send: pipe.send, registerSession: pipe.registerSession,
      initialize: ordering.initialize, stop: fatal, product: 'HeadlessChrome', expectedVersion: '155.0.8059.39'});
    pipe.armEvents();
    stage = 'guarded_bootstrap';
    owner = await bootstrap.start();
    stage = 'renderer_sandbox';
    const inventory = await pipe.send('SystemInfo.getProcessInfo');
    const owned = lifecycle.observe(), baseline = fs.readFileSync('/proc/self/status', 'utf8');
    if (!Array.isArray(inventory.processInfo) || inventory.processInfo.length > 256) throw new Error();
    const renderers = inventory.processInfo.filter(row => row.type === 'renderer');
    if (!renderers.length) throw new Error();
    evidence.renderer_sandbox = renderers.map(row => {
      const pin = owned.get(row.id);
      if (!pin) throw new Error();
      const raw = fs.readFileSync('/proc/' + row.id + '/status', 'utf8');
      if (lifecycle.observe().get(row.id)?.start !== pin.start) throw new Error();
      return sandboxStatus(raw, baseline);
    });
    if (assetDocuments) evidence.asset_documents = [];
    for (const url of assetDocuments ? input.observed_assets.map(row => row.url) : [PUBLIC_LOGIN_URL]) {
      expectedDocument = url; primaryId = null; loaded = false;
      stage = 'single_document_navigation';
      const navigation = await pipe.send('Page.navigate', {url}, owner.sessionId);
      if (navigation.errorText) throw new Error();
      const deadline = Date.now() + 15000;
      while (!primaryId || !loaded) {
        if (failed || Date.now() > deadline) throw new Error();
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      stage = 'document_capture';
      // Wait for loadingFinished before getResponseBody, without retrying a broker request.
      const body = await pipe.send('Network.getResponseBody', {requestId: primaryId}, owner.sessionId);
      if (typeof body.body !== 'string' || Buffer.byteLength(body.body) > 1048576) throw new Error();
      const captured = {url, request_id: primaryId, body: body.body, base64_encoded: body.base64Encoded === true};
      if (assetDocuments) {
        if (Buffer.byteLength(JSON.stringify([...evidence.asset_documents, captured])) > 1048576) throw new Error();
        evidence.asset_documents.push(captured);
      } else evidence.document = captured;
    }
    if (assetsMode && !assetDocuments) {
      stage = 'bounded_public_dom';
      await new Promise(resolve => setTimeout(resolve, 5000));
      if (failed) throw new Error();
      const document = await pipe.send('DOM.getDocument', {depth: 0}, owner.sessionId);
      const outer = await pipe.send('DOM.getOuterHTML', {nodeId: document.root.nodeId}, owner.sessionId);
      if (typeof outer.outerHTML !== 'string' || Buffer.byteLength(outer.outerHTML) > 262144) throw new Error();
      evidence.rendered_dom = {representation: 'CDP DOM serialization UTF8, not original response bytes', html: outer.outerHTML};
    }
    await queue;
    if (failed || (!assetsMode && permitted !== 1) || permitted < 1) throw new Error();
    evidence.counts = {requests, permitted, blocked};
    evidence.owned_browser_exit_verified = await lifecycle.stop();
    return evidence;
  } finally {
    const failedStage = stage;
    stage = 'owned_cleanup';
    await lifecycle.stop();
    pipe?.lost();
    await Promise.allSettled([...tasks]);
    stage = failedStage;
  }
}
try {console.log(JSON.stringify(await run()));}
catch {clearTimeout(timer); if (retained) console.log(JSON.stringify({complete: false, evidence: retained})); console.error(JSON.stringify({code: 'PUBLIC_DOCUMENT_OBSERVATION_FAILED', stage,
  requests, permitted, blocked, credentials_read: false})); process.exitCode = 1;}
