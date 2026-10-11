// One-use source reads. Every grant is retained and consumed before continuation.
import {inspectSourceRequestForPolicy} from './source-request-inspection.mjs';
import {requirePolicy, policyUrl} from './internal/source-policy.mjs';
const HASH = /^[a-f0-9]{64}$/;
const FIXED = Object.freeze({
  preliminary_verify: ['/hub/auth/verify', 'POST'],
  two_factor_systems: ['/hub/auth/two-factor/login/active-systems/boursedirect', 'GET'],
  two_factor_state: ['/hub/auth/two-factor/login/state/boursedirect', 'GET'],
  branding_config: ['/hub/referential/branding/boursedirect', 'GET'],
});
export function sourceReadGate(policy, {binding, retain, consume, continueRequest, stop}) {
  requirePolicy(policy);
  if ([retain, consume, continueRequest, stop].some(value => typeof value !== 'function')) throw new Error('SOURCE_READ_GATE_REFUSED');
  const owner = structuredClone(binding), seen = new Set(), grants = new Set();
  let fenced = false, stopping;
  function check() {if (fenced) throw new Error();}
  function bounded(callback) {
    let timer;
    return Promise.race([Promise.resolve().then(callback), new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error()), 45000);
    })]).finally(() => clearTimeout(timer));
  }
  function abort() {
    fenced = true;
    stopping ??= bounded(stop).then(value => {if (value !== true) throw new Error('SOURCE_READ_STOP_UNVERIFIED'); return true;});
    return stopping;
  }
  async function paused(input) {
    try {
      check();
      const {candidate, event, expected, grant} = structuredClone(input);
      if (seen.size >= 256 || seen.has(event.requestId)) throw new Error();
      seen.add(event.requestId);
      if (event.sessionId !== owner.sessionId || !Object.hasOwn(owner.frames, event.frameId)
          || typeof grant !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(grant) || grants.has(grant)) throw new Error();
      grants.add(grant);
      const known = FIXED[candidate.role];
      if (known) {
        if (candidate.url !== policy.origin + known[0] || candidate.method !== known[1]
            || candidate.resourceType !== 'XHR') throw new Error();
      } else if (!['frame_document', 'monthly_statement', 'contract_note'].includes(candidate.role)
          || !(candidate.method === 'GET' || candidate.role === 'frame_document' && candidate.method === 'POST'
            && candidate.url === policy.origin + '/priv/new/releves.php')
          || candidate.resourceType !== 'Document') throw new Error();
      policyUrl(policy, candidate.url);
      if (!HASH.test(candidate.sourceSha256)) throw new Error();
      const observation = inspectSourceRequestForPolicy(policy, {owner: {sessionId: owner.sessionId, frameId: event.frameId},
        candidate, event, expected});
      if (await bounded(() => retain({grant, ...observation})) !== true) throw new Error();
      check();
      // consume owns atomic private publication and rejects grant reuse, including
      // use from another request/process. Retention alone grants no continuation.
      if (await bounded(() => consume({grant, request_id: event.requestId, page_epoch: owner.pageEpoch,
        frame_epoch: owner.frames[event.frameId].epoch})) !== true) throw new Error();
      check(); await bounded(() => continueRequest(event.requestId)); check(); return true;
    } catch {await abort(); throw new Error('SOURCE_READ_GATE_REFUSED');}
  }
  return Object.freeze({paused, abort});
}
