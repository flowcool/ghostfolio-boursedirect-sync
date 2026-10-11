// A credential-free observation grants one known public document request only.
export const PUBLIC_LOGIN_URL = 'https://www.boursedirect.fr/fr/login';
// Read previously observed public scripts as inert documents; never execute them.
export function publicAssetDocumentPolicy(owner, assets) {
  publicLoginPolicy(owner, assets);
  if (!assets.length || assets.some(row => row.resourceType !== 'Script'))
    throw new Error('PUBLIC_OBSERVATION_ASSETS_REFUSED');
  const binding = {...owner}, allowed = new Set(assets.map(row => row.url));
  const seen = new Set(), used = new Set();
  return value => {
    if (!value || typeof value.requestId !== 'string' || !value.requestId || value.requestId.length > 256
        || seen.has(value.requestId) || seen.size >= 256) throw new Error('PUBLIC_OBSERVATION_REQUEST_REFUSED');
    seen.add(value.requestId);
    const url = value.request?.url;
    const permitted = value.sessionId === binding.sessionId && value.frameId === binding.frameId
      && value.resourceType === 'Document' && value.request?.method === 'GET'
      && allowed.has(url) && !used.has(url) && !Object.hasOwn(value, 'redirectedRequestId');
    if (permitted) used.add(url);
    return permitted;
  };
}
export function publicLoginPolicy(owner, assets = [], authBootstrap = false) {
  if (typeof authBootstrap !== 'boolean') throw new Error('PUBLIC_OBSERVATION_ASSETS_REFUSED');
  if (!owner || Object.keys(owner).length !== 2 || ['sessionId', 'frameId'].some(key =>
    typeof owner[key] !== 'string' || !owner[key] || owner[key].length > 256))
    throw new Error('PUBLIC_OBSERVATION_OWNER_REFUSED');
  if (!Array.isArray(assets) || assets.length > 32) throw new Error('PUBLIC_OBSERVATION_ASSETS_REFUSED');
  const reads = new Set();
  for (const row of assets) {
    if (!row || Object.keys(row).length !== 2 || !Object.hasOwn(row, 'url') || !Object.hasOwn(row, 'resourceType')
        || typeof row.url !== 'string' || row.url.length > 4096
        || !['Script', 'Stylesheet', 'Image', 'Font'].includes(row.resourceType))
      throw new Error('PUBLIC_OBSERVATION_ASSETS_REFUSED');
    let url; try {url = new URL(row.url);} catch {throw new Error('PUBLIC_OBSERVATION_ASSETS_REFUSED');}
    if (url.origin !== 'https://www.boursedirect.fr' || url.username || url.password || url.hash || url.href !== row.url)
      throw new Error('PUBLIC_OBSERVATION_ASSETS_REFUSED');
    const key = JSON.stringify([row.url, row.resourceType]);
    if (reads.has(key)) throw new Error('PUBLIC_OBSERVATION_ASSETS_REFUSED');
    reads.add(key);
  }
  const binding = {...owner}, seen = new Set(), usedAssets = new Set(), usedBootstrap = new Set();
  const startedAt = Date.now();
  let consumed = false;
  return value => {
    if (!value || typeof value.requestId !== 'string' || !value.requestId || value.requestId.length > 256
        || seen.has(value.requestId) || seen.size >= 256) throw new Error('PUBLIC_OBSERVATION_REQUEST_REFUSED');
    seen.add(value.requestId);
    const permitted = !consumed && value.sessionId === binding.sessionId && value.frameId === binding.frameId
      && value.resourceType === 'Document' && value.request?.method === 'GET'
      && value.request.url === PUBLIC_LOGIN_URL && !Object.hasOwn(value, 'redirectedRequestId');
    if (permitted) {consumed = true; return true;}
    const match = authBootstrap && typeof value.request?.url === 'string'
      ? /^https:\/\/www\.boursedirect\.fr\/apps\/auth\/production\/auth\.(js|css)\?version=([0-9]{13})$/.exec(value.request.url) : null;
    const current = Date.now();
    const key = JSON.stringify([value.request?.url, value.resourceType]);
    if (consumed && match && !usedBootstrap.has(match[1]) && current >= startedAt
        && !usedAssets.has(key)
        && current - startedAt <= 60000 && Number(match[2]) >= startedAt && Number(match[2]) <= current + 1000
        && value.sessionId === binding.sessionId && value.frameId === binding.frameId
        && value.request.method === 'GET' && !Object.hasOwn(value, 'redirectedRequestId')
        && value.resourceType === (match[1] === 'js' ? 'Script' : 'Stylesheet')) {
      usedBootstrap.add(match[1]); usedAssets.add(key); return true;
    }
    const read = consumed && value.sessionId === binding.sessionId && value.frameId === binding.frameId
      && value.request?.method === 'GET' && !Object.hasOwn(value, 'redirectedRequestId')
      && reads.has(key) && !usedAssets.has(key) && !(match && usedBootstrap.has(match[1]));
    if (read) {usedAssets.add(key); if (match) usedBootstrap.add(match[1]);}
    return read;
  };
}
