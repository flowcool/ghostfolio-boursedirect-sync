// Source-described protocol outcomes only. No cookies, headers or raw body return.
import {parseDocument} from 'yaml';
import {requirePolicy, policyUrl} from './internal/source-policy.mjs';
export function inspectSourceAuthenticationResponse(policy, {phase, status, body, base64Encoded}) {
  try {
    requirePolicy(policy);
    if (!Number.isSafeInteger(status) || typeof body !== 'string' || Buffer.byteLength(body) > 65536
        || typeof base64Encoded !== 'boolean') throw new Error();
    if (base64Encoded) {
      const bytes = Buffer.from(body, 'base64');
      if (bytes.toString('base64') !== body) throw new Error();
      body = new TextDecoder('utf-8', {fatal: true}).decode(bytes);
    }
    let value;
    if (body !== '') {
      const document = parseDocument(body, {uniqueKeys: true});
      if (document.errors.length || document.warnings.length) throw new Error();
      value = JSON.parse(body);
    }
    const object = value && typeof value === 'object' && !Array.isArray(value);
    if (phase === 'password_uncertain') {
      if (![400, 401, 403].includes(status) || !object || value.error !== '2FA required') throw new Error();
      return Object.freeze({outcome: 'known_totp_challenge', status});
    }
    if (phase === 'otp_uncertain') {
      if (status !== 200 || !object || Object.hasOwn(value, 'error') || value.success !== true) throw new Error();
      return Object.freeze({outcome: 'otp_accepted', status});
    }
    if (phase === 'finalization_uncertain') {
      if (status !== 200 || !object || Object.hasOwn(value, 'error') || typeof value.redirect !== 'string') throw new Error();
      const url = new URL(value.redirect, policy.origin);
      policyUrl(policy, url.href);
      if (url.pathname === '/fr/login' || !url.pathname.startsWith('/fr/page/') || url.search || url.hash) throw new Error();
      return Object.freeze({outcome: 'credentials_finalized', status, document_url: url.href});
    }
    throw new Error();
  } catch {throw new Error('SOURCE_AUTHENTICATION_RESPONSE_REFUSED');}
}
