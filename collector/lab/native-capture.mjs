// Native ticket evaluator; synthetic marker adapter only, no financial parsing.
import {syntheticPolicy, policyUrl} from '../internal/source-policy.mjs';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const MAX_BYTES = 1048576;
function identifier(value) {return typeof value === 'string' && value.length > 0 && value.length <= 256;}

export function nativeCapture({binding, url, account, day, role, active, serialize, timeoutMs = 5000}) {
  const owner = structuredClone(binding);
  try {policyUrl(syntheticPolicy(new URL(url).origin, owner?.pageEpoch), url);}
  catch {throw new Error('NATIVE_CAPTURE_CONFIG_INVALID');}
  if (!owner || !['targetId', 'sessionId', 'frameId'].every(k => identifier(owner[k]))
      || !['pageEpoch', 'frameEpoch'].every(k => UUID.test(owner[k] ?? ''))
      || !identifier(account) || !identifier(role) || !/^\d{4}-\d{2}-\d{2}$/.test(day ?? '')
      || !/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}\//.test(url ?? '')
      || [active, serialize].some(f => typeof f !== 'function')
      || !Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 5000) {
    throw new Error('NATIVE_CAPTURE_CONFIG_INVALID');
  }
  let stage = 'empty', network, pause, reply, committed = false, loaded = false;
  function reject() {stage = 'failed'; throw new Error('NATIVE_CAPTURE_REJECTED');}
  function check() {if (stage === 'failed' || stage === 'captured') reject();}
  function arm() {if (stage !== 'empty') reject(); stage = 'armed';}
  function navigation(value) {
    check();
    if (stage !== 'armed' || reply || value?.frameId !== owner.frameId || !identifier(value.loaderId)
        || value.errorText || (network && value.loaderId !== network.loaderId)) reject();
    reply = structuredClone(value);
  }
  function event(value) {
    check();
    if (stage !== 'armed' || value?.sessionId !== owner.sessionId) reject();
    const params = value.params;
    if (value.method === 'Network.requestWillBeSent') {
      if (network || params?.frameId !== owner.frameId || params.type !== 'Document'
          || params.request?.url !== url || params.request?.method !== 'GET'
          || Object.hasOwn(params, 'redirectResponse') || !identifier(params.requestId)
          || !identifier(params.loaderId) || (reply && params.loaderId !== reply.loaderId)) reject();
      // Retain selected native metadata only, never headers or postData.
      network = {requestId: params.requestId, loaderId: params.loaderId};
    } else if (value.method === 'Fetch.requestPaused') {
      if (pause || params?.frameId !== owner.frameId || params.resourceType !== 'Document'
          || params.request?.url !== url || params.request?.method !== 'GET'
          || Object.hasOwn(params, 'redirectedRequestId') || !identifier(params.requestId)
          || !identifier(params.networkId) || Object.hasOwn(params, 'responseStatusCode')) reject();
      pause = {requestId: params.requestId, networkId: params.networkId};
    } else if (value.method === 'Page.frameNavigated') {
      if (committed || !network || !pause || pause.networkId !== network.requestId
          || params?.frame?.id !== owner.frameId || params.frame.url !== url
          || params.frame.loaderId !== network.loaderId) reject();
      committed = true;
    } else if (value.method === 'Page.lifecycleEvent') {
      if (loaded || !committed || params?.name !== 'load' || params.frameId !== owner.frameId
          || params.loaderId !== network.loaderId) reject();
      loaded = true;
    } else reject();
    if (network && pause && network.requestId !== pause.networkId) reject();
  }
  async function bounded(callback) {
    let timer;
    const deadline = new Promise((_, fail) => {timer = setTimeout(() => fail(new Error('NATIVE_CAPTURE_REJECTED')), timeoutMs);});
    try {return await Promise.race([Promise.resolve().then(callback), deadline]);}
    finally {clearTimeout(timer);}
  }
  function current(value) {
    return value && ['targetId', 'sessionId', 'frameId', 'pageEpoch', 'frameEpoch'].every(k => value[k] === owner[k])
      && value.url === url && value.loaderId === network.loaderId;
  }
  async function capture() {
    try {
      check();
      if (stage !== 'armed' || !network || !pause || !reply || !committed || !loaded
          || reply.loaderId !== network.loaderId) reject();
      stage = 'serializing';
      if (!current(await bounded(active)) || stage !== 'serializing') reject();
      const raw = await bounded(serialize);
      if (stage !== 'serializing' || typeof raw !== 'string' || Buffer.byteLength(raw) > MAX_BYTES) reject();
      if (!current(await bounded(active)) || stage !== 'serializing') reject();
      const markers = JSON.parse(raw);
      if (!markers || Object.keys(markers).sort().join(',') !== 'account,body,day,operation,role'
          || markers.account !== account || markers.day !== day || markers.role !== role
          || markers.operation !== 'known' || typeof markers.body !== 'string') reject();
      stage = 'captured';
      return {body: markers.body, requestId: network.requestId, fetchRequestId: pause.requestId,
        loaderId: network.loaderId, ...owner, online_ready: false, browser_proven: false, import_ready: false};
    } catch {reject();}
  }
  return {arm, navigation, event, capture,
    ready: () => stage === 'armed' && !!reply && committed && loaded};
}
