// Opt-in network-none host proof. Synthetic data only; no broker or vault adapter.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import {capabilityPipe, PIPE_LIMITS} from '../capability-pipe.mjs';

export function sandboxDetails(raw, baseline) {
  function fields(value) {
    const result = {};
    for (const line of value.split('\n')) {
      const match = /^([A-Za-z_]+):\s*(.*?)\s*$/.exec(line);
      if (!match) continue;
      if (Object.hasOwn(result, match[1])) throw new Error('SANDBOX_STATUS_REFUSED');
      result[match[1]] = match[2];
    }
    return result;
  }
  const status = fields(raw), parent = fields(baseline);
  const pids = status.NSpid?.split(/\s+/);
  const filters = /^\d+$/.test(status.Seccomp_filters ?? '') ? Number(status.Seccomp_filters) : 0;
  const parentFilters = /^\d+$/.test(parent.Seccomp_filters ?? '') ? Number(parent.Seccomp_filters) : 0;
  return {no_new_privileges: status.NoNewPrivs === '1', seccomp_filter_mode: status.Seccomp === '2',
    baseline_seccomp_filter_mode: parent.Seccomp === '2', additional_seccomp_filter: parentFilters >= 1 && filters > parentFilters,
    nested_pid_namespace: Boolean(pids && pids.length >= 2 && pids.every(value => /^[1-9]\d*$/.test(value))),
    pid_namespace_depth: pids?.length ?? 0, seccomp_filters: filters, baseline_seccomp_filters: parentFilters};
}
export function sandboxStatus(raw, baseline) {
  const result = sandboxDetails(raw, baseline);
  if (!result.no_new_privileges || !result.seccomp_filter_mode || !result.baseline_seccomp_filter_mode
      || !result.additional_seccomp_filter || !result.nested_pid_namespace) throw new Error('SANDBOX_STATUS_REFUSED');
  return result;
}

export function loopbackNamespace(raw) {
  const names = raw.split('\n').slice(2).filter(line => line.trim()).map(line => {
    const match = /^\s*([^:\s]+):/.exec(line);
    if (!match) throw new Error('SANDBOX_NETWORK_REFUSED');
    return match[1];
  });
  if (names.length !== 1 || names[0] !== 'lo') throw new Error('SANDBOX_NETWORK_REFUSED');
  return true;
}

export function processIdentity(raw) {
  const match = /^(\d+) \(.*\) (.*)$/.exec(raw.trim());
  const fields = match?.[2].split(/\s+/);
  if (!match || fields.length < 20 || !/^[A-Z]$/.test(fields[0])
      || ![match[1], fields[1], fields[2], fields[19]].every(value => /^\d+$/.test(value)))
    throw new Error('SANDBOX_PROCESS_REFUSED');
  const result = {pid: Number(match[1]), ppid: Number(fields[1]), group: Number(fields[2]),
    start: fields[19], state: fields[0]};
  if (![result.pid, result.ppid, result.group].every(Number.isSafeInteger) || result.pid < 2)
    throw new Error('SANDBOX_PROCESS_REFUSED');
  return result;
}
export function sameProcess(expected, current) {
  return Boolean(expected && current && expected.pid === current.pid && expected.start === current.start);
}
export function ownedDescendants(rows, root) {
  const table = new Map(rows.map(row => [row.pid, row]));
  if (table.size !== rows.length || !sameProcess(root, table.get(root.pid)))
    throw new Error('SANDBOX_OWNERSHIP_REFUSED');
  const owned = new Map([[root.pid, table.get(root.pid)]]);
  for (let pass = 0; pass < rows.length; pass++) {
    const before = owned.size;
    for (const row of rows) if (owned.has(row.ppid) && !owned.has(row.pid)) owned.set(row.pid, row);
    if (before === owned.size) break;
  }
  return owned;
}
function readIdentity(pid) {
  try {return processIdentity(fs.readFileSync('/proc/' + pid + '/stat', 'utf8'));}
  catch (error) {if (error.code === 'ENOENT') return undefined; throw error;}
}
function processTable() {
  const names = fs.readdirSync('/proc').filter(value => /^\d+$/.test(value) && Number(value) >= 2);
  if (names.length > 256) throw new Error('SANDBOX_PROCESS_LIMIT');
  return names.map(name => readIdentity(name)).filter(Boolean);
}

// Install lifecycle listeners before attempting proc acquisition or pipe setup.
export function ownedBrowserLifecycle(child, {read = readIdentity, table = processTable,
  signal = (pid, value) => process.kill(pid, value), delay = () => new Promise(resolve => setTimeout(resolve, 100))} = {}) {
  let root, observed = false, exited = false, closed = false, spawnFailed = false, stopping;
  const known = new Map();
  child.on('error', () => {spawnFailed = true;});
  child.on('exit', () => {exited = true;});
  child.on('close', () => {closed = true;});
  function pin() {
    if (!Number.isSafeInteger(child.pid) || child.pid < 2 || spawnFailed) throw new Error('SANDBOX_PROCESS_REFUSED');
    const current = read(child.pid);
    if (!current || exited) throw new Error('SANDBOX_PROCESS_REFUSED');
    if (root && !sameProcess(root, current)) throw new Error('SANDBOX_OWNERSHIP_REFUSED');
    root = current; known.set(root.pid, root);
  }
  function observe() {
    if (!root || !sameProcess(root, read(root.pid))) return new Map();
    const owned = ownedDescendants(table(), root);
    for (const [pid, row] of owned) {
      if (known.has(pid) && !sameProcess(known.get(pid), row)) throw new Error('SANDBOX_OWNERSHIP_REFUSED');
      known.set(pid, row);
    }
    observed = true;
    return owned;
  }
  function live() {
    return [...known.values()].filter(row => {
      const current = read(row.pid);
      return sameProcess(row, current) && !['Z', 'X'].includes(current.state);
    });
  }
  function signalOwned(value) {
    for (const row of [...known.values()].reverse()) {
      const current = read(row.pid);
      if (!sameProcess(row, current) || ['Z', 'X'].includes(current.state)) continue;
      try {signal(row.pid, value);} catch (error) {if (error.code !== 'ESRCH') throw error;}
    }
  }
  function absentUnpinnedRoot() {
    return !Number.isSafeInteger(child.pid) || child.pid < 2 || read(child.pid) === undefined;
  }
  function verified() {
    return (exited || (spawnFailed && closed)) && live().length === 0
      && (root === undefined ? absentUnpinnedRoot() : observed);
  }
  async function waitExit() {
    for (let attempt = 0; attempt < 50; attempt++) {
      if (verified()) return;
      await delay();
    }
    throw new Error('SANDBOX_EXIT_TIMEOUT');
  }
  function stop() {
    stopping ??= (async () => {
      // A failed initial proc read can still recover a pinned exact child before signaling.
      if (!root && !exited && !spawnFailed && Number.isSafeInteger(child.pid) && read(child.pid)) pin();
      observe();
      signalOwned('SIGTERM');
      try {await waitExit();} catch {signalOwned('SIGKILL'); await waitExit();}
      if (!verified()) throw new Error('SANDBOX_EXIT_UNVERIFIED');
      return true;
    })();
    return stopping;
  }
  return {pin, observe, stop, exited: () => exited, live};
}

let stage = 'runtime_prerequisites', sandboxUnavailable = false;
const osObservation = {owned_descendant_processes: 0, renderers_found: 0, renderer_status: [], proc_read_failures: 0};
async function prove() {
  if (process.getuid() !== 1000) throw new Error('SANDBOX_RUNTIME_REFUSED');
  stage = 'network_namespace';
  loopbackNamespace(fs.readFileSync('/proc/net/dev', 'utf8'));
  const profile = fs.mkdtempSync('/home/fixture/synthetic-sandbox-');
  const baseline = fs.readFileSync('/proc/self/status', 'utf8');
  stage = 'chrome_launch';
  const child = spawn('/opt/chrome-headless-shell-linux64/chrome-headless-shell', [
    '--no-startup-window', '--remote-debugging-pipe', '--user-data-dir=' + profile,
    '--disable-background-networking', '--disable-extensions', '--disable-component-extensions-with-background-pages',
    '--disable-component-update', '--disable-default-apps', '--no-first-run', '--no-default-browser-check'],
  {detached: true, env: {PATH: '/usr/bin:/bin', HOME: '/home/fixture'},
    stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe']});
  const lifecycle = ownedBrowserLifecycle(child);
  let fenced = false, stderrBytes = 0, pipe, result;
  const stop = lifecycle.stop;
  function fence() {fenced = true; void stop().catch(() => {});}
  try {
    lifecycle.pin();
    child.on('error', fence);
    child.stderr.on('data', bytes => {
      stderrBytes += bytes.length;
      if (/No usable sandbox|Failed to move to new namespace|Operation not permitted/.test(bytes.toString())) sandboxUnavailable = true;
      if (stderrBytes > 32768) fence();
    });
    pipe = capabilityPipe({write: raw => new Promise((resolve, reject) => {
      child.stdio[3].write(raw, error => error ? reject(error) : resolve());
    }), onEvent: () => {}, fence, limits: {...PIPE_LIMITS, commandMs: 10000, sessionMs: 60000}});
    child.stdio[4].on('data', bytes => {try {pipe.receive(bytes);} catch {fence();}});
    child.stdio[4].on('end', () => {if (!lifecycle.exited()) fence();});
    pipe.armEvents();
    stage = 'chrome_version';
    const version = await pipe.send('Browser.getVersion');
    if (!/^(?:HeadlessChrome|Chrome)\/155\.0\.8059\.39$/.test(version.product)) throw new Error();
    stage = 'synthetic_target';
    const target = await pipe.send('Target.createTarget', {url: 'about:blank'});
    const attached = await pipe.send('Target.attachToTarget', {targetId: target.targetId, flatten: true});
    pipe.registerSession(attached.sessionId);
    await pipe.send('Page.enable', {}, attached.sessionId);
    stage = 'synthetic_document';
    await pipe.send('Page.navigate', {url: 'data:text/html,<title>SYNTHETIC_SANDBOX_PROOF</title>'}, attached.sessionId);
    let title;
    for (let attempt = 0; attempt < 20; attempt++) {
      title = await pipe.send('Runtime.evaluate', {expression: 'document.title', returnByValue: true}, attached.sessionId);
      if (title.result?.value === 'SYNTHETIC_SANDBOX_PROOF') break;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    if (title?.result?.value !== 'SYNTHETIC_SANDBOX_PROOF') throw new Error();
    stage = 'renderer_process_inventory';
    const processes = await pipe.send('SystemInfo.getProcessInfo');
    if (!Array.isArray(processes.processInfo) || processes.processInfo.length > 256)
      throw new Error('SANDBOX_PROCESS_REFUSED');
    const rendererIds = processes.processInfo.filter(row => row.type === 'renderer').map(row => row.id);
    if (rendererIds.length === 0 || new Set(rendererIds).size !== rendererIds.length
        || rendererIds.some(pid => !Number.isSafeInteger(pid) || pid < 2))
      throw new Error('SANDBOX_PROCESS_REFUSED');
    stage = 'renderer_ownership';
    const owned = lifecycle.observe(), renderers = [];
    osObservation.owned_descendant_processes = owned.size;
    osObservation.renderers_found = rendererIds.length;
    for (const pid of rendererIds) {
      const identity = owned.get(pid);
      if (!identity || !sameProcess(identity, readIdentity(pid))) throw new Error('SANDBOX_OWNERSHIP_REFUSED');
      stage = 'renderer_os_sandbox';
      const rawStatus = fs.readFileSync('/proc/' + pid + '/status', 'utf8');
      if (!sameProcess(identity, readIdentity(pid))) throw new Error('SANDBOX_OWNERSHIP_REFUSED');
      osObservation.renderer_status.push(sandboxDetails(rawStatus, baseline));
      renderers.push(sandboxStatus(rawStatus, baseline));
    }
    if (fenced || renderers.length === 0) throw new Error();
    result = {code: 'BROWSER_SANDBOX_QUALIFIED', chrome_version: '155.0.8059.39',
      network_none: true, synthetic_document_rendered: true, renderer_count: renderers.length,
      renderer_sandbox: renderers, broker_requests: 0, credentials_read: false};
  } finally {
    const failedStage = stage;
    try {await stop();} catch {stage = 'owned_browser_exit'; throw new Error('SANDBOX_EXIT_UNVERIFIED');}
    stage = failedStage;
    // Observe owned browser exit before intentional pipe closure.
    pipe?.lost();
  }
  stage = 'owned_descendant_exit';
  if (lifecycle.live().length) throw new Error('SANDBOX_DESCENDANTS_UNVERIFIED');
  result.owned_browser_exit_verified = true;
  result.owned_descendant_exit_verified = true;
  return result;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {console.log(JSON.stringify(await prove()));}
  catch {console.error(JSON.stringify({code: 'BROWSER_SANDBOX_NOT_QUALIFIED', stage,
    sandbox_unavailable_message_observed: sandboxUnavailable, os_observation: osObservation})); process.exitCode = 1;}
}
