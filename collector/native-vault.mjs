// Native CLI subprocesses; Compose supplies initial vault ENV only to this worker.
import fs from 'node:fs';
import path from 'node:path';
import {parseDocument, stringify} from 'yaml';
import {vaultWorker} from './vault-worker.mjs';
import {executePrivate, verifyExecutable} from './private-process.mjs';

export function nativeVaultEnvironment(env, pin) {
  try {
    const required = ['BW_SERVER', 'BW_CLIENTID', 'BW_CLIENTSECRET', 'BW_PASSWORD', 'BW_ITEM_NAME'];
    if (!env || required.some(key => typeof env[key] !== 'string' || !env[key]
      || Buffer.byteLength(env[key]) > 4096 || /[\x00-\x1f\x7f]/.test(env[key]))) throw new Error();
    if (['BW_SESSION', 'BD_LOGIN', 'BD_PASSWORD', 'BD_TOTP_SECRET', 'BD_OTP'].some(key => Object.hasOwn(env, key))) throw new Error();
    const origin = new URL(env.BW_SERVER);
    if (origin.protocol !== 'https:' || origin.origin !== env.BW_SERVER || origin.username || origin.password) throw new Error();
    return {configuration: {schema_version: 5, vaultOrigin: origin.origin,
      binding: {name: env.BW_ITEM_NAME}, cli: pin},
    credentials: Object.fromEntries(['BW_CLIENTID', 'BW_CLIENTSECRET', 'BW_PASSWORD'].map(key => [key, env[key]]))};
  } catch {throw new Error('NATIVE_VAULT_CONFIG_INVALID');}
}

// A trusted in-process collector supplies consume only after its source/journal gates.
// No executable, command, socket or credential-export option is accepted from ENV.
export async function nativeVaultExecution({env, pin, appdata, binding, accountConfig, consume,
  execute = executePrivate, verify = verifyExecutable, now = () => Math.floor(Date.now() / 1000)}) {
  const input = nativeVaultEnvironment(env, pin);
  if (consume !== undefined) {
    if (typeof consume !== 'function' || !binding || binding.name !== env.BW_ITEM_NAME
      || binding.vaultOrigin !== env.BW_SERVER) throw new Error('NATIVE_VAULT_BINDING_REFUSED');
    input.configuration = {...input.configuration, schema_version: 4, binding: {
      itemId: binding.itemId, name: binding.name, uri: binding.uri,
      principalHash: binding.principalHash, uriAliasesSha256: binding.uriAliasesSha256, accountConfig}};
  }
  const worker = vaultWorker({configuration: input.configuration, appdata, execute,
    verifyExecutable: verify, now});
  try {
    const selected = await worker.initialize(input.credentials);
    input.credentials = undefined;
    return consume ? await consume(selected, worker.code) : selected;
  } finally {
    input.credentials = undefined;
    await worker.close();
  }
}

export function retainNativeBinding(directory, env, selected) {
  const code = 'NATIVE_VAULT_BINDING_REFUSED';
  let lock, identity, releaseAllowed = false;
  const lockPath = path.join(directory, 'vault.lock');
  try {
    const root = fs.lstatSync(directory);
    if (!root.isDirectory() || root.uid !== process.getuid() || (root.mode & 0o077)) throw new Error();
    lock = fs.openSync(lockPath, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_NOFOLLOW, 0o600);
    identity = fs.fstatSync(lock);
    fs.fsyncSync(lock);
    const lockParent = fs.openSync(directory, fs.constants.O_RDONLY | fs.constants.O_DIRECTORY);
    try {fs.fsyncSync(lockParent);} finally {fs.closeSync(lockParent);}
    releaseAllowed = true;
    const expected = {schema_version: 1, vaultOrigin: env.BW_SERVER, name: env.BW_ITEM_NAME,
      itemId: selected.itemId, principalHash: selected.principalHash, uri: selected.uri,
      uriAliasesSha256: selected.uriAliasesSha256, profile: selected.profile};
    const filename = path.join(directory, 'vault-binding.yaml');
    let fd;
    try {
      fd = fs.openSync(filename, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
      const stat = fs.fstatSync(fd);
      if (!stat.isFile() || stat.uid !== process.getuid() || (stat.mode & 0o077) || stat.nlink !== 1 || stat.size > 16384) throw new Error();
      const doc = parseDocument(fs.readFileSync(fd, 'utf8'), {uniqueKeys: true});
      if (doc.errors.length || doc.warnings.length || JSON.stringify(doc.toJS()) !== JSON.stringify(expected)) throw new Error();
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      releaseAllowed = false;
      const out = fs.openSync(filename, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_NOFOLLOW, 0o600);
      try {fs.writeFileSync(out, stringify(expected)); fs.fsyncSync(out);} finally {fs.closeSync(out);}
      const parent = fs.openSync(directory, fs.constants.O_RDONLY | fs.constants.O_DIRECTORY);
      try {fs.fsyncSync(parent);} finally {fs.closeSync(parent);}
      releaseAllowed = true;
    } finally {if (fd !== undefined) fs.closeSync(fd);}
    return expected;
  } catch {throw new Error(code);}
  finally {
    if (lock !== undefined) {
      fs.closeSync(lock);
      if (releaseAllowed) {
        try {
          const current = fs.lstatSync(lockPath);
          if (current.dev !== identity.dev || current.ino !== identity.ino) throw new Error();
          fs.unlinkSync(lockPath);
          const parent = fs.openSync(directory, fs.constants.O_RDONLY | fs.constants.O_DIRECTORY);
          try {fs.fsyncSync(parent);} finally {fs.closeSync(parent);}
        } catch {throw new Error(code);}
      }
    }
  }
}
