// Synthetic network-none proof for the native pipe and three-phase gate.
import fs from 'node:fs';
import http from 'node:http';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {sourceNativeSession} from '../source-native-session.mjs';
import {sourceAuthenticationComposition} from '../source-authentication-gate.mjs';
import {syntheticPolicy} from '../internal/source-policy.mjs';
import {submitSourceCredentials, inspectSourceTotpSelection, submitSourceTotp} from '../source-authentication-dom.mjs';
import {inspectSourceAuthenticationResponse} from '../source-authentication-response.mjs';
import {atomicPrivate} from '../core.mjs';
const origin = 'http://127.0.0.1:48123';
let raw = ''; for await (const chunk of process.stdin) {raw += chunk; if (raw.length > 4096) throw new Error();}
const input = JSON.parse(raw);
if (!['success', 'wrong-body', 'fsync'].includes(input.scenario)) throw new Error('SYNTHETIC_RUNTIME_REFUSED');
const now = () => Math.floor(Date.now()/1000);
const policy = syntheticPolicy(origin, input.allocation);
const authority = sourceAuthenticationComposition(policy);
authority.enroll(); const handle = authority.acquirePrincipal();
const source = {schema_version: 2, origin, roles: {password: null, app_method: null, otp: null, finalize: null}};
let phase = 'password_uncertain', session, child, server, exit, pipeClosed = false, sandbox = false, gate;
const counts = {password: 0, otp: 0, finalize: 0};
let stage = 'initialize';
let outcome = {code: 'SYNTHETIC_NATIVE_QUALIFICATION_REFUSED', passed: false, online_ready: false, browser_codes: []};
const app = `<link rel=icon href="data:,"><form id=f><input type=text id=bd_auth_login_type_login><input type=password id=bd_auth_login_type_password></form><section><h6>Authentification par application (TOTP)</h6><div class="code-input react-code-input">${Array.from({length:6},(_,i)=>`<input type=number inputmode=numeric data-id=${i}>`).join('')}</div><input type=radio name=devicestate id=trusted value=trusted><input type=radio name=devicestate id=distrusted value=distrusted checked></section><script>
let credentials;function post(url,body){return new Promise((ok,no)=>{const x=new XMLHttpRequest();x.open('POST',url);x.setRequestHeader('Content-Type','application/json');x.onload=()=>ok(JSON.parse(x.responseText));x.onerror=no;x.send(JSON.stringify(body));});}
f.onsubmit=e=>{e.preventDefault();credentials={username:bd_auth_login_type_login.value,password:bd_auth_login_type_password.value,branding:'boursedirect',redirect:null};post('/hub/auth/login',credentials);};
document.querySelector('.code-input input').oninput=e=>{const code=e.target.value;post('/hub/auth/two-factor/validate-totp',{code,branding:'boursedirect',trusted_device:false}).then(()=>post('/hub/auth/login-2fa',credentials));};</script>`;
try {
  stage = 'synthetic_server';
  server = http.createServer((req,res) => {
    const url = new URL(req.url, origin);
    if (req.method === 'GET' && url.pathname === '/login') {res.setHeader('Content-Type','text/html');res.end(app);return;}
    let body = '';req.on('data',bytes=>{body+=bytes;if(body.length>4096)req.destroy();});
    req.on('end',()=>{
      res.setHeader('Content-Type','application/json');
      if (url.pathname === '/hub/auth/login') {counts.password++;res.writeHead(401);res.end('{"error":"2FA required"}');}
      else if (url.pathname === '/hub/auth/two-factor/validate-totp') {counts.otp++;res.end('{"success":true}');}
      else if (url.pathname === '/hub/auth/login-2fa') {counts.finalize++;res.end('{"redirect":"/fr/page/mes-comptes"}');}
      else {res.writeHead(403);res.end('{}');}
    });
  });
  await new Promise(resolve=>server.listen(8080,'127.0.0.1',resolve));
  child = spawn('/usr/bin/node',['/home/fixture/proof/lab/source-browser-pipe.mjs','http://127.0.0.1:8080'],
    {env:{HOME:'/home/fixture',PATH:'/usr/bin:/bin'},stdio:['pipe','pipe','pipe']});
  exit = once(child,'exit');
  let metadata='';child.stderr.on('data',bytes=>{
    metadata+=bytes;if(metadata.length>8192)throw new Error();
    while(metadata.includes('\n')){const k=metadata.indexOf('\n'),row=JSON.parse(metadata.slice(0,k));metadata=metadata.slice(k+1);
      outcome.browser_codes.push(row);
      if(row.code==='OWNED_BROWSER_RENDERER_ATTESTED')sandbox=row.renderer_sandbox_verified===true;
      if(row.code==='OWNED_BROWSER_PIPE_CLOSED')pipeClosed=row.browser_exit_verified===true;
    }
  });
  let receive;
  child.stdout.on('end',()=>{if(receive&&!pipeClosed)receive.lost();});
  let protocolBytes=0;
  child.stdout.on('data',bytes=>{protocolBytes+=bytes.length;if(protocolBytes<=1048576)fs.appendFileSync('/home/fixture/bootstrap-protocol.bytes',bytes,{mode:0o600});if(!receive)throw new Error();try{receive.receive(bytes);}catch{}});
  stage = 'native_bootstrap';
  session = await sourceNativeSession({write:bytes=>new Promise((resolve,reject)=>child.stdin.write(bytes,e=>e?reject(e):resolve())),
    installReceive:value=>{receive=value;},
    stopOwned:async()=>{child.stdin.end();const [code]=await exit;return code===0&&pipeClosed;}, closePipe:()=>child.stdout.destroy(),
    paused:async({event,binding,send})=>{
      const p=event.params;
      if(p.request.url===origin+'/login'&&p.request.method==='GET'&&p.resourceType==='Document') {
        await send('Fetch.continueRequest',{requestId:p.requestId},event.sessionId);return;
      }
      const roles={password_uncertain:['password_submit','/hub/auth/login'],otp_uncertain:['otp_submit','/hub/auth/two-factor/validate-totp'],finalization_uncertain:['password_finalize','/hub/auth/login-2fa']};
      const [role,path]=roles[phase];
      const expected=phase==='otp_uncertain'?{code:'123456',branding:'boursedirect'}:{login:'SYNTHETIC',password:'SYNTHETIC_PASSWORD',branding:'boursedirect'};
      if(input.scenario==='wrong-body')expected.password='WRONG';
      await gate.paused({phase,candidate:{role,url:origin+path,method:'POST',resourceType:'XHR',sourceSha256:'c'.repeat(64)},
        event:{requestId:p.requestId,sessionId:event.sessionId,frameId:p.frameId,resourceType:p.resourceType,
          request:{url:p.request.url,method:p.request.method,headers:p.request.headers,postData:p.request.postData}},expected,
        ...(phase==='otp_uncertain'?{otp:{issuedAt:now(),step:Math.floor(now()/30)}}:{})});
    },
    response:async({event,send})=>{
      const p=event.params;
      if(p.request.method==='POST') {
        const body=await send('Fetch.getResponseBody',{requestId:p.requestId},event.sessionId);
        const inspected=inspectSourceAuthenticationResponse(policy,{phase,status:p.responseStatusCode,...body});
        atomicPrivate(handle.directory+'/response.yaml',inspected);
        if(p.request.url.endsWith('/login')) {
          if(inspected.outcome!=='known_totp_challenge')throw new Error();authority.transition(handle,'password_accepted',now());
        } else if(p.request.url.endsWith('/validate-totp')) {
          if(inspected.outcome!=='otp_accepted')throw new Error();authority.transition(handle,'otp_accepted',now());authority.transition(handle,'finalization_uncertain',now());phase='finalization_uncertain';
        } else if(p.request.url.endsWith('/login-2fa')) {
          if(inspected.document_url!==origin+'/fr/page/mes-comptes')throw new Error();authority.transition(handle,'authenticated',now());outcome.passed=true;
        } else throw new Error();
      }
      await send('Fetch.continueResponse',{requestId:p.requestId},event.sessionId);
    }});
  stage = 'attempt';
  authority.startAttempt(handle,now(),'post-2fa-finalization');authority.transition(handle,'password_uncertain',now());
  const bound=session.binding();
  gate=authority.gate({handle,source,binding:bound,now,retain:value=>{
    if(input.scenario==='fsync')throw new Error();
    atomicPrivate(handle.directory+'/native-request.yaml',value);return true;},
    continueRequest:id=>session.send('Fetch.continueRequest',{requestId:id}),cancelAuth:()=>{throw new Error();},stop:session.stop});
  stage = 'navigation';
  await session.send('Page.navigate',{url:origin+'/login'});
  const until=Date.now()+15000;
  const processInfo = await session.browserProcesses();
  outcome.native_renderer_count = processInfo.processInfo.filter(row => row.type === 'renderer').length;
  stage = 'renderer_proof';
  while(!sandbox){if(Date.now()>until||session.fenced())throw new Error();await new Promise(resolve=>setTimeout(resolve,100));}
  stage = 'dom_readiness';
  while (!await session.evaluate(function () {return document.readyState === 'complete' && Boolean(document.querySelector('#bd_auth_login_type_login'));})) {
    if (Date.now() > until || session.fenced()) throw new Error();
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  stage = 'credential_dom';
  await session.evaluate(submitSourceCredentials,['SYNTHETIC','SYNTHETIC_PASSWORD']);
  while(counts.password<1){if(Date.now()>until||session.fenced())throw new Error();await new Promise(resolve=>setTimeout(resolve,20));}
  // Wait for the response-stage durable transition, never a network retry.
  while(JSON.parse(JSON.stringify((await import('yaml')).parse(fs.readFileSync(handle.directory+'/journal.yaml','utf8')))).attempts[handle.attempt].state!=='password_accepted') {
    if(Date.now()>until||session.fenced())throw new Error();await new Promise(resolve=>setTimeout(resolve,20));}
  await session.evaluate(inspectSourceTotpSelection,[true]);
  const selection=await session.evaluate(inspectSourceTotpSelection);
  authority.confirmLocalAppMethod(handle,source,{source_sha256:'c'.repeat(64),page_epoch:bound.pageEpoch,
    frame_epoch:Object.values(bound.frames)[0].epoch,session_id:bound.sessionId,frame_id:Object.keys(bound.frames)[0],
    method:selection.method,trusted_device:selection.trusted_device,native_dom_checked:selection.native_dom_checked},now());
  // No code fetched yet; wait to start early in a step, then use only one code.
  if(now()%30>20)await new Promise(resolve=>setTimeout(resolve,(30-now()%30)*1000+50));
  authority.transition(handle,'otp_uncertain',now());phase='otp_uncertain';
  await session.evaluate(submitSourceTotp,['123456']);
  while(!outcome.passed){if(Date.now()>until+35000||session.fenced())throw new Error();await new Promise(resolve=>setTimeout(resolve,20));}
  outcome.code='SYNTHETIC_NATIVE_QUALIFICATION_PASSED';
} catch (error) {outcome.stage = stage; if (/^(CAPABILITY|SOURCE_NATIVE|SOURCE_BROWSER|SOURCE_AUTHENTICATION)_[A-Z_]+$/.test(error?.message ?? '')) outcome.failure_code = error.message;}
finally {
  if(session)await session.close().catch(()=>{});else if(child){child.stdin.end();await exit.catch(()=>{});}
  if(server)await new Promise(resolve=>server.close(resolve));
  const journal=(await import('yaml')).parse(fs.readFileSync(handle.directory+'/journal.yaml','utf8'));
  outcome={...outcome,counts,retained_state:journal.attempts[handle.attempt]?.state??null,browser_exit_verified:pipeClosed,renderer_sandbox_verified:sandbox};
  authority.releasePrincipal(handle);
  console.log(JSON.stringify(outcome));
}
