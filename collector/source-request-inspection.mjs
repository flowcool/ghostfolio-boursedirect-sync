// Native paused-request inspection only. No dispatch, credential export or role activation.
import {parseDocument} from 'yaml';
import {brokerUrl} from './core.mjs';

const HASH = /^[a-f0-9]{64}$/;
const POST_KEYS = Object.freeze({
  preliminary_verify: ['branding'],
  password_submit: ['username', 'password', 'branding', 'redirect'],
  otp_submit: ['code', 'branding', 'trusted_device'],
  password_finalize: ['username', 'password', 'branding', 'redirect'],
});
const GET_ROLES = new Set(['app_method', 'frame_document', 'monthly_statement', 'contract_note']);
function exact(value, keys) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || Object.keys(value).length !== keys.length || keys.some(key => !Object.hasOwn(value, key))) throw new Error();
}
function text(value) {
  if (typeof value !== 'string' || !value || Buffer.byteLength(value) > 4096
      || /[\x00-\x1f\x7f]/.test(value)) throw new Error();
}
function identifier(value) {
  if (typeof value !== 'string' || !value || value.length > 256) throw new Error();
}

export function inspectSourceRequest({owner, candidate, event, expected}) {
  try {
    exact(owner, ['sessionId', 'frameId']); Object.values(owner).forEach(identifier);
    exact(candidate, ['role', 'url', 'method', 'resourceType', 'sourceSha256']);
    brokerUrl(candidate.url);
    if (!HASH.test(candidate.sourceSha256)) throw new Error();
    const fields = POST_KEYS[candidate.role];
    if (!fields && !GET_ROLES.has(candidate.role)) throw new Error();
    if (candidate.method !== (fields ? 'POST' : 'GET')
        || candidate.resourceType !== (fields || candidate.role === 'app_method' ? 'XHR' : 'Document')) throw new Error();
    // The runtime supplies native metadata without translating URLs or CDP IDs.
    exact(event, ['requestId', 'sessionId', 'frameId', 'resourceType', 'request']);
    identifier(event.requestId);
    if (event.sessionId !== owner.sessionId || event.frameId !== owner.frameId
        || event.resourceType !== candidate.resourceType) throw new Error();
    exact(event.request, fields ? ['url', 'method', 'headers', 'postData'] : ['url', 'method']);
    if (event.request.url !== candidate.url || event.request.method !== candidate.method) throw new Error();
    const observation = {role: candidate.role, url: candidate.url, method: candidate.method,
      resource_type: candidate.resourceType, source_sha256: candidate.sourceSha256,
      request_id: event.requestId, session_id: event.sessionId, frame_id: event.frameId,
      payload_keys: Object.freeze([]), content_type: null, dispatch_authority: false, online_ready: false};
    if (!fields) {exact(expected, []); return Object.freeze(observation);}
    if (!event.request.headers || typeof event.request.headers !== 'object'
        || Array.isArray(event.request.headers)) throw new Error();
    const types = Object.entries(event.request.headers).filter(([key]) => key.toLowerCase() === 'content-type');
    if (types.length !== 1 || types[0][1] !== 'application/json'
        || typeof event.request.postData !== 'string' || Buffer.byteLength(event.request.postData) > 8192) throw new Error();
    const document = parseDocument(event.request.postData, {uniqueKeys: true});
    if (document.errors.length || document.warnings.length) throw new Error();
    const body = JSON.parse(event.request.postData);
    exact(body, fields);
    if (candidate.role === 'preliminary_verify') {
      exact(expected, ['branding']); text(expected.branding);
      if (body.branding !== expected.branding) throw new Error();
    } else if (candidate.role === 'otp_submit') {
      exact(expected, ['code', 'branding']); text(expected.branding);
      if (typeof expected.code !== 'string' || !/^[0-9]{6}$/.test(expected.code) || body.code !== expected.code
          || body.branding !== expected.branding || body.trusted_device !== false) throw new Error();
    } else {
      exact(expected, ['login', 'password', 'branding']); Object.values(expected).forEach(text);
      if (body.username !== expected.login.trim() || body.password !== expected.password
          || body.branding !== expected.branding || body.redirect !== null) throw new Error();
    }
    // Never return a credential body, a secret-derived hash or any native header.
    observation.payload_keys = Object.freeze([...fields]);
    observation.content_type = 'application/json';
    return Object.freeze(observation);
  } catch {throw new Error('SOURCE_REQUEST_ENVELOPE_REFUSED');}
}
