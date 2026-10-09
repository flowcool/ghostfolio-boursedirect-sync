// Loaded before collector imports. Tests cannot connect to network/browser/Docker.
import net from 'node:net';
import tls from 'node:tls';
import dns from 'node:dns';
import dgram from 'node:dgram';
import http from 'node:http';
import https from 'node:https';
import child from 'node:child_process';
import workers from 'node:worker_threads';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {syncBuiltinESMExports} from 'node:module';
const forbidden=()=>{throw new Error('TEST_NETWORK_FORBIDDEN');};
dgram.createSocket=forbidden;
for(const method of Object.keys(dns))if(/^(lookup|resolve|reverse)/.test(method)&&typeof dns[method]==='function')dns[method]=forbidden;
for(const method of Object.keys(dns.promises))if(/^(lookup|resolve|reverse)/.test(method)&&typeof dns.promises[method]==='function')dns.promises[method]=forbidden;
for(const Resolver of [dns.Resolver,dns.promises.Resolver]){
  for(let prototype=Resolver.prototype;prototype&&prototype!==Object.prototype;prototype=Object.getPrototypeOf(prototype)){
    for(const method of Object.getOwnPropertyNames(prototype))if(/^(lookup|resolve|reverse)/.test(method)&&typeof prototype[method]==='function')prototype[method]=forbidden;
  }
}
net.Socket.prototype.connect=forbidden;net.connect=forbidden;net.createConnection=forbidden;
tls.connect=forbidden;http.request=forbidden;http.get=forbidden;https.request=forbidden;https.get=forbidden;
globalThis.fetch=forbidden;globalThis.WebSocket=forbidden;
workers.Worker=function(){throw new Error('TEST_WORKER_FORBIDDEN');};
const ownedDirectory=path.dirname(fileURLToPath(import.meta.url));
const originalSpawn=child.spawnSync;
child.spawnSync=(executable,args,options)=>{
  if(executable!==process.execPath||JSON.stringify(args)!==JSON.stringify(['--import',path.join(ownedDirectory,'no-network.mjs'),path.join(ownedDirectory,'principal-child.mjs')])||options?.env?.PATH!=='/usr/bin:/bin'||!options?.env?.HOME||Object.keys(options.env).sort().join(',')!=='HOME,PATH')throw new Error('TEST_CHILD_FORBIDDEN');
  return originalSpawn(executable,args,options);
};
for(const method of ['exec','execSync','execFile','execFileSync','spawn','fork'])child[method]=()=>{throw new Error('TEST_CHILD_FORBIDDEN');};
for(const key of Object.keys(process.env))if(/^(BD_|GHOST|BEADS)/.test(key))delete process.env[key];
syncBuiltinESMExports();
