// A credential-free observation grants one known public document request only.
export const PUBLIC_LOGIN_URL = 'https://www.boursedirect.fr/fr/login';
export function publicLoginPolicy(owner) {
  if (!owner || Object.keys(owner).length !== 2 || ['sessionId', 'frameId'].some(key =>
    typeof owner[key] !== 'string' || !owner[key] || owner[key].length > 256))
    throw new Error('PUBLIC_OBSERVATION_OWNER_REFUSED');
  const binding = {...owner}, seen = new Set();
  let consumed = false;
  return value => {
    if (!value || typeof value.requestId !== 'string' || !value.requestId || value.requestId.length > 256
        || seen.has(value.requestId) || seen.size >= 256) throw new Error('PUBLIC_OBSERVATION_REQUEST_REFUSED');
    seen.add(value.requestId);
    const permitted = !consumed && value.sessionId === binding.sessionId && value.frameId === binding.frameId
      && value.resourceType === 'Document' && value.request?.method === 'GET'
      && value.request.url === PUBLIC_LOGIN_URL && !Object.hasOwn(value, 'redirectedRequestId');
    if (permitted) consumed = true;
    return permitted;
  };
}
