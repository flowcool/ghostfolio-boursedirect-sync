// Internal cooperation boundary; never selected by an operator command or env.
const policies = new WeakSet();
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function register(value) { const policy = Object.freeze(value); policies.add(policy); return policy; }
export const BROKER_POLICY = register({kind: 'broker', origin: 'https://www.boursedirect.fr'});

export function syntheticPolicy(origin, allocation) {
  const match = typeof origin === 'string' && /^http:\/\/127\.0\.0\.1:([1-9][0-9]{0,4})$/.exec(origin);
  if (!match || Number(match[1]) > 65535 || new URL(origin).origin !== origin
      || typeof allocation !== 'string' || !UUID.test(allocation)) {
    throw new Error('SYNTHETIC_POLICY_INVALID');
  }
  return register({kind: 'synthetic-cdp-v1', origin, allocation});
}

export function requirePolicy(policy) {
  if (!policies.has(policy)) throw new Error('SOURCE_POLICY_INVALID');
  return policy;
}

export function policyUrl(policy, value) {
  requirePolicy(policy);
  if (typeof value !== 'string' || value.length > 4096) throw new Error('BROKER_URL_INVALID');
  let url; try {url = new URL(value);} catch {throw new Error('BROKER_URL_INVALID');}
  if (url.origin !== policy.origin || url.username || url.password || value.includes('#')
      || url.href !== value || /%2f|%5c|%2e/i.test(url.pathname)) throw new Error('BROKER_URL_INVALID');
  return url;
}
