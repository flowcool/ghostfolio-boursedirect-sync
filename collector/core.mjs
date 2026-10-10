/** Offline acquisition authority helpers. No browser, HTTP or production enrollment. */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {createHash, createHmac, randomUUID} from 'node:crypto';
import {parseDocument, stringify} from 'yaml';
import {BROKER_POLICY, policyUrl, requirePolicy} from './internal/source-policy.mjs';

export const ORIGIN = 'https://www.boursedirect.fr';
const LIMIT = 1048576;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const HASH = /^[0-9a-f]{64}$/;
const STATES = new Set(['enrolled', 'password_uncertain', 'password_accepted', 'otp_uncertain', 'authenticated', 'closed_success', 'blocked']);
const PUBLIC_CODES = new Set([
  'ACQUISITION_BOUND_INVALID', 'ACQUISITION_FAILED', 'ACQUISITION_SCHEMA_INVALID',
  'AUTH_ALREADY_ENROLLED', 'AUTH_ATTEMPT_LIMIT', 'AUTH_CLOCK_REVERSED', 'AUTH_HANDLE_CLOSED',
  'AUTH_PERMIT_BLOCKED', 'AUTH_PERMIT_INVALID', 'AUTH_PRINCIPAL_FENCED', 'AUTH_PRINCIPAL_LOCKED',
  'AUTH_PUBLICATION_REJECTED', 'AUTH_REQUEST_REJECTED', 'AUTH_SOURCE_ROLE_DISABLED',
  'AUTH_STATE_INVALID', 'AUTH_STATE_TOO_LARGE', 'AUTH_SUCCESS_WITHOUT_REQUEST', 'AUTH_TRANSITION_INVALID',
  'BROKER_URL_INVALID', 'COMMAND_INVALID', 'COMMAND_TOO_LARGE', 'LOGIN_IDENTITY_INVALID',
  'OTP_INPUT_MISSING', 'OTP_MODES_CONFLICT', 'OTP_NEAR_EXPIRY', 'OTP_SECRET_INVALID', 'OTP_STALE',
  'PRIVATE_FILE_INVALID', 'PRIVATE_PATH_INVALID', 'PRIVATE_PATH_MISSING', 'PRIVATE_PERMISSIONS_INVALID',
  'SOURCE_CONTRACT_INVALID',
]);
export function fail(code) { throw new Error(code); }
function exact(value, keys, code = 'ACQUISITION_SCHEMA_INVALID') {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).sort().join('|') !== [...keys].sort().join('|')) fail(code);
}
function integer(value, min, max) { if (!Number.isSafeInteger(value) || value < min || value > max) fail('ACQUISITION_BOUND_INVALID'); }
export function principal(login) {
  if (typeof login !== 'string' || !/^[A-Za-z0-9._@-]{1,128}$/.test(login)) fail('LOGIN_IDENTITY_INVALID');
  return createHash('sha256').update('BD-AUTH-v1\n' + login.toUpperCase()).digest('hex');
}
export function brokerUrl(value) { return policyUrl(BROKER_POLICY,value); }
export function command(raw) {
  if (typeof raw !== 'string' || Buffer.byteLength(raw) > 5120) fail('COMMAND_TOO_LARGE');
  let value; try { const doc=parseDocument(raw,{uniqueKeys:true}); if(doc.errors.length||doc.warnings.length)fail('COMMAND_INVALID'); value=JSON.parse(raw); } catch { fail('COMMAND_INVALID'); }
  const shapes = {inspect:['action'], login:['action'], 'app-method':['action'], otp:['action'], close:['action'],
    navigate:['action','view'], select:['action','handle'], calendar:['action','direction'],
    open:['action','handle'], capture:['action','kind','period']};
  if (!value || typeof value.action !== 'string' || !Object.hasOwn(shapes,value.action)) fail('COMMAND_INVALID');
  exact(value, shapes[value.action], 'COMMAND_INVALID');
  if (value.action==='navigate' && !['statements','notes','history'].includes(value.view)) fail('COMMAND_INVALID');
  if (['select','open'].includes(value.action) && (typeof value.handle!=='string' || !UUID.test(value.handle))) fail('COMMAND_INVALID');
  if (value.action==='calendar' && !['previous-month','next-month','previous-year','next-year'].includes(value.direction)) fail('COMMAND_INVALID');
  if (value.action==='capture' && (!['statement','note'].includes(value.kind) || typeof value.period!=='string' || !(value.kind==='statement' ? /^\d{4}-\d{2}$/ : /^\d{4}-\d{2}-\d{2}$/).test(value.period))) fail('COMMAND_INVALID');
  return value;
}
export function privateDirectory(directory, create=false) {
  if (!path.isAbsolute(directory)) fail('PRIVATE_PATH_INVALID');
  let current=path.parse(directory).root;
  for (const part of directory.slice(current.length).split(path.sep).filter(Boolean)) {
    current=path.join(current,part);
    if (!fs.existsSync(current)) {
      if (!create) fail('PRIVATE_PATH_MISSING');
      fs.mkdirSync(current,{mode:0o700});
      const parent=fs.openSync(path.dirname(current),fs.constants.O_RDONLY|fs.constants.O_DIRECTORY);
      try{fs.fsyncSync(parent);}finally{fs.closeSync(parent);}
    }
    const info=fs.lstatSync(current);
    if (!info.isDirectory() || info.isSymbolicLink()) fail('PRIVATE_PATH_INVALID');
  }
  const info=fs.statSync(directory);
  if ((info.mode & 0o077)!==0 || info.uid!==process.getuid()) fail('PRIVATE_PERMISSIONS_INVALID');
  return directory;
}
function privateRead(filename) {
  privateDirectory(path.dirname(filename));
  let fd;
  try {
    fd=fs.openSync(filename,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW|fs.constants.O_NONBLOCK);
    const info=fs.fstatSync(fd);
    if (!info.isFile() || info.size>LIMIT || info.nlink!==1 || info.uid!==process.getuid() || (info.mode&0o077)!==0) fail('PRIVATE_FILE_INVALID');
    const raw=fs.readFileSync(fd);
    if(raw.length>LIMIT) fail('PRIVATE_FILE_INVALID');
    let decoded;try{decoded=new TextDecoder('utf-8',{fatal:true}).decode(raw);}catch{fail('AUTH_STATE_INVALID');}
    const doc=parseDocument(decoded,{uniqueKeys:true,maxAliasCount:0});
    if(doc.errors.length || doc.warnings.length) fail('AUTH_STATE_INVALID');
    return doc.toJS({maxAliasCount:0});
  } finally { if(fd!==undefined) fs.closeSync(fd); }
}
export function atomicPrivate(filename,value,{exclusive=false}={}) {
  privateDirectory(path.dirname(filename));
  const raw=Buffer.from(stringify(value)); if(raw.length>LIMIT) fail('AUTH_STATE_TOO_LARGE');
  if(fs.existsSync(filename)) {
    const info=fs.lstatSync(filename);
    if(exclusive || !info.isFile() || info.isSymbolicLink() || info.nlink!==1 || info.uid!==process.getuid() || (info.mode&0o077)!==0) fail('AUTH_PUBLICATION_REJECTED');
  }
  const temp=path.join(path.dirname(filename),'.'+randomUUID()+'.tmp');let fd;
  try {
    fd=fs.openSync(temp,fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_EXCL|fs.constants.O_NOFOLLOW,0o600);
    fs.writeFileSync(fd,raw);fs.fsyncSync(fd);fs.closeSync(fd);fd=undefined;
    if(exclusive) { fs.linkSync(temp,filename);fs.unlinkSync(temp); } else fs.renameSync(temp,filename);
    const parent=fs.openSync(path.dirname(filename),fs.constants.O_RDONLY|fs.constants.O_DIRECTORY);
    try{fs.fsyncSync(parent);}finally{fs.closeSync(parent);}
  } finally {if(fd!==undefined)fs.closeSync(fd); if(fs.existsSync(temp))fs.unlinkSync(temp);}
}
export function authorityForPolicy(policy) {
  requirePolicy(policy);
  const lab=policy!==BROKER_POLICY, handles=new WeakMap(), url=value=>policyUrl(policy,value);
  function owned(handle) {const data=handles.get(handle);if(!data)fail('AUTH_HANDLE_CLOSED');return data;}
function authRoot() { return path.join(os.homedir(),'.local','state','ghostfolio-boursedirect-sync',...(lab?['synthetic-cdp','auth']:['auth'])); }
function identity(login) {
  if(!lab)return principal(login);
  if(login!==undefined)fail('LOGIN_IDENTITY_INVALID');
  return createHash('sha256').update('BD-SYNTHETIC-CDP-v1\nSYNTHETIC-NATIVE-CDP').digest('hex');
}
function location(login) { return path.join(authRoot(),identity(login)); }
function enroll(login) {
  const root=privateDirectory(authRoot(),true), directory=location(login);
  if(fs.existsSync(directory)) fail('AUTH_ALREADY_ENROLLED');
  fs.mkdirSync(directory,{mode:0o700});
  // An interrupted enrollment leaves a directory that normal enrollment cannot erase.
  const state={schema_version:lab?2:1,principal:identity(login),installation_id:randomUUID(),attempts:{},...(lab?{policy:policy.kind,origin:policy.origin,allocation_id:policy.allocation}:{})};
  atomicPrivate(path.join(directory,'journal.yaml'),state,{exclusive:true});
  const fd=fs.openSync(root,fs.constants.O_RDONLY|fs.constants.O_DIRECTORY);try{fs.fsyncSync(fd);}finally{fs.closeSync(fd);}
  return state.principal;
}
function validPermit(p) {
  exact(p,['phase','attempt','page_epoch','frame_epoch','url','method','resource_type','nonce','deadline','consumed']);
  if(!['password_uncertain','otp_uncertain','password_accepted'].includes(p.phase) || !UUID.test(p.attempt) || !UUID.test(p.nonce) || !UUID.test(p.page_epoch) || !UUID.test(p.frame_epoch) || !['GET','POST'].includes(p.method) || !['Document','XHR','Fetch'].includes(p.resource_type) || typeof p.consumed!=='boolean') fail('AUTH_PERMIT_INVALID');
  integer(p.deadline,0,Number.MAX_SAFE_INTEGER);url(p.url);
}
function validateJournal(state,id) {
  exact(state,['schema_version','principal','installation_id','attempts',...(lab?['policy','origin','allocation_id']:[])]);
  if(lab&&(state.policy!==policy.kind||state.origin!==policy.origin||state.allocation_id!==policy.allocation))fail('AUTH_STATE_INVALID');
  if(state.schema_version!==(lab?2:1) || typeof state.principal!=='string' || !HASH.test(state.principal) || state.principal!==id || !UUID.test(state.installation_id)) fail('AUTH_STATE_INVALID');
  if(!state.attempts || typeof state.attempts!=='object' || Array.isArray(state.attempts) || Object.keys(state.attempts).length>1000) fail('AUTH_STATE_INVALID');
  for(const [key,a] of Object.entries(state.attempts)) {
    exact(a,['state','started_at','updated_at','permit']);
    if(!UUID.test(key)||!STATES.has(a.state))fail('AUTH_STATE_INVALID');
    integer(a.started_at,0,Number.MAX_SAFE_INTEGER);integer(a.updated_at,a.started_at,Number.MAX_SAFE_INTEGER);
    if(a.permit!==null){validPermit(a.permit);if(a.permit.attempt!==key||a.permit.phase!==a.state)fail('AUTH_STATE_INVALID');}
  }
  return state;
}
function acquirePrincipal(login) {
  const directory=privateDirectory(location(login));const lock=path.join(directory,'lock');
  try{fs.mkdirSync(lock,{mode:0o700});}catch{fail('AUTH_PRINCIPAL_LOCKED');}
  const parent=fs.openSync(directory,fs.constants.O_RDONLY|fs.constants.O_DIRECTORY);
  try{fs.fsyncSync(parent);}finally{fs.closeSync(parent);}
  const data={directory,lock,principal:identity(login),attempt:null,released:false};
  const handle=Object.freeze(Object.defineProperties({},Object.fromEntries(Object.keys(data).map(k=>[k,{enumerable:true,get:()=>data[k]}]))));
  handles.set(handle,data);
  try{readJournal(handle);}catch(e){releasePrincipal(handle);throw e;}
  return handle;
}
function readJournal(handle) {
  owned(handle);
  if(handle.released)fail('AUTH_HANDLE_CLOSED');
  return validateJournal(privateRead(path.join(handle.directory,'journal.yaml')),handle.principal);
}
function releasePrincipal(handle) {
  const data=owned(handle);
  if(handle.released)return;
  // Revoke authority before any release operation can fail or ownership can move.
  data.released=true;
  fs.rmdirSync(handle.lock);
  const parent=fs.openSync(handle.directory,fs.constants.O_RDONLY|fs.constants.O_DIRECTORY);
  try{fs.fsyncSync(parent);}finally{fs.closeSync(parent);}
}
function startAttempt(handle,now) {
  integer(now,0,Number.MAX_SAFE_INTEGER);const state=readJournal(handle);
  if(Object.values(state.attempts).some(a=>a.state!=='closed_success'))fail('AUTH_PRINCIPAL_FENCED');
  if(Object.keys(state.attempts).length>=1000)fail('AUTH_ATTEMPT_LIMIT');
  if(Object.values(state.attempts).some(a=>now<a.updated_at))fail('AUTH_CLOCK_REVERSED');
  const id=randomUUID();state.attempts[id]={state:'enrolled',started_at:now,updated_at:now,permit:null};
  atomicPrivate(path.join(handle.directory,'journal.yaml'),state);owned(handle).attempt=id;return id;
}
const TRANSITIONS={enrolled:['password_uncertain','blocked'],password_uncertain:['password_accepted','blocked'],password_accepted:['otp_uncertain','blocked'],otp_uncertain:['authenticated','blocked'],authenticated:['closed_success','blocked'],closed_success:[],blocked:[]};
function transition(handle,next,now) {
  const state=readJournal(handle),a=state.attempts[handle.attempt];
  if(!a||!TRANSITIONS[a.state].includes(next))fail('AUTH_TRANSITION_INVALID');
  integer(now,a.updated_at,Number.MAX_SAFE_INTEGER);
  if(['password_accepted','authenticated'].includes(next)&&(!a.permit||!a.permit.consumed))fail('AUTH_SUCCESS_WITHOUT_REQUEST');
  a.state=next;a.updated_at=now;a.permit=null;
  atomicPrivate(path.join(handle.directory,'journal.yaml'),state);return next;
}
function validateSourceContract(source) {
  exact(source,['schema_version','origin','roles']);
  if(source.schema_version!==1||source.origin!==policy.origin)fail('SOURCE_CONTRACT_INVALID');
  exact(source.roles,['password','app_method','otp']);
  for(const [role,c] of Object.entries(source.roles)){
    if(c===null)continue;
    exact(c,['url','method','resource_type','evidence']);url(c.url);
    if(!['GET','POST'].includes(c.method)||!['Document','XHR','Fetch'].includes(c.resource_type)||typeof c.evidence!=='string'||!c.evidence.trim()||c.evidence.length>1000)fail('SOURCE_CONTRACT_INVALID');
    if(role!=='app_method'&&c.method!=='POST')fail('SOURCE_CONTRACT_INVALID');
  }
  return source;
}
function evaluateRequest(source,phase,request) {
  validateSourceContract(source);exact(request,['url','method','resource_type','redirect']);
  const role={password_uncertain:'password',password_accepted:'app_method',otp_uncertain:'otp'}[phase];
  const c=role?source.roles[role]:null;
  return !!c&&request.redirect===false&&['url','method','resource_type'].every(k=>request[k]===c[k]);
}
function armPermit(handle,contract,now,source) {
  exact(contract,['phase','page_epoch','frame_epoch','url','method','resource_type']);
  if(!evaluateRequest(source,contract.phase,{url:contract.url,method:contract.method,resource_type:contract.resource_type,redirect:false}))fail('AUTH_SOURCE_ROLE_DISABLED');
  const state=readJournal(handle),a=state.attempts[handle.attempt];
  if(!a||a.state!==contract.phase||a.permit)fail('AUTH_PERMIT_BLOCKED');
  integer(now,a.updated_at,Number.MAX_SAFE_INTEGER-45);
  const permit={...contract,attempt:handle.attempt,nonce:randomUUID(),deadline:now+45,consumed:false};validPermit(permit);
  // Contract is already independently characterized by the eventual source-contract owner.
  a.permit=permit;a.updated_at=now;atomicPrivate(path.join(handle.directory,'journal.yaml'),state);return permit.nonce;
}
function consumePermit(handle,request,now) {
  exact(request,['phase','page_epoch','frame_epoch','url','method','resource_type','nonce','redirect']);
  const state=readJournal(handle),a=state.attempts[handle.attempt],p=a?.permit;
  integer(now,0,Number.MAX_SAFE_INTEGER);
  if(!p||p.consumed||p.phase!==a.state||now<a.updated_at||now>p.deadline||request.redirect!==false||['phase','page_epoch','frame_epoch','url','method','resource_type','nonce'].some(k=>request[k]!==p[k]))fail('AUTH_REQUEST_REJECTED');
  p.consumed=true;a.updated_at=now;atomicPrivate(path.join(handle.directory,'journal.yaml'),state);
  return true; // Trusted driver may continue only after this function returns.
}
  return Object.freeze({enroll,validateJournal,acquirePrincipal,releasePrincipal,startAttempt,transition,validateSourceContract,evaluateRequest,armPermit,consumePermit,
    assertHandle:handle=>{const data=owned(handle);if(data.released)fail('AUTH_HANDLE_CLOSED');return true;}});
}
const brokerAuthority=authorityForPolicy(BROKER_POLICY);
export function enroll(login) {return brokerAuthority.enroll(login);}
export function validateJournal(state,id) {return brokerAuthority.validateJournal(state,id);}
export function acquirePrincipal(login) {return brokerAuthority.acquirePrincipal(login);}
export function releasePrincipal(handle) {return brokerAuthority.releasePrincipal(handle);}
export function startAttempt(handle,now) {return brokerAuthority.startAttempt(handle,now);}
export function transition(handle,next,now) {return brokerAuthority.transition(handle,next,now);}
export function validateSourceContract(source) {return brokerAuthority.validateSourceContract(source);}
export function evaluateRequest(source,phase,request) {return brokerAuthority.evaluateRequest(source,phase,request);}
export function armPermit(handle,contract,now,source) {return brokerAuthority.armPermit(handle,contract,now,source);}
export function consumePermit(handle,request,now) {return brokerAuthority.consumePermit(handle,request,now);}
export function otpFromEnvironment(env,now) {
  integer(now,0,Number.MAX_SAFE_INTEGER);
  const remain=30-(now%30);if(remain<5)fail('OTP_NEAR_EXPIRY');
  if(env.BD_TOTP_SECRET && (env.BD_OTP||env.BD_OTP_ISSUED_AT))fail('OTP_MODES_CONFLICT');
  if(env.BD_TOTP_SECRET){
    return totp(env.BD_TOTP_SECRET,now);
  }
  if(typeof env.BD_OTP!=='string'||!/^\d{6}$/.test(env.BD_OTP)||typeof env.BD_OTP_ISSUED_AT!=='string'||!/^\d{1,12}$/.test(env.BD_OTP_ISSUED_AT))fail('OTP_INPUT_MISSING');
  const issued=Number(env.BD_OTP_ISSUED_AT);
  if(issued>now||now-issued>20||Math.floor(issued/30)!==Math.floor(now/30))fail('OTP_STALE');
  return env.BD_OTP;
}

export function diagnostic(error) {
  const code=error?.message;
  return {ok:false,code:typeof code==='string'&&PUBLIC_CODES.has(code)?code:'ACQUISITION_FAILED',import_ready:false};
}

export function totp(value,now) {
  integer(now,0,Number.MAX_SAFE_INTEGER);
  if(typeof value!=='string'||! /^[A-Z2-7]{16,128}$/.test(value))fail('OTP_SECRET_INVALID');
  let bits='';for(const c of value)bits+='ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'.indexOf(c).toString(2).padStart(5,'0');
  if(bits.slice(Math.floor(bits.length/8)*8).includes('1'))fail('OTP_SECRET_INVALID');
  const key=Buffer.from(bits.match(/.{8}/g).map(b=>parseInt(b,2)));
  const counter=Buffer.alloc(8);counter.writeBigUInt64BE(BigInt(Math.floor(now/30)));
  const digest=createHmac('sha1',key).update(counter).digest(),offset=digest[19]&15;
  return String((digest.readUInt32BE(offset)&0x7fffffff)%1000000).padStart(6,'0');
}
