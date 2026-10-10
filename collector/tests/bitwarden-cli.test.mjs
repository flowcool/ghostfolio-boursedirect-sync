import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import child from 'node:child_process';
import {syncBuiltinESMExports} from 'node:module';
import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';
import {bitwardenCli, sshCliTransport} from '../bitwarden-cli.mjs';
import {vaultWorker, providerConfiguration} from '../vault-worker.mjs';
import {principal} from '../core.mjs';
import {executePrivate} from '../private-process.mjs';
import {collectorEnvironment} from '../private-process.mjs';

const credentials = {BW_CLIENTID:'SYNTHETIC_CLIENT', BW_CLIENTSECRET:'SYNTHETIC_API', BW_PASSWORD:'SYNTHETIC_UNLOCK'};
function fixture({badHash=false,holdVersion,onVersion,named=false,inspection=false,lookupFault,egressProxy,logoutFault,statusFault}={}) {
  const calls = [], id = 'b'.repeat(64), itemId = randomUUID(); let stops = 0, allowed = true;
  const configuration = {schema_version:1, vaultOrigin:'https://vault.synthetic.invalid', binding:{itemId,name:'invented',
    uri:'https://www.boursedirect.fr/synthetic',principalHash:principal('SYNTHETIC'),accountConfig:{path:'/synthetic/account.yaml',sha256:'a'.repeat(64)}},
    cli:{path:'/usr/local/bin/bw',sha256:'c'.repeat(64),version:'synthetic-1',defaultsVerified:false}};
  const item = {id:itemId,type:1,name:'invented',login:{username:'SYNTHETIC',password:'SYNTHETIC_PASSWORD',
    uris:[{uri:configuration.binding.uri}],totp:'otpauth://totp/invented?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&algorithm=SHA1&digits=6&period=30'}};
  if(named || inspection){
    item.name='boursedirect.fr'; configuration.schema_version=inspection ? 3 : 2;
    configuration.binding=inspection ? {name:item.name} : {name:item.name,accountConfig:configuration.binding.accountConfig};
  }
  const adapter = bitwardenCli({configuration,containerId:id,egressProxy,attest:async value=>value===id && allowed,
    stopOwned:async value=>{assert.equal(value,id); stops++;}, transport:async (executable,args,env,timeout,input)=>{
      calls.push({executable,args,env,timeout,input});
      const mode=args[args.indexOf('vault-cli')+1];
      if(mode==='logout' && logoutFault)return {status:1,stdout:'',stderr:'SYNTHETIC_PRIVATE_ERROR'};
      if(mode==='version' && holdVersion){onVersion();await holdVersion;}
      const stdout=args.includes('/usr/bin/sha256sum') ? (badHash?'d'.repeat(64):configuration.cli.sha256)+'  /usr/local/bin/bw\n'
        : mode==='version' ? 'synthetic-1\n' : mode==='unlock' ? 'SYNTHETIC_SESSION\n'
        : mode==='item' ? JSON.stringify(item) : mode==='lookup' ? lookupFault ? lookupFault(item) : JSON.stringify([item])
        : mode==='totp' ? '123456\n' : '';
      if(mode==='status')return {status:0,stdout:statusFault ? JSON.stringify(statusFault)
        : JSON.stringify({status:'unauthenticated',userId:null,userEmail:null,lastSync:null}),stderr:''};
      return {status:0,stdout,stderr:''};
    }});
  const worker=vaultWorker({configuration,...adapter,appdata:'/data',now:()=>120});
  return {configuration,item,adapter,worker,calls,setAllowed:x=>{allowed=x;},stops:()=>stops};
}
test('independent vault inspection requires no importer binding and exports no broker secret',async()=>{
  const f=fixture({inspection:true}),result=await f.worker.initialize(credentials);
  assert.deepEqual(Object.keys(result).sort(),['itemId','online_ready','principalHash','profile','uri']);
  for(const secret of ['SYNTHETIC','SYNTHETIC_PASSWORD','SYNTHETIC_SESSION','GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'])
    assert.equal(JSON.stringify(result).includes(secret),false);
  assert.equal(result.uri,f.item.login.uris[0].uri);
  assert.equal(result.online_ready,false);
  assert.deepEqual(f.calls.slice(-2).map(x=>x.args[x.args.indexOf('vault-cli')+1]),['logout','status']);
  assert.equal(f.calls.slice(-2).every(x=>x.input.length===0),true);
  assert.throws(()=>collectorEnvironment(result,'/synthetic'),/PRIVATE_PROCESS_FAILED/);
  const count=f.calls.length,expected={runNonce:randomUUID(),stageNonce:randomUUID()};
  await assert.rejects(f.worker.code(expected,expected),/VAULT_WORKER_FAILED/);
  await assert.rejects(f.adapter.execute('/usr/local/bin/bw',['get','totp',f.item.id],
    {PATH:'/usr/bin:/bin',HOME:'/data',BITWARDENCLI_APPDATA_DIR:'/data',BW_SESSION:'SYNTHETIC_SESSION'}),/CLI_ADAPTER_FAILED/);
  assert.equal(f.calls.length,count);assert.equal(f.calls.some(x=>x.args.includes('totp')),false);
});
for(const fault of ['logout','locked-status','identity-retained'])test('inspection fences unverified session cleanup '+fault,async()=>{
  const f=fixture({inspection:true,logoutFault:fault==='logout',statusFault:fault==='locked-status'
    ? {status:'locked'} : fault==='identity-retained' ? {status:'unauthenticated',userId:'SYNTHETIC'} : undefined});
  await assert.rejects(f.worker.initialize(credentials),/VAULT_WORKER_FAILED/);
  const count=f.calls.length;
  await assert.rejects(f.worker.initialize(credentials),/VAULT_WORKER_FAILED/);
  assert.equal(f.calls.length,count);
  assert.equal(f.calls.some(x=>x.args.includes('totp')),false);
});
test('inspection cannot accept an account binding or relax acquisition account requirements',()=>{
  const f=fixture({inspection:true});
  assert.throws(()=>providerConfiguration({...f.configuration,binding:{...f.configuration.binding,
    accountConfig:{path:'/synthetic/account.yaml',sha256:'a'.repeat(64)}}}),/VAULT_CONFIG_INVALID/);
  assert.throws(()=>providerConfiguration({...f.configuration,schema_version:2}),/VAULT_CONFIG_INVALID/);
});
for(const [fault,lookupFault] of [
  ['ambiguous',item=>JSON.stringify([item,item])],['deleted',item=>JSON.stringify([{...item,deletedDate:'synthetic'}])],
  ['missing password',item=>{delete item.login.password;return JSON.stringify([item]);}],
  ['unbound URI',item=>{item.login.uris[0].uri='https://foreign.invalid';return JSON.stringify([item]);}],
  ['bad TOTP profile',item=>{item.login.totp+='&digits=8';return JSON.stringify([item]);}],
])test('independent inspection keeps strict item validation: '+fault,async()=>{
  const f=fixture({inspection:true,lookupFault});
  await assert.rejects(f.worker.initialize(credentials),/^Error: VAULT_WORKER_FAILED$/);
  assert.equal(f.stops(),1);assert.equal(f.calls.filter(x=>x.args.includes('lookup')).length,1);
  assert.equal(f.calls.some(x=>x.args.includes('totp')),false);
});
test('attested numeric proxy travels only in cleared CLI execution environment',async()=>{
  const f=fixture({egressProxy:'http://172.31.0.2:8080'});
  await f.worker.initialize(credentials);
  assert.equal(f.calls.length,7);
  for(const call of f.calls){
    assert.equal(call.args.includes('https_proxy=http://172.31.0.2:8080'),true);
    assert.deepEqual(call.env,{PATH:'/usr/bin:/bin'});
    assert.equal(call.args.some(x=>x.startsWith('NO_PROXY=')),false);
    for(const secret of Object.values(credentials))assert.equal(JSON.stringify(call.args).includes(secret),false);
  }
});
for(const egressProxy of ['http://proxy:8080','http://172.31.0.2:80','http://172.31.0.2:8080/',
  'http://user@172.31.0.2:8080','http://172.31.0.2:8080?bypass=yes','https://172.31.0.2:8080'])
  test('proxy endpoint rejects inherited or ambiguous routing '+egressProxy,()=>{
    assert.throws(()=>fixture({egressProxy}),/CLI_ADAPTER_INVALID/);
  });
test('authorized exact name resolves once and binds the delayed TOTP to its UUID',async()=>{
  const f=fixture({named:true}),selected=await f.worker.initialize(credentials);
  assert.equal(selected.itemId,f.item.id); assert.equal(selected.principalHash,principal('SYNTHETIC'));
  assert.equal(selected.online_ready,false); assert.equal(JSON.stringify(selected).includes('otpauth'),false);
  const lookup=f.calls.filter(x=>x.args.includes('lookup'));
  assert.equal(lookup.length,1);assert.equal(lookup[0].args.at(-1),'boursedirect.fr');
  assert.equal(f.calls.some(x=>x.args.includes('totp')),false);
  const expected={runNonce:randomUUID(),stageNonce:randomUUID()};
  assert.equal((await f.worker.code(expected,expected)).code,'123456');
  assert.equal(f.calls.at(-1).args.at(-1),f.item.id);
  await assert.rejects(f.worker.initialize(credentials),/VAULT_WORKER_FAILED/);
  await assert.rejects(f.worker.code(expected,expected),/VAULT_WORKER_FAILED/);
  assert.equal(f.calls.length,8);
});
test('named mode cannot widen the operator lookup or mix a pre-pinned identity',()=>{
  const f=fixture({named:true});
  for(const binding of [{...f.configuration.binding,name:'another'},
    {...f.configuration.binding,itemId:f.item.id}, {...f.configuration.binding,principalHash:principal('SYNTHETIC')}])
    assert.throws(()=>providerConfiguration({...f.configuration,binding}),/VAULT_CONFIG_INVALID/);
});
for(const [name,lookupFault] of [
  ['absent',()=>JSON.stringify([])],['ambiguous',item=>JSON.stringify([item,item])],
  ['wrong name',item=>JSON.stringify([{...item,name:'boursedirect.fr.other'}])],
  ['deleted',item=>JSON.stringify([{...item,deletedDate:'synthetic'}])],
  ['UUID',item=>JSON.stringify([{...item,id:'invalid'}])],
  ['URI',item=>{item.login.uris[0].uri='https://unrelated.invalid';return JSON.stringify([item]);}],
  ['profile',item=>{item.login.totp+='&digits=8';return JSON.stringify([item]);}],
  ['malformed',()=>'{bad'],
])test('named lookup refuses '+name+' before delivery or TOTP, without retry',async()=>{
  const f=fixture({named:true,lookupFault});
  await assert.rejects(f.worker.initialize(credentials),/^Error: VAULT_WORKER_FAILED$/);
  assert.equal(f.stops(),1);assert.equal(f.calls.filter(x=>x.args.includes('lookup')).length,1);
  const count=f.calls.length;
  await assert.rejects(f.worker.initialize(credentials),/VAULT_WORKER_FAILED/);
  assert.equal(f.calls.length,count);assert.equal(f.calls.some(x=>x.args.includes('totp')),false);
});
test('existing worker reaches fixed CLI through stdin with no secret Docker argv or env',async()=>{
  const f=fixture(); await f.worker.initialize(credentials);
  const expected={runNonce:randomUUID(),stageNonce:randomUUID()};
  assert.equal((await f.worker.code(expected,expected)).code,'123456');
  assert.equal(f.calls.length,8); // hash + seven fixed CLI invocations
  for(const call of f.calls){
    assert.equal(call.executable,'/usr/bin/docker'); assert.equal(call.timeout,45000);
    assert.deepEqual(call.env,{PATH:'/usr/bin:/bin'});
    assert.deepEqual(call.args.slice(0,5),['exec','-i','b'.repeat(64),'/usr/bin/env','-i']);
    for(const secret of [...Object.values(credentials),'SYNTHETIC_SESSION']) assert.equal(JSON.stringify(call.args).includes(secret),false);
    assert.equal(call.args.includes('-e'),false);
  }
  const login=f.calls.find(x=>x.args.includes('login'));
  assert.deepEqual(login.input.toString().trim().split('\n').map(x=>Buffer.from(x,'base64').toString()),
    [credentials.BW_CLIENTID,credentials.BW_CLIENTSECRET]);
  await assert.rejects(f.worker.code(expected,expected),/VAULT_WORKER_FAILED/);
  assert.equal(f.calls.length,8);
});
test('missing runtime attestation prevents even executable inspection and fences once',async()=>{
  const f=fixture(); f.setAllowed(false);
  await assert.rejects(f.worker.initialize(credentials),/VAULT_WORKER_FAILED/);
  assert.equal(f.calls.length,0); assert.equal(f.stops(),1);
  await assert.rejects(f.adapter.execute('/usr/local/bin/bw',['--version'],{}),/CLI_ADAPTER_FAILED/);
  assert.equal(f.stops(),1);
});
test('changed CLI executable hash refuses before any credential command',async()=>{
  const f=fixture({badHash:true});
  await assert.rejects(f.worker.initialize(credentials),/VAULT_WORKER_FAILED/);
  assert.equal(f.calls.length,1); assert.equal(f.stops(),1);
  assert.equal(f.calls[0].input.length,0);
});
test('concurrent invocation fences the held result and cannot advance the fixed sequence',async()=>{
  let release,entered;
  const holdVersion=new Promise(resolve=>{release=resolve;}), ready=new Promise(resolve=>{entered=resolve;});
  const f=fixture({holdVersion,onVersion:entered}); await f.adapter.verifyExecutable(f.configuration.cli);
  const env={PATH:'/usr/bin:/bin',HOME:'/data',BITWARDENCLI_APPDATA_DIR:'/data'};
  const first=assert.rejects(f.adapter.execute('/usr/local/bin/bw',['--version'],env),/CLI_ADAPTER_FAILED/);
  await ready;
  await assert.rejects(f.adapter.execute('/usr/local/bin/bw',['config','server',f.configuration.vaultOrigin],env),/CLI_ADAPTER_FAILED/);
  release(); await first;
  assert.equal(f.calls.length,2); assert.equal(f.stops(),1);
});
test('wrong command or inherited environment consumes adapter without transport',async()=>{
  for(const wrong of ['command','environment']){
    const f=fixture(); await f.adapter.verifyExecutable(f.configuration.cli);
    await assert.rejects(f.adapter.execute('/usr/local/bin/bw',wrong==='command'?['list','items']:['--version'],
      {PATH:'/usr/bin:/bin',HOME:'/data',BITWARDENCLI_APPDATA_DIR:'/data',...(wrong==='environment'?{BW_PASSWORD:'SYNTHETIC_UNLOCK'}:{})}),/CLI_ADAPTER_FAILED/);
    assert.equal(f.calls.length,1); assert.equal(f.stops(),1);
  }
});
test('private process writes bounded stdin and handles pipe failure without leaking errors',async t=>{
  const original=child.spawn, calls=[]; let badPipe=false;
  child.spawn=(executable,args,options)=>{
    const process=new EventEmitter();
    process.stdin=new PassThrough(); process.stdout=new PassThrough(); process.stderr=new PassThrough();
    const input=[]; process.stdin.on('data',bytes=>input.push(bytes));
    calls.push({executable,args,options,input});
    setImmediate(()=>{
      if(badPipe) process.stdin.emit('error',new Error('SYNTHETIC_PRIVATE_ERROR'));
      else process.stdout.write('accepted');
      process.emit('close',0);
    });
    return process;
  };
  syncBuiltinESMExports();
  t.after(()=>{child.spawn=original;syncBuiltinESMExports();});
  const result=await executePrivate('/synthetic/executable',['fixed'],{PATH:'/usr/bin:/bin'},100,Buffer.from('SYNTHETIC_API'));
  assert.equal(result.stdout,'accepted'); assert.equal(calls[0].options.stdio[0],'pipe');
  assert.equal(Buffer.concat(calls[0].input).toString(),'SYNTHETIC_API');
  assert.equal(JSON.stringify(calls[0].args).includes('SYNTHETIC_API'),false);
  assert.equal((await executePrivate('/synthetic/executable',['fixed'],{},100)).stdout,'accepted');
  assert.equal(calls[1].options.stdio[0],'ignore');
  badPipe=true;
  await assert.rejects(executePrivate('/synthetic/executable',['fixed'],{},100,Buffer.from('SYNTHETIC_API')), /^Error: PRIVATE_PROCESS_FAILED$/);
  const count=calls.length;
  await assert.rejects(executePrivate('/synthetic/executable',['fixed'],{},100,Buffer.alloc(32769)), /PRIVATE_PROCESS_FAILED/);
  assert.equal(calls.length,count);
});
test('SSH transport preserves argument boundaries while keeping credential bytes on stdin',async()=>{
  let seen;
  const transport=sshCliTransport('owned-host',async (...args)=>{seen=args;return {status:0,stdout:'',stderr:''};});
  const input=Buffer.from('SYNTHETIC_API');
  await transport('/usr/bin/docker',['exec','-i','b'.repeat(64),'/bin/sh','-c',"printf '%s' 'fixed'"],{PATH:'/usr/bin:/bin'},45000,input);
  assert.equal(seen[0],'/usr/bin/ssh'); assert.equal(seen[1].includes('StrictHostKeyChecking=yes'),true);
  assert.equal(seen[1].at(-2),'owned-host'); assert.equal(seen[1].at(-1).includes("'\\''"),true);
  assert.equal(JSON.stringify(seen[1]).includes('SYNTHETIC_API'),false); assert.equal(seen[4],input);
  assert.throws(()=>sshCliTransport('-oProxyCommand=unsafe'),/CLI_ADAPTER_INVALID/);
});
