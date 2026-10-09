import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {randomUUID} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import * as c from '../core.mjs';
import {parse,stringify} from 'yaml';
const source={schema_version:1,origin:c.ORIGIN,roles:{password:{url:c.ORIGIN+'/synthetic-password',method:'POST',resource_type:'Document',evidence:'synthetic-only'},app_method:null,otp:{url:c.ORIGIN+'/synthetic-otp',method:'POST',resource_type:'XHR',evidence:'synthetic-only'}}};
function isolated(run){const home=fs.mkdtempSync(path.join(os.tmpdir(),'bd-auth-test-'));const old=process.env.HOME;process.env.HOME=home;try{return run(home);}finally{if(old===undefined)delete process.env.HOME;else process.env.HOME=old;fs.rmSync(home,{recursive:true,force:true});}}
function prepare(){c.enroll('SYNTHETIC');const h=c.acquirePrincipal('synthetic');c.startAttempt(h,100);c.transition(h,'password_uncertain',100);return h;}
function contract(h){return {phase:'password_uncertain',page_epoch:randomUUID(),frame_epoch:randomUUID(),url:source.roles.password.url,method:'POST',resource_type:'Document'};}
function request(p,nonce){return {...p,nonce,redirect:false};}
test('principal case-equivalence rejects whitespace and portfolio identities',()=>{
 assert.equal(c.principal('USER'),c.principal('user'));
 for(const s of [' user','user ','','å','x'.repeat(129)])assert.throws(()=>c.principal(s),/LOGIN_IDENTITY_INVALID/);
 assert.notEqual(c.principal('other'),c.principal('user'));
});
for(const url of ['http://www.boursedirect.fr/','https://user@www.boursedirect.fr/','https://www.boursedirect.fr/#x','https://www.boursedirect.fr:443/','https://www.boursedirect.fr/a/../b','https://other.invalid/','https://www.boursedirect.fr/%2e'])test('reject noncanonical broker URL '+url,()=>assert.throws(()=>c.brokerUrl(url),/BROKER_URL_INVALID/));
for(const raw of ['{"action":"login","password":"secret"}','{"action":"login","action":"close"}','{"action":"navigate","view":"orders"}','{"action":"inspect","url":"x"}','x','[]',JSON.stringify({action:'select',handle:'bad'})])test('strict command '+raw.slice(0,35),()=>assert.throws(()=>c.command(raw)));
test('command size and accepted schema',()=>{assert.throws(()=>c.command(' '.repeat(5121)),/COMMAND_TOO_LARGE/);assert.deepEqual(c.command('{"action":"login"}'),{action:'login'});});
test('enrollment is explicit, immutable and private',()=>isolated(home=>{
 assert.throws(()=>c.acquirePrincipal('SYNTHETIC'));
 const id=c.enroll('SYNTHETIC');assert.throws(()=>c.enroll('synthetic'),/AUTH_ALREADY_ENROLLED/);
 const dir=path.join(home,'.local/state/ghostfolio-boursedirect-sync/auth',id);
 assert.equal(fs.statSync(dir).mode&0o777,0o700);assert.equal(fs.statSync(path.join(dir,'journal.yaml')).mode&0o777,0o600);
 assert(!fs.readFileSync(path.join(dir,'journal.yaml'),'utf8').includes('SYNTHETIC'));
}));
test('same-principal separate process cannot acquire lock or bypass portfolio/root changes',()=>isolated(home=>{
 const h=prepare();
 // Exact owned child fixture only, temporary HOME, no real credentials.
 const child=()=>spawnSync(process.execPath,['--import',path.resolve('tests/no-network.mjs'),path.resolve('tests/principal-child.mjs')],{env:{HOME:home,PATH:'/usr/bin:/bin'},encoding:'utf8',timeout:5000});
 let result=child();assert.equal(result.status,0,result.stderr);assert.match(result.stdout,/AUTH_PRINCIPAL_LOCKED/);
 c.releasePrincipal(h);result=child();assert.match(result.stdout,/AUTH_PRINCIPAL_FENCED/);
 // Different source account IDs/output directories never enter the auth namespace.
 assert.throws(()=>{const h2=c.acquirePrincipal('synthetic');try{c.startAttempt(h2,110);}finally{c.releasePrincipal(h2);}},/AUTH_PRINCIPAL_FENCED/);
 c.enroll('OTHER');const other=c.acquirePrincipal('OTHER');c.startAttempt(other,110);c.releasePrincipal(other);
}));
test('extra request/redirect/frame changes and expiry never consume permit',()=>isolated(()=>{
 const h=prepare(),p=contract(h),nonce=c.armPermit(h,p,100,source);
 for(const changed of [{redirect:true},{nonce:randomUUID()},{frame_epoch:randomUUID()},{page_epoch:randomUUID()},{phase:'otp_uncertain'},{method:'GET'},{url:c.ORIGIN+'/other'},{resource_type:'XHR'}])assert.throws(()=>c.consumePermit(h,{...request(p,nonce),...changed},101),/AUTH_REQUEST_REJECTED/);
 assert.throws(()=>c.consumePermit(h,request(p,nonce),146),/AUTH_REQUEST_REJECTED/);
 assert.equal(c.consumePermit(h,request(p,nonce),101),true);assert.throws(()=>c.consumePermit(h,request(p,nonce),101),/AUTH_REQUEST_REJECTED/);
 c.transition(h,'password_accepted',102);c.releasePrincipal(h);
}));
test('full success closes only after both durable consumed requests',()=>isolated(()=>{
 const h=prepare(),p=contract(h),nonce=c.armPermit(h,p,100,source);c.consumePermit(h,request(p,nonce),101);c.transition(h,'password_accepted',102);c.transition(h,'otp_uncertain',103);
 const otp={...p,phase:'otp_uncertain',url:source.roles.otp.url,resource_type:'XHR'};const n=c.armPermit(h,otp,103,source);c.consumePermit(h,request(otp,n),104);c.transition(h,'authenticated',105);c.transition(h,'closed_success',106);c.releasePrincipal(h);
 const next=c.acquirePrincipal('synthetic');c.startAttempt(next,107);c.releasePrincipal(next);
}));
test('unconsumed/unknown/blocked transitions cannot declare success',()=>isolated(()=>{
 const h=prepare();assert.throws(()=>c.transition(h,'password_accepted',101),/AUTH_SUCCESS_WITHOUT_REQUEST/);assert.throws(()=>c.transition(h,'closed_success',101),/AUTH_TRANSITION_INVALID/);
 c.transition(h,'blocked',101);assert.throws(()=>c.transition(h,'password_uncertain',102));c.releasePrincipal(h);
}));
test('absent source role and arbitrary action denied before permit persistence',()=>isolated(()=>{
 const h=prepare(),p=contract(h);assert.throws(()=>c.armPermit(h,{...p,url:c.ORIGIN+'/orders'},100,source),/AUTH_SOURCE_ROLE_DISABLED/);
 assert.throws(()=>c.armPermit(h,p,100,{...source,roles:{...source.roles,password:null}}),/AUTH_SOURCE_ROLE_DISABLED/);c.releasePrincipal(h);
}));
test('publication failure prevents request callback and retains uncertain fence',()=>isolated(()=>{
 const h=prepare(),p=contract(h),nonce=c.armPermit(h,p,100,source);const filename=path.join(h.directory,'journal.yaml');const bytes=fs.readFileSync(filename);
 fs.linkSync(filename,path.join(h.directory,'alias'));
 let called=false;assert.throws(()=>{c.consumePermit(h,request(p,nonce),101);called=true;},/PRIVATE_FILE_INVALID/);assert.equal(called,false);assert.deepEqual(fs.readFileSync(filename),bytes);c.releasePrincipal(h);
}));
test('symlink ancestor or state substitution refused',()=>isolated(home=>{
 const h=prepare();c.releasePrincipal(h);const filename=path.join(h.directory,'journal.yaml');const state=parse(fs.readFileSync(filename,'utf8'));state.schema_version=true;fs.writeFileSync(filename,stringify(state));assert.throws(()=>c.acquirePrincipal('SYNTHETIC'),/AUTH_STATE_INVALID/);
 const destination=path.join(home,'outside');fs.mkdirSync(destination,{mode:0o700});const alias=path.join(home,'alias');fs.symlinkSync(destination,alias);assert.throws(()=>c.privateDirectory(alias),/PRIVATE_PATH_INVALID/);
}));
for(const [time,expected] of [[1111111109,'081804'],[1111111111,'050471'],[1234567890,'005924'],[2000000000,'279037'],[20000000000,'353130']])test('RFC6238 SHA1 six-digit vector '+time,()=>assert.equal(c.totp('GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ',time),expected));
test('OTP near rollover stale modes malformed key/time fail before submission',()=>{
 for(const env of [{},{BD_OTP:'123456',BD_OTP_ISSUED_AT:'0'},{BD_OTP:'123456',BD_OTP_ISSUED_AT:'101'},{BD_TOTP_SECRET:'bad'},{BD_TOTP_SECRET:'GEZDGNBVGY3TQOJQ',BD_OTP:'123456'}])assert.throws(()=>c.otpFromEnvironment(env,100));
 assert.throws(()=>c.otpFromEnvironment({BD_OTP:'123456',BD_OTP_ISSUED_AT:'119'},119),/OTP_NEAR_EXPIRY/);
 assert.equal(c.otpFromEnvironment({BD_OTP:'123456',BD_OTP_ISSUED_AT:'100'},100),'123456');assert.throws(()=>c.otpFromEnvironment({},NaN));
});
test('network bootstrap is active',()=>assert.throws(()=>fetch('https://example.invalid'),/TEST_NETWORK_FORBIDDEN/));

for(const secret of ['secret /private/path','ENOENT private-login','AUTH_STATE_INVALID\nsecret'])test('diagnostic redaction '+secret.split(' ')[0],()=>assert.equal(c.diagnostic(new Error(secret)).code,'ACQUISITION_FAILED'));
test('known diagnostic fixed code',()=>assert.equal(c.diagnostic(new Error('AUTH_PRINCIPAL_FENCED')).code,'AUTH_PRINCIPAL_FENCED'));
test('crash after password consumption remains fenced across new session',()=>isolated(()=>{
 const h=prepare(),p=contract(h),n=c.armPermit(h,p,100,source);c.consumePermit(h,request(p,n),101);c.releasePrincipal(h);
 const h2=c.acquirePrincipal('synthetic');try{assert.throws(()=>c.startAttempt(h2,102),/AUTH_PRINCIPAL_FENCED/);}finally{c.releasePrincipal(h2);}
}));
test('failed fsync prevents trusted continuation',()=>isolated(()=>{
 const h=prepare(),p=contract(h),n=c.armPermit(h,p,100,source),real=fs.fsyncSync;let dispatched=0;
 fs.fsyncSync=()=>{throw new Error('private filesystem details');};
 try{assert.throws(()=>{c.consumePermit(h,request(p,n),101);dispatched++;});}finally{fs.fsyncSync=real;}
 assert.equal(dispatched,0);c.releasePrincipal(h);
}));
test('unused permit is bounded, schema exact and clock cannot reverse',()=>isolated(()=>{
 const h=prepare(),p=contract(h);assert.throws(()=>c.armPermit(h,p,99,source));
 assert.throws(()=>c.armPermit(h,{...p,body:'secret'},100,source));c.releasePrincipal(h);
}));
