// Private native CDP composition, separate from the ordinary collector.
// The caller supplies a pinned owned pipe and exact policy decisions, never IDs rewritten.
import {capabilityPipe, PIPE_LIMITS} from './capability-pipe.mjs';
import {bootstrapExperiment} from './capability-bootstrap.mjs';
import {orderingExperiment} from './capability-ordering.mjs';
import {randomUUID} from 'node:crypto';

export async function sourceNativeSession({write, stopOwned, closePipe, installReceive,
  paused, response, publicPreflight = () => false, chromeVersion = '155.0.8059.39'}) {
  if ([write, stopOwned, closePipe, installReceive, paused, response, publicPreflight].some(value => typeof value !== 'function')
      || chromeVersion !== '155.0.8059.39') throw new Error('SOURCE_NATIVE_SESSION_REFUSED');
  let fenced = false, ordering, pipe, bootstrap, owner, frameId, contextId;
  const pageEpoch = randomUUID(), frameEpoch = randomUUID(), tasks = new Set();
  const quarantinedFrames = new Set();
  let requests = 0, bytes = 0, failure;
  function abort() {fenced = true; return ordering ? ordering.abort() : stopOwned();}
  function check() {if (fenced) throw new Error('SOURCE_NATIVE_SESSION_FENCED');}
  function track(promise) {
    tasks.add(promise);
    void promise.catch(error => {failure ??= {code:/^[A-Z_]+$/.test(error?.message??'')?error.message:'SOURCE_NATIVE_HANDLER_REFUSED'};return abort();}).catch(() => {}).finally(() => tasks.delete(promise));
  }
  function send(method, params = {}, sessionId) {check(); return pipe.send(method, params, sessionId);}
  function binding() {
    check();
    if (!owner || !frameId) throw new Error('SOURCE_NATIVE_OWNER_MISSING');
    return {targetId: owner.targetId, sessionId: owner.sessionId, pageEpoch,
      frames: {[frameId]: {epoch: frameEpoch, role: 'source'}}};
  }
  function ownedEvent(event) {
    if (event.sessionId !== owner?.sessionId || event.params.frameId !== frameId
        || Object.hasOwn(event.params, 'redirectedRequestId')) throw new Error('SOURCE_NATIVE_EVENT_REFUSED');
  }
  pipe = capabilityPipe({write, limits: {...PIPE_LIMITS, sessionMs: 600000},
    fence: code => {failure ??= {code};void abort().catch(() => {});}, onEvent: event => {
      if (fenced) return;
      const diagnostic={event:event.method,resource_type:event.params.resourceType??null,
        response_status:event.params.responseStatusCode??null,response_error:event.params.responseErrorReason??null};
      try {
      if (['Target.targetCreated', 'Target.attachedToTarget'].includes(event.method)) {bootstrap.event(event); return;}
      if (event.method === 'Fetch.authRequired') {
        if (event.sessionId !== owner?.sessionId) throw new Error();
        track(ordering.cancelHttpAuth(event.sessionId, event.params.requestId)); return;
      }
      if (event.method === 'Network.requestWillBeSent' && event.params.redirectResponse) throw new Error();
      if (event.method === 'Page.frameAttached') {
        const p=event.params;
        if (publicPreflight()!==true || event.sessionId!==owner?.sessionId
            || typeof p.frameId!=='string' || !p.frameId || p.frameId.length>256
            || p.frameId===frameId || quarantinedFrames.has(p.frameId) || quarantinedFrames.size>=32
            || !(p.parentFrameId===frameId || quarantinedFrames.has(p.parentFrameId))) throw new Error();
        quarantinedFrames.add(p.frameId);return;
      }
      if (event.method === 'Page.frameNavigated') {
        if (quarantinedFrames.has(event.params.frame?.id)) {
          if (publicPreflight()!==true || event.sessionId!==owner?.sessionId
              || !['about:blank','chrome-error://chromewebdata/'].includes(event.params.frame.url)) throw new Error();
          return;
        }
        if (event.sessionId !== owner?.sessionId || event.params.frame?.id !== frameId
            || event.params.frame.parentId) throw new Error();
        contextId = undefined;
      }
      if (event.method === 'Runtime.executionContextsCleared') contextId = undefined;
      if (event.method === 'Runtime.executionContextDestroyed' && event.params.executionContextId === contextId?.id) contextId = undefined;
      if (event.method === 'Runtime.executionContextCreated') {
        const context = event.params.context;
        if (quarantinedFrames.has(context.auxData?.frameId)) {
          if (publicPreflight()!==true || event.sessionId!==owner?.sessionId) throw new Error();
          return; // Never expose a child realm through evaluate or binding.
        }
        if (event.sessionId !== owner?.sessionId || context.auxData?.frameId !== frameId) throw new Error();
        if (context.auxData?.isDefault === true) {
          if (contextId !== undefined || !Number.isSafeInteger(context.id)
              || typeof context.uniqueId !== 'string' || !context.uniqueId) throw new Error();
          contextId = {id: context.id, unique: context.uniqueId};
        }
      }
      if (event.method === 'Fetch.requestPaused') {
        const p = event.params;
        if (++requests > 512 || (bytes += Buffer.byteLength(JSON.stringify(p))) > 2097152) throw new Error();
        if (quarantinedFrames.has(p.frameId)) {
          if (publicPreflight()!==true || event.sessionId!==owner?.sessionId || p.request.method!=='GET'
              || Object.hasOwn(p,'redirectedRequestId') || Object.hasOwn(p,'responseStatusCode')
              || Object.hasOwn(p,'responseErrorReason')) throw new Error();
          track(send('Fetch.failRequest',{requestId:p.requestId,errorReason:'BlockedByClient'},event.sessionId));return;
        }
        ownedEvent(event);
        if (Object.hasOwn(p, 'responseStatusCode')) {
          if (p.responseStatusCode >= 300 && p.responseStatusCode < 400 || p.responseErrorReason) throw new Error();
          track(response({event, binding: binding(), send}));
        } else track(paused({event, binding: binding(), send}));
      }
      } catch(error) {failure={...diagnostic,code:/^[A-Z_]+$/.test(error?.message??'')?error.message:'SOURCE_NATIVE_EVENT_REFUSED'};throw error;}
    }});
  installReceive({receive: pipe.receive, lost: () => {pipe.lost(); void abort().catch(() => {});}});
  ordering = orderingExperiment({send, installRoutes: () => {}, stopOwned,
    closePipe, beforeResume: async sessionId => {
      const frame = (await send('Page.getFrameTree', {}, sessionId)).frameTree;
      if (!frame || !['', 'about:blank'].includes(frame.frame.url) || frame.childFrames?.length) throw new Error();
      frameId = frame.frame.id;
      owner.sessionId = sessionId;
      // Response interception lets the caller durably advance known protocol
      // outcomes before the frontend can immediately issue its next native step.
      await send('Fetch.enable', {patterns: [{urlPattern: '*', requestStage: 'Request'},
        {urlPattern: '*', requestStage: 'Response'}], handleAuthRequests: true}, sessionId);
      await send('Runtime.enable', {}, sessionId);
    }});
  bootstrap = bootstrapExperiment({send, registerSession: pipe.registerSession,
    initialize: (sessionId, waiting, targetId) => {
      owner = {targetId, sessionId}; return ordering.initialize(sessionId, waiting);
    }, stop: abort, product: 'HeadlessChrome', expectedVersion: chromeVersion});
  try {
    pipe.armEvents(); owner = await bootstrap.start();
    return Object.freeze({binding, browserProcesses: () => send('SystemInfo.getProcessInfo'), send: (method, params = {}) => send(method, params, owner.sessionId),
      evaluate: async (fn, args = []) => {
        check();
        if (typeof fn !== 'function' || !Array.isArray(args)) throw new Error('SOURCE_NATIVE_REALM_MISSING');
        const expression = '(' + fn.toString() + ')(...' + JSON.stringify(structuredClone(args)) + ')';
        const deadline = Date.now() + 10000;
        while (contextId === undefined) {
          check(); if (Date.now() > deadline) throw new Error('SOURCE_NATIVE_REALM_MISSING');
          await new Promise(resolve => setTimeout(resolve, 50));
        }
        const result = await send('Runtime.evaluate', {expression,
          uniqueContextId: contextId.unique, returnByValue: true, awaitPromise: false}, owner.sessionId);
        check(); if (result.exceptionDetails) throw new Error('SOURCE_NATIVE_DOM_REFUSED');
        return result.result?.value;
      }, disableScripts: () => send('Emulation.setScriptExecutionDisabled', {value: true}, owner.sessionId),
      stop: async () => {await abort(); return true;},
      close: async () => {await abort(); await Promise.allSettled([...tasks]); return true;},
      failure: () => structuredClone(failure), fenced: () => fenced});
  } catch (error) {await abort(); throw new Error(/^(CAPABILITY|SOURCE_NATIVE)_[A-Z_]+$/.test(error?.message ?? '') ? error.message : 'SOURCE_NATIVE_SESSION_REFUSED');}
}
