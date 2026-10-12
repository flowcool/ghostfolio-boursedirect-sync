// One explicitly qualified lab attempt. Secrets and raw CLI output stay here.
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {privateChannel} from '../private-channel.mjs';
import {bitwardenCli, sshCliTransport} from '../bitwarden-cli.mjs';
import {vaultWorker} from '../vault-worker.mjs';
import {qualifyBrokerSource} from '../source-qualification-pilot.mjs';
import {principal} from '../core.mjs';

process.umask(0o077);
let fenced=false, child, receive, exit, browserClosed=false, sandbox=false, worker, pilot, failed=false, browserStoppedOwned=false;
const channel=privateChannel({input:process.stdin,output:process.stdout,fence:()=>{fenced=true;child?.stdin.end();process.exitCode=1;}});
let serial=Promise.resolve();
function request(value) {
  const next=serial.then(async()=>{
    if(channel.failed()||fenced&&!['retain','attest_vault','stop_vault','stop_browser'].includes(value.action))throw new Error();
    const response=channel.receive();await channel.send(value);const row=await response;
    if(channel.failed()||Object.keys(row).join(',')!=='result')throw new Error();return row.result;
  });
  serial=next.catch(()=>{fenced=true;});return next;
}
const quote=value=>"'"+value.replaceAll("'","'\\''")+"'";
try {
  const input=await channel.receive();
  if(!/^[A-Za-z0-9][A-Za-z0-9_.@-]{0,252}$/.test(input.destination)
      || !/^[a-f0-9]{64}$/.test(input.browserId)
      || !/^http:\/\/(?:[0-9]{1,3}\.){3}[0-9]{1,3}:8080$/.test(input.browserProxy))throw new Error();
  const argv=['/usr/bin/docker','exec','-i','-u','1000:1000','-w','/home/fixture',input.browserId,
    '/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME=/home/fixture','/usr/bin/node',
    '/home/fixture/proof/lab/source-browser-pipe.mjs',input.browserProxy];
  child=spawn('/usr/bin/ssh',['-T','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
    '--',input.destination,argv.map(quote).join(' ')],{env:{PATH:'/usr/bin:/bin'},stdio:['pipe','pipe','pipe']});
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
      browserStoppedOwned=await request({action:'stop_browser'})===true;return browserStoppedOwned;
    }};
  const adapter=bitwardenCli({...input.vault,
    transport:sshCliTransport(input.destination),
    attest:(containerId,pin)=>request({action:'attest_vault',containerId,pin}),
    stopOwned:containerId=>request({action:'stop_vault',containerId})});
  worker=vaultWorker({configuration:input.vault.configuration,...adapter,appdata:'/data',now:()=>Math.floor(Date.now()/1000)});
  pilot=await qualifyBrokerSource({transport,sourcePin:input.sourcePin,
    verifyBrowser:async()=>{
      const deadline=Date.now()+10000;while(!sandbox){if(fenced||Date.now()>deadline)throw new Error();await new Promise(ok=>setTimeout(ok,50));}
      return await request({action:'attest_browser'})===true;
    },
    credentials:()=>{if(input.publicOnly===true)throw new Error('SOURCE_PUBLIC_PREFLIGHT_COMPLETE');return worker.initialize(input.credentials);},
    enrollBound:async(authority,selected)=>{
      if(principal(selected.login)!==input.vault.configuration.binding.principalHash
          ||JSON.stringify(selected.accountConfig)!==JSON.stringify(input.vault.configuration.binding.accountConfig))throw new Error();
      if(await request({action:'reserve_enrollment',principal: selected.principalHash})!==true)throw new Error();
      // Explicit qualification enrollment, never an ordinary connect fallback.
      authority.enroll(selected.login);return true;
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
  await pilot.captureDocument({url:pilot.document_url,role:'frame_document',sourceSha256:input.sourcePin.app_sha256});
  let confirmed=false;
  for(let n=0;n<96;n++) {
    const next=await request({action:'next_document'});
    if(next.accounts_verified===true&&!confirmed) {
      await pilot.confirmAuthenticated({two_distinct_account_wrappers_verified:true});confirmed=true;
    }
    if(next.needs_selection===true)continue;
    if(next.done===true) {
      if(!confirmed)throw new Error();
      await pilot.close();pilot=undefined;await worker.close();const totpRequests=Number(worker.status().used);worker=undefined;
      await channel.send({action:'complete',accounts_verified:true,documents:next.documents,
        session_logged_out:true,browser_exit_verified:browserClosed||browserStoppedOwned,
        browser_pipe_exit_verified:browserClosed,browser_stopped_owned:browserStoppedOwned,totp_requests:totpRequests});break;
    }
    if(n===95)throw new Error();
    await pilot.captureDocument(next.document);
  }
} catch {
  failed=true;process.exitCode=1;
} finally {
  await pilot?.close().catch(()=>{process.exitCode=1;});
  await worker?.close().catch(()=>{process.exitCode=1;});
  if(child&&!browserClosed&&!browserStoppedOwned){child.stdin.end();await exit?.catch(()=>{});}
  if(failed)await channel.send({action:'refused',code:'SOURCE_QUALIFICATION_REFUSED'}).catch(()=>{});
  try{channel.releaseInput();}catch{process.exitCode=1;}process.stdin.destroy();
}
