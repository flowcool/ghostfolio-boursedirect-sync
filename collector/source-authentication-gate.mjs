// Bounded qualification only: native inspection, private retention, durable permit.
// The caller separately proves source bytes, response outcomes and browser ownership.
import {authorityForPolicy, principal} from './core.mjs';
import {controllerForPolicy} from './request-controller.mjs';
import {inspectSourceRequestForPolicy} from './source-request-inspection.mjs';
import {BROKER_POLICY, requirePolicy} from './internal/source-policy.mjs';

const PHASES = Object.freeze({
  password_uncertain: ['password_submit', 'password', '/hub/auth/login'],
  otp_uncertain: ['otp_submit', 'otp', '/hub/auth/two-factor/validate-totp'],
  finalization_uncertain: ['password_finalize', 'finalize', '/hub/auth/login-2fa'],
});

function createGate(policy, authority, {handle, binding, source, now, retain, continueRequest, cancelAuth, stop}) {
  requirePolicy(policy); authority.assertHandle(handle); authority.validateSourceContract(source);
  if (source.schema_version !== 2 || [now, retain, continueRequest, cancelAuth, stop].some(value => typeof value !== 'function'))
    throw new Error('SOURCE_AUTHENTICATION_GATE_REFUSED');
  const contract = structuredClone(source), owner = structuredClone(binding);
  let fenced = false, stopping;
  const phases = new Set();
  function bounded(callback) {
    let timer;
    return Promise.race([Promise.resolve().then(callback), new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error()), 45000);
    })]).finally(() => clearTimeout(timer));
  }
  function abort() {
    fenced = true;
    stopping ??= bounded(stop).then(value => {
      if (value !== true) throw new Error('SOURCE_AUTHENTICATION_STOP_UNVERIFIED');
      return true;
    }, () => {throw new Error('SOURCE_AUTHENTICATION_STOP_UNVERIFIED');});
    void stopping.catch(() => {}); return stopping;
  }
  function check() {if (fenced) throw new Error(); authority.assertHandle(handle);}
  const authController = controllerForPolicy(policy, {binding: owner, source: contract, now,
    consume: (request, time) => {check(); return authority.consumePermit(handle, request, time);},
    continueRequest: id => {check(); return continueRequest(id);}, cancelAuth, stop: abort});
  function authRequired(value) {
    fenced = true;
    return authController.authRequired(value);
  }
  async function paused(input) {
    try {
      check();
      const {phase, candidate, event, expected, otp} = structuredClone(input);
      const selected = PHASES[phase];
      if (!selected || phases.has(phase)) throw new Error();
      // Reserve before a private fsync callback can await. Duplicates fence both.
      phases.add(phase);
      if (candidate.role !== selected[0] || candidate.url !== policy.origin + selected[2]
          || candidate.method !== 'POST' || candidate.resourceType !== 'XHR'
          || (phase === 'otp_uncertain') !== (otp !== undefined)) throw new Error();
      if (phase !== 'otp_uncertain' && (policy === BROKER_POLICY
        ? principal(expected.login) !== handle.principal : expected.login !== 'SYNTHETIC')) throw new Error();
      if (event.sessionId !== owner.sessionId || !Object.hasOwn(owner.frames, event.frameId)) throw new Error();
      const observation = inspectSourceRequestForPolicy(policy, {owner: {sessionId: owner.sessionId, frameId: event.frameId},
        candidate, event, expected});
      if (await bounded(() => retain(observation)) !== true) throw new Error();
      check();
      const qualified = structuredClone(contract);
      qualified.roles[selected[1]] = {url: candidate.url, method: 'POST', resource_type: 'XHR',
        evidence: 'native-envelope:' + candidate.sourceSha256 + ':' + event.requestId};
      const frameEpoch = owner.frames[event.frameId].epoch;
      const permit = {phase, page_epoch: owner.pageEpoch, frame_epoch: frameEpoch,
        url: candidate.url, method: 'POST', resource_type: 'XHR'};
      const nonce = authority.armPermit(handle, permit, now(), qualified);
      const controller = controllerForPolicy(policy, {binding: owner, source: qualified, now,
        consume: (request, time) => {check(); return authority.consumePermit(handle, request, time);},
        continueRequest: id => {check(); return continueRequest(id);}, cancelAuth, stop: abort});
      controller.arm({phase, nonce, pageEpoch: owner.pageEpoch, frameEpoch, frameId: event.frameId,
        url: candidate.url, method: 'POST', resourceType: 'XHR', ...(otp === undefined ? {} : {otp})});
      const result = await controller.paused({requestId: event.requestId, sessionId: event.sessionId,
        frameId: event.frameId, pageEpoch: owner.pageEpoch, frameEpoch, resourceType: event.resourceType,
        request: {url: event.request.url, method: event.request.method}});
      check(); return result;
    } catch {
      await abort(); throw new Error('SOURCE_AUTHENTICATION_GATE_REFUSED');
    }
  }
  return Object.freeze({paused, authRequired, abort, status: () => ({fenced, reserved_phases: phases.size, online_ready: false})});
}

// Cooperating authorities are bound once; no authority or policy arrives in a
// request or operator command. This preserves the core's WeakMap handle ownership.
export function sourceAuthenticationComposition(policy) {
  requirePolicy(policy);
  const authority = authorityForPolicy(policy);
  return Object.freeze({...authority, gate: options => createGate(policy, authority, options)});
}

export function brokerAuthenticationComposition() {return sourceAuthenticationComposition(BROKER_POLICY);}
