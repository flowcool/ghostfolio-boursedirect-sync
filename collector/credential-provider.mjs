// Pure trusted-worker/provider interfaces; no CLI, networking or secret-store access.
import {principal, brokerUrl, totp, otpFromEnvironment} from './core.mjs';
const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;
const HASH = /^[0-9a-f]{64}$/;
const PROFILE = Object.freeze({algorithm: 'SHA1', period: 30, digits: 6});
function exact(value, keys) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || Object.keys(value).length !== keys.length || keys.some(k => !Object.hasOwn(value, k))) throw new Error();
}
function uuid(value) { if (typeof value !== 'string' || !UUID.test(value)) throw new Error(); }
function text(value) { if (typeof value !== 'string' || !value || value.length > 4096 || /[\x00-\x1f\x7f]/.test(value)) throw new Error(); }
function time(value) { if (!Number.isSafeInteger(value) || value < 0) throw new Error(); }

// Invoke only inside the trusted worker. Return profile, never secret or TOTP URI.
export function validateWorkerTotp(value, defaultsVerified = false) {
  try {
    text(value); let secret = value;
    if (value.startsWith('otpauth://')) {
      const uri = new URL(value);
      if (uri.protocol !== 'otpauth:' || uri.hostname !== 'totp' || uri.username || uri.password
          || uri.port || uri.hash || !uri.pathname || uri.pathname === '/') throw new Error();
      const values = Object.create(null);
      for (const [key, val] of uri.searchParams) {
        if (!['secret', 'issuer', 'algorithm', 'digits', 'period'].includes(key) || Object.hasOwn(values, key)) throw new Error();
        values[key] = val;
      }
      secret = values.secret;
      const required = {algorithm: 'SHA1', digits: '6', period: '30'};
      for (const [key, expected] of Object.entries(required)) {
        if (values[key] === undefined ? defaultsVerified !== true : values[key] !== expected) throw new Error();
      }
    } else if (defaultsVerified !== true) throw new Error();
    // Existing strict pure SHA1/30s/6digit helper validates Base32 without exporting it.
    totp(secret, 120);
    return {...PROFILE};
  } catch { throw new Error('PROVIDER_PROFILE_INVALID'); }
}

export function selectWorkerItem(item, binding, defaultsVerified = false) {
  try {
    exact(binding, ['itemId', 'name', 'uri', 'principalHash', 'accountConfig']);
    uuid(binding.itemId); text(binding.name); brokerUrl(binding.uri);
    if (!HASH.test(binding.principalHash)) throw new Error();
    exact(binding.accountConfig, ['path', 'sha256']); text(binding.accountConfig.path);
    if (!HASH.test(binding.accountConfig.sha256)) throw new Error();
    if (!item || item.id !== binding.itemId || item.name !== binding.name || item.type !== 1 || item.deletedDate) throw new Error();
    const login = item.login;
    if (!login || !Array.isArray(login.uris) || login.uris.length !== 1
        || login.uris[0]?.uri !== binding.uri || principal(login.username) !== binding.principalHash) throw new Error();
    text(login.username); text(login.password);
    const profile = validateWorkerTotp(login.totp, defaultsVerified);
    // Only validated login fields/profile leave this worker helper; no raw item/seed.
    return {login: login.username, password: login.password, profile, itemId: binding.itemId,
      principalHash: binding.principalHash, accountConfig: structuredClone(binding.accountConfig), online_ready: false};
  } catch { throw new Error('PROVIDER_ITEM_INVALID'); }
}

export function credentialMode(env, providerSelected) {
  if (!env || typeof env !== 'object' || typeof providerSelected !== 'boolean') throw new Error('PROVIDER_MODE_INVALID');
  // Presence, including malformed/empty values, counts as a competing mode.
  const initial = ['BD_OTP', 'BD_OTP_ISSUED_AT', 'BD_TOTP_SECRET'].some(key => Object.hasOwn(env, key));
  if (providerSelected && initial) throw new Error('PROVIDER_MODE_CONFLICT');
  return providerSelected ? 'provider' : 'initial-environment';
}

export function validateProviderCode(value, expected, receiptTime) {
  try {
    exact(value, ['runNonce', 'stageNonce', 'code', 'startedAt', 'completedAt', 'profile']);
    exact(expected, ['runNonce', 'stageNonce']); uuid(expected.runNonce); uuid(expected.stageNonce);
    if (value.runNonce !== expected.runNonce || value.stageNonce !== expected.stageNonce) throw new Error();
    exact(value.profile, Object.keys(PROFILE));
    if (Object.entries(PROFILE).some(([k,v]) => value.profile[k] !== v)) throw new Error();
    time(value.startedAt); time(value.completedAt); time(receiptTime);
    if (value.startedAt > value.completedAt || value.completedAt > receiptTime
        || Math.floor(value.startedAt / 30) !== Math.floor(value.completedAt / 30)) throw new Error();
    const code = otpFromEnvironment({BD_OTP: value.code, BD_OTP_ISSUED_AT: String(value.startedAt)}, receiptTime);
    return {code, otp: {issuedAt: value.startedAt, step: Math.floor(value.startedAt / 30)}, online_ready: false};
  } catch { throw new Error('PROVIDER_CODE_INVALID'); }
}

export function delayedOtpProvider({runNonce, stageNonce, fetchCode, now, env = {}, timeoutMs = 45000}) {
  try {
    uuid(runNonce); uuid(stageNonce); credentialMode(env, true);
    if (typeof fetchCode !== 'function' || typeof now !== 'function'
        || !Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 45000) throw new Error();
  } catch { throw new Error('PROVIDER_CONFIG_INVALID'); }
  const expected = {runNonce, stageNonce}; let used = false, fenced = false;
  async function request(input) {
    // Reserve before any callback or await; no retry after refusal or timeout.
    if (used || fenced) {fenced = true; throw new Error('PROVIDER_REQUEST_REJECTED');}
    used = true; let timer;
    try {
      exact(input, ['runNonce', 'stageNonce']);
      if (input.runNonce !== runNonce || input.stageNonce !== stageNonce) throw new Error();
      const startedAt = now(); time(startedAt);
      if (30 - startedAt % 30 < 5) throw new Error();
      const timeout = new Promise((_, reject) => {timer = setTimeout(() => reject(new Error()), timeoutMs);});
      const response = await Promise.race([Promise.resolve().then(() => {
        if (fenced) throw new Error(); return fetchCode({...expected});
      }), timeout]);
      if (fenced) throw new Error();
      // Trusted worker brackets its own CLI; controller adds the earlier request bound.
      const receiptTime = now(); time(receiptTime);
      if (response?.startedAt < startedAt) throw new Error();
      return validateProviderCode(response, expected, receiptTime);
    } catch {fenced = true; throw new Error('PROVIDER_REQUEST_REJECTED');}
    finally {clearTimeout(timer);}
  }
  return {request, status: () => ({used, fenced, online_ready: false})};
}
