// One public native acquisition. Broker secrets remain in this process.
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {privateChannel} from './private-channel.mjs';
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {nativeVaultSession,retainNativeBinding} from './native-vault.mjs';
import {qualifyBrokerSource} from './source-qualification-pilot.mjs';
import {principal,checkLoginState} from './core.mjs';

process.umask(0o077);
if(process.argv.length===3&&process.argv[2]==='--check-login-state') {
  try {checkLoginState();process.exit(0);}
  catch {process.exit(1);}
}
let fenced=false, child, receive, exit, browserClosed=false, sandbox=false, worker, pilot, failed=false;
const channel=privateChannel({input:process.stdin,output:process.stdout,fence:()=>{fenced=true;child?.stdin.end();process.exitCode=1;}});
let serial=Promise.resolve();
function request(value) {
  const next=serial.then(async()=>{
    if(channel.failed()||fenced&&value.action!=='retain')throw new Error();
    const response=channel.receive();await channel.send(value);const row=await response;
    if(channel.failed()||Object.keys(row).join(',')!=='result')throw new Error();return row.result;
  });
  serial=next.catch(()=>{fenced=true;});return next;
}
const vaultEnv=Object.fromEntries(Object.entries(process.env).filter(([key])=>key.startsWith('BW_')||key.startsWith('BD_')));
for(const key of Object.keys(vaultEnv))delete process.env[key];
try {
  const input=await channel.receive();
  if(Object.keys(input).join(',')!=='action'||input.action!=='connect')throw new Error();
  checkLoginState();
  const sourcePin=JSON.parse(fs.readFileSync('/opt/app/source-pin.json','utf8'));
  const accountConfig={path:'/opt/app/source-pin.json',sha256:createHash('sha256').update(fs.readFileSync('/opt/app/source-pin.json')).digest('hex')};
  const pin=JSON.parse(fs.readFileSync('/opt/app/cli-pin.json','utf8'));
  const appdata=fs.mkdtempSync('/data/session-');
  child=spawn(process.execPath,['/opt/app/lab/source-browser-pipe.mjs','http://127.0.0.1:8080'],
    {env:{PATH:'/usr/bin:/bin',HOME:'/home/fixture'},stdio:['pipe','pipe','pipe']});
  exit=once(child,'close');let control='';
  child.stderr.on('data',bytes=>{
    control+=bytes;if(control.length>8192){fenced=true;child.stdin.end();return;}
    try {
      while(control.includes('\n')) {
        const k=control.indexOf('\n'),row=JSON.parse(control.slice(0,k));control=control.slice(k+1);
        if(row.code==='OWNED_BROWSER_RENDERER_ATTESTED')sandbox=row.renderer_sandbox_verified===true&&row.chrome_version==='155.0.8059.39';
        else if(row.code==='OWNED_BROWSER_PIPE_CLOSED')browserClosed=row.browser_exit_verified===true;
        else if(row.code!=='OWNED_BROWSER_PROCESS_ATTESTED')throw new Error();
      }
    } catch {fenced=true;child.stdin.end();}
  });
  child.stdout.on('data',bytes=>{try{if(!receive)throw new Error();receive.receive(bytes);}catch{fenced=true;child.stdin.end();}});
  child.once('close',()=>{if(!browserClosed)receive?.lost();});
  const transport={write:bytes=>new Promise((ok,no)=>child.stdin.write(bytes,error=>error?no(error):ok())),
    installReceive:value=>{receive=value;},closePipe:()=>child.stdout.destroy(),
    stopOwned:async()=>{
      child.stdin.end();let timer;
      try {const [code]=await Promise.race([exit,new Promise((_,no)=>{timer=setTimeout(()=>no(new Error()),15000);})]);
        if(code===0&&browserClosed)return true;
      } catch {} finally {clearTimeout(timer);}
      return false;
    }};
  pilot=await qualifyBrokerSource({transport,sourcePin,
    verifyBrowser:async()=>{
      const deadline=Date.now()+10000;while(!sandbox){if(fenced||Date.now()>deadline)throw new Error();await new Promise(ok=>setTimeout(ok,50));}
      return true;
    },
    credentials:async()=>{
      worker=await nativeVaultSession({env:vaultEnv,pin,appdata,accountConfig,acquisition:true,
        bindIdentity:metadata=>retainNativeBinding('/state',vaultEnv,metadata)});
      return worker.selected;
    },
    enrollBound:async(authority,selected)=>{
      const id=principal(selected.login);
      if(id!==selected.principalHash||JSON.stringify(selected.accountConfig)!==JSON.stringify(accountConfig))throw new Error();
      if(await request({action:'reserve_enrollment',principal:id})!==true)throw new Error();
      const directory=path.join(process.env.HOME,'.local/state/ghostfolio-boursedirect-sync/auth',id);
      if(!fs.existsSync(directory))authority.enroll(selected.login);
      return true;
    },lateCode:(request,expected)=>worker.code(request,expected),
    retain:observation=>request({action:'retain',observation}),
    consumeRead:grant=>request({action:'consume_read',grant}),
    onDocument:async document=>{
      if(await request({action:'document_begin',url:document.url,role:document.role,representation:document.representation})!==true)throw new Error();
      for(let i=0;i<document.body.length;i+=12000) {
        if(await request({action:'document_chunk',body:document.body.subarray(i,i+12000).toString('base64')})!==true)throw new Error();
      }
      return await request({action:'document_end'})===true;
    }});
  // The same authenticated browser remains owned while the supervisor selects
  // exact GETs from captured documents. No guessed routes or fresh login.
  await pilot.captureDocument({url:pilot.document_url,role:'frame_document',sourceSha256:sourcePin.app_sha256});
  let confirmed=false;
  for(let n=0;n<320;n++) {
    const next=await request({action:'next_document'});
    if(next.accounts_verified===true&&!confirmed) {
      await pilot.confirmAuthenticated(next.configured_account_verified===true
        ? {configured_account_verified:true} : next.account_discovery_verified===true
        ? {account_discovery_verified:true} : {two_distinct_account_wrappers_verified:true});confirmed=true;
    }
    if(next.needs_selection===true)continue;
    if(next.done===true) {
      if(!confirmed)throw new Error();
      await worker.close();const totpRequests=Number(worker.status().used);worker=undefined;
      await pilot.close({session_logged_out:true});pilot=undefined;
      await channel.send({action:'complete',accounts_verified:true,documents:next.documents,
        session_logged_out:true,browser_exit_verified:browserClosed,
        browser_pipe_exit_verified:browserClosed,browser_stopped_owned:false,totp_requests:totpRequests});break;
    }
    if(n===319)throw new Error();
    await pilot.captureDocument(next.document);
  }
} catch {
  failed=true;process.exitCode=1;
} finally {
  await pilot?.close().catch(()=>{process.exitCode=1;});
  await worker?.close().catch(()=>{process.exitCode=1;});
  if(child&&!browserClosed){child.stdin.end();await exit?.catch(()=>{});}
  if(failed)await channel.send({action:'refused',code:'SOURCE_CONNECT_REFUSED'}).catch(()=>{});
  try{channel.releaseInput();}catch{process.exitCode=1;}process.stdin.destroy();
}
