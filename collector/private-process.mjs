// Trusted runtime launcher only; never callable through an operator command.
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';

export function verifyExecutable(pin) {
  let fd;
  try {
    fd = fs.openSync(pin.path, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
    const stat = fs.fstatSync(fd);
    if (!stat.isFile() || stat.size > 134217728 || stat.nlink !== 1 || (stat.mode & 0o022)) return false;
    return createHash('sha256').update(fs.readFileSync(fd)).digest('hex') === pin.sha256;
  } catch {return false;} finally {if (fd !== undefined) fs.closeSync(fd);}
}

export function executePrivate(executable, args, env, timeoutMs = 45000, input) {
  return new Promise((resolve, reject) => {
    let child, timer, out = [], error = [], bytes = 0, settled = false, timedOut = false;
    function fail() {if (child?.pid) {try {process.kill(-child.pid, 'SIGKILL');} catch { /* Exit listener settles. */ }} }
    try {
      if (input !== undefined && (!Buffer.isBuffer(input) || input.length > 32768)) throw new Error();
      child = spawn(executable, args, {env, detached: true, stdio: [input === undefined ? 'ignore' : 'pipe', 'pipe', 'pipe']});
      timer = setTimeout(() => {timedOut = true; fail();}, timeoutMs);
      if (input !== undefined) {
        child.stdin.on('error', () => {timedOut = true; fail();});
        child.stdin.end(input);
      }
      const collect = target => value => {bytes += value.length; if (bytes > 294912) {timedOut = true; fail();} else target.push(value);};
      child.stdout.on('data', collect(out)); child.stderr.on('data', collect(error));
      child.on('error', () => {if (!settled) {settled = true; clearTimeout(timer); reject(new Error('PRIVATE_PROCESS_FAILED'));}});
      child.on('close', status => {
        if (settled) return; settled = true; clearTimeout(timer);
        if (timedOut) {reject(new Error('PRIVATE_PROCESS_FAILED')); return;}
        try {
          const decode = new TextDecoder('utf-8', {fatal: true});
          resolve({status, stdout: decode.decode(Buffer.concat(out)), stderr: decode.decode(Buffer.concat(error))});
        } catch {reject(new Error('PRIVATE_PROCESS_FAILED'));}
        finally {out = error = [];}
      });
    } catch {clearTimeout(timer); fail(); reject(new Error('PRIVATE_PROCESS_FAILED'));}
  });
}

// Initial collector environment constructed inside its container; browser env
// is independently minimal. IPC fd is anonymous, fixed and inherited once.
export function collectorEnvironment(selected, home) {
  if (!selected || typeof selected.login !== 'string' || typeof selected.password !== 'string'
      || typeof home !== 'string' || !home.startsWith('/')) throw new Error('PRIVATE_PROCESS_FAILED');
  return {PATH: '/usr/bin:/bin', HOME: home, BD_LOGIN: selected.login, BD_PASSWORD: selected.password};
}
