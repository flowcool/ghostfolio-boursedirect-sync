// Opt-in network-none host proof. Synthetic data only; no broker or vault adapter.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {capabilityPipe, PIPE_LIMITS} from '../capability-pipe.mjs';

export function sandboxStatus(raw, baseline) {
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
  if (status.NoNewPrivs !== '1' || status.Seccomp !== '2' || parent.Seccomp !== '2'
      || parentFilters < 1 || filters <= parentFilters || !pids || pids.length < 2
      || pids.some(value => !/^[1-9]\d*$/.test(value))) throw new Error('SANDBOX_STATUS_REFUSED');
  return {no_new_privileges: true, additional_seccomp_filter: true,
    nested_pid_namespace: true, seccomp_filters: filters, baseline_seccomp_filters: parentFilters};
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

let stage = 'runtime_prerequisites', sandboxUnavailable = false;
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
  if (!Number.isSafeInteger(child.pid) || child.pid < 2) throw new Error('SANDBOX_PROCESS_REFUSED');
  let exited = false, fenced = false, stopping, stderrBytes = 0, pipe, result;
  const exit = once(child, 'exit').then(() => {exited = true;});
  exit.catch(() => {});
  async function waitExit() {
    let timer;
    try {await Promise.race([exit, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error('SANDBOX_EXIT_TIMEOUT')), 5000);
    })]);} finally {clearTimeout(timer);}
  }
  function stop() {
    stopping ??= (async () => {
      if (!exited) {
        process.kill(-child.pid, 'SIGTERM');
        try {await waitExit();} catch {
          if (!exited) process.kill(-child.pid, 'SIGKILL');
          await waitExit();
        }
      }
      if (!exited) throw new Error('SANDBOX_EXIT_UNVERIFIED');
    })();
    return stopping;
  }
  function fence() {fenced = true; void stop().catch(() => {});}
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
  child.stdio[4].on('end', () => {if (!exited) fence();});
  pipe.armEvents();
  try {
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
    stage = 'renderer_os_sandbox';
    const renderers = [];
    for (const name of fs.readdirSync('/proc').filter(value => /^\d+$/.test(value))) {
      try {
        const stat = fs.readFileSync('/proc/' + name + '/stat', 'utf8');
        const group = Number(stat.slice(stat.lastIndexOf(')') + 2).split(' ')[2]);
        const args = fs.readFileSync('/proc/' + name + '/cmdline', 'utf8').split('\0');
        if (group !== child.pid || !args.includes('--type=renderer')) continue;
        renderers.push(sandboxStatus(fs.readFileSync('/proc/' + name + '/status', 'utf8'), baseline));
      } catch (error) {if (error.message === 'SANDBOX_STATUS_REFUSED') throw error;}
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
    pipe.lost();
  }
  stage = 'owned_group_exit';
  const aliveOwnedGroup = () => fs.readdirSync('/proc').filter(value => /^\d+$/.test(value)).some(name => {
    try {
      const stat = fs.readFileSync('/proc/' + name + '/stat', 'utf8');
      const fields = stat.slice(stat.lastIndexOf(')') + 2).split(' ');
      return Number(fields[2]) === child.pid && !['Z','X'].includes(fields[0]);
    } catch (error) {if (error.code !== 'ENOENT') throw error; return false;}
  });
  for (let attempt = 0; attempt < 50 && aliveOwnedGroup(); attempt++)
    await new Promise(resolve => setTimeout(resolve, 100));
  if (aliveOwnedGroup()) throw new Error('SANDBOX_DESCENDANTS_UNVERIFIED');
  result.owned_browser_exit_verified = true;
  result.owned_group_exit_verified = true;
  return result;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {console.log(JSON.stringify(await prove()));}
  catch {console.error(JSON.stringify({code: 'BROWSER_SANDBOX_NOT_QUALIFIED', stage,
    sandbox_unavailable_message_observed: sandboxUnavailable})); process.exitCode = 1;}
}
