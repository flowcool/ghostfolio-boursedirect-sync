// Dedicated owned browser pipe. CDP stdout is private protocol, never a log.
// SSH/exec owner must pin this source, full container ID, egress and executable.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import {ownedBrowserLifecycle, sandboxStatus, processIdentity, sameProcess} from './browser-sandbox-proof.mjs';

export function validateSourceBrowserRuntime(proxy, env, uid) {
  try {
  if (uid !== 1000 || typeof proxy !== 'string'
      || !/^http:\/\/(?:[0-9]{1,3}\.){3}[0-9]{1,3}:8080$/.test(proxy)
      || new URL(proxy).origin !== proxy || new URL(proxy).hostname.split('.').some(value => Number(value) > 255)
      || !env || Object.keys(env).sort().join(',') !== 'HOME,PATH'
      || env.HOME !== '/home/fixture' || env.PATH !== '/usr/bin:/bin') throw new Error('SOURCE_BROWSER_RUNTIME_REFUSED');
  return proxy;
  } catch {throw new Error('SOURCE_BROWSER_RUNTIME_REFUSED');}
}

export async function sourceBrowserPipe(proxy) {
  validateSourceBrowserRuntime(proxy, process.env, process.getuid());
  process.umask(0o077);
  const profile = fs.mkdtempSync('/home/fixture/source-qualification-');
  const child = spawn('/opt/chrome-headless-shell-linux64/chrome-headless-shell', [
    '--no-startup-window', '--remote-debugging-pipe', '--user-data-dir=' + profile,
    '--proxy-server=' + proxy, '--proxy-bypass-list=<-loopback>',
    '--disable-background-networking', '--disable-extensions', '--disable-component-extensions-with-background-pages',
    '--disable-component-update', '--disable-default-apps', '--disable-popup-blocking', '--no-first-run', '--no-default-browser-check'],
    {detached: true, env: {PATH: '/usr/bin:/bin', HOME: '/home/fixture'},
      stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe']});
  const lifecycle = ownedBrowserLifecycle(child);
  let lifetime, monitor, closing, stderrBytes = 0, rendererProof = false, processProof = false;
  const baseline = fs.readFileSync('/proc/self/status', 'utf8');
  let complete;
  const done = new Promise(resolve => {complete = resolve;});
  function close(failure = false) {
    if (failure) process.exitCode = 1;
    closing ??= (async () => {
      clearTimeout(lifetime); clearInterval(monitor);
      const verified = await lifecycle.stop();
      if (verified !== true) throw new Error('SOURCE_BROWSER_EXIT_UNVERIFIED');
      process.stdin.unpipe(child.stdio[3]); process.stdin.destroy();
      child.stdio[4].unpipe(process.stdout);
      await new Promise((resolve, reject) => process.stderr.write(JSON.stringify({
        code: 'OWNED_BROWSER_PIPE_CLOSED', browser_exit_verified: true,
        renderer_sandbox_verified: rendererProof}) + '\n', error => error ? reject(error) : resolve()));
      complete(true);
    })().catch(() => {process.exitCode = 1; complete(false);});
    return closing;
  }
  function fail() {void close(true);}
  try {
    lifecycle.pin();
    child.stderr.on('data', bytes => {stderrBytes += bytes.length; if (stderrBytes > 32768) fail();});
    child.on('error', fail);
    child.on('exit', () => {if (!closing) fail();});
    process.stdin.on('end', () => {void close();}); process.stdin.on('error', fail);
    process.stdout.on('error', fail);
    child.stdio[3].on('error', fail); child.stdio[4].on('error', fail);
    child.stdio[4].on('end', () => {if (!closing) fail();});
    for (const signal of ['SIGTERM', 'SIGINT']) process.once(signal, fail);
    process.stdin.pipe(child.stdio[3]); child.stdio[4].pipe(process.stdout, {end: false});
    monitor = setInterval(() => {
      if (closing) return;
      try {
        const owned = lifecycle.observe();
        let count = 0;
        const types = [];
        for (const [pid, identity] of owned) {
          const args = fs.readFileSync('/proc/' + pid + '/cmdline', 'utf8');
          const type = /(?:^|[ \x00])--type=([a-z_-]+)(?:[ \x00]|$)/.exec(args)?.[1];
          if (type) types.push(type);
          if (type !== 'renderer') continue;
          const raw = fs.readFileSync('/proc/' + pid + '/status', 'utf8');
          const current = processIdentity(fs.readFileSync('/proc/' + pid + '/stat', 'utf8'));
          if (!sameProcess(identity, current)) throw new Error();
          sandboxStatus(raw, baseline); count++;
        }
        if (!processProof) {
          processProof = true;
          process.stderr.write(JSON.stringify({code: 'OWNED_BROWSER_PROCESS_ATTESTED', owned_processes: owned.size, renderers: count, process_types: types}) + '\n');
        }
        if (count && !rendererProof) {
          rendererProof = true;
          process.stderr.write(JSON.stringify({code: 'OWNED_BROWSER_RENDERER_ATTESTED',
            renderer_sandbox_verified: true, chrome_version: '155.0.8059.39'}) + '\n');
        }
      } catch (error) {
        // A short-lived child may disappear between proc reads. Identity changes,
        // unreadable live processes and failed sandbox assertions remain fatal.
        if (error.code !== 'ENOENT') fail();
      }
    }, 200);
    lifetime = setTimeout(fail, 600000);
    return await done;
  } catch {await close(true); return false;}
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    if (process.argv.length !== 3) throw new Error();
    if (await sourceBrowserPipe(process.argv[2]) !== true) process.exitCode = 1;
  } catch {process.stderr.write('{"code":"SOURCE_BROWSER_PIPE_REFUSED"}\n'); process.exitCode = 1;}
}
