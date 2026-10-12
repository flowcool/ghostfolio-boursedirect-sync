// Opt-in broker qualification caller. No transport, enrollment, credential lookup
// or publication authority is inferred here; the canonical owned supervisor supplies it.
import {createHash, randomUUID} from 'node:crypto';
import {sourceNativeSession} from './source-native-session.mjs';
import {sourceAuthenticationComposition} from './source-authentication-gate.mjs';
import {sourceReadGate} from './source-read-gate.mjs';
import {publicLoginPolicy, PUBLIC_LOGIN_URL} from './public-login-policy.mjs';
import {inspectSourceAuthenticationResponse} from './source-authentication-response.mjs';
import {submitSourceCredentials, selectSourceTotpMethod, inspectSourceTotpSelection, submitSourceTotp} from './source-authentication-dom.mjs';
import {delayedOtpProvider, validateProviderCode} from './credential-provider.mjs';
import {BROKER_POLICY, requirePolicy} from './internal/source-policy.mjs';

const READS = Object.freeze({
  '/hub/auth/verify': ['preliminary_verify', 'POST', 1],
  '/hub/referential/branding/boursedirect': ['branding_config', 'GET', 1],
  '/hub/auth/two-factor/login/active-systems/boursedirect': ['two_factor_systems', 'GET', 2],
  '/hub/auth/two-factor/login/state/boursedirect': ['two_factor_state', 'GET', 1],
});
const PHASES = Object.freeze({
  '/hub/auth/login': ['password_uncertain', 'password_submit'],
  '/hub/auth/two-factor/validate-totp': ['otp_uncertain', 'otp_submit'],
  '/hub/auth/login-2fa': ['finalization_uncertain', 'password_finalize'],
});
// Retained app source derives Js from the auth Script directory. Its TOTP
// selection uses `${Js}/system-totp.png` (including the doubled slash).
const AUTH_PUBLIC_IMAGES = new Set(['/apps/auth/production//system-totp.png',
  '/apps/auth/production/system-sms.png']);
function nativeBody(value, limit = 1048576) {
  if (!value || typeof value.body !== 'string' || typeof value.base64Encoded !== 'boolean'
      || Buffer.byteLength(value.body) > limit) throw new Error();
  const raw = value.base64Encoded ? Buffer.from(value.body, 'base64') : Buffer.from(value.body);
  if (value.base64Encoded && raw.toString('base64') !== value.body) throw new Error();
  return raw;
}
function envelope(event) {
  const p = event.params;
  return {requestId:p.requestId,sessionId:event.sessionId,frameId:p.frameId,resourceType:p.resourceType,
    request:{url:p.request.url,method:p.request.method,...(p.request.method==='POST'?{headers:p.request.headers,postData:p.request.postData}:{})},
    ...(Object.hasOwn(p,'redirectedRequestId')?{redirectedRequestId:p.redirectedRequestId}:{})};
}

async function runPilot(policy, {transport, sourcePin, credentials, enrollBound, lateCode,
  retain, consumeRead, verifyBrowser, onDocument, now = () => Math.floor(Date.now()/1000)}) {
  requirePolicy(policy);
  if (!sourcePin || !/^[a-f0-9]{64}$/.test(sourcePin.app_sha256) || !Array.isArray(sourcePin.assets)
      || [credentials,enrollBound,lateCode,retain,consumeRead,verifyBrowser,onDocument,now].some(fn=>typeof fn!=='function')) throw new Error('SOURCE_QUALIFICATION_PILOT_REFUSED');
  const pins=structuredClone(sourcePin), authority=sourceAuthenticationComposition(policy);
  const synthetic=policy!==BROKER_POLICY, loginUrl=synthetic?policy.origin+'/fr/login':PUBLIC_LOGIN_URL;
  const source={schema_version:2,origin:policy.origin,roles:{password:null,app_method:null,otp:null,finalize:null}};
  let session, gate, reads, publicDecide, handle, selected, code, phase='preflight', appVerified=false,
    configVerified=false, preliminaryVerified=false, stateVerified=false, systemsVerified=false;
  const pending=new Map(), responseSeen=new Set(), budgets=new Map(), documentGrants=new Map();
  let finalDocument, fatal=false;
  const retainSafe=async value=>{if(await retain(structuredClone(value))!==true)throw new Error();};
  const stop=async()=>{fatal=true;if(session) return session.stop(); throw new Error();};
  const candidate=(role,url,method='GET',resourceType='XHR',sha=pins.app_sha256)=>({role,url,method,resourceType,sourceSha256:sha});
  async function publicRead(event,binding,send) {
    const p=event.params;
    if (!publicDecide({...p,sessionId:event.sessionId})) {
      if(phase!=='preflight'||p.request.method!=='GET'||p.resourceType==='Document')throw new Error('SOURCE_PUBLIC_RESOURCE_OUTSIDE_PREFLIGHT');
      await retainSafe({role:'public_resource_blocked',url:p.request.url,method:'GET',resource_type:p.resourceType,
        request_id:p.requestId,session_id:event.sessionId,frame_id:p.frameId,dispatch_authority:false});
      await send('Fetch.failRequest',{requestId:p.requestId,errorReason:'BlockedByClient'},event.sessionId);return;
    }
    const grant='public-'+randomUUID();
    await retainSafe({grant,role:'public_resource',url:p.request.url,method:p.request.method,resource_type:p.resourceType,
      request_id:p.requestId,session_id:event.sessionId,frame_id:p.frameId,dispatch_authority:false});
    if(await consumeRead({grant,request_id:p.requestId,page_epoch:binding.pageEpoch,
      frame_epoch:binding.frames[p.frameId].epoch})!==true)throw new Error();
    if(fatal||session.fenced())throw new Error();
    pending.set(p.requestId,{kind:'public',url:p.request.url});
    await send('Fetch.continueRequest',{requestId:p.requestId},event.sessionId);
  }
  async function paused({event,binding,send}) {
    const p=event.params,url=new URL(p.request.url);
    if (url.origin!==policy.origin) {
      if(phase!=='preflight'||p.request.method!=='GET'||p.resourceType==='Document')throw new Error('SOURCE_FOREIGN_RESOURCE_OUTSIDE_PREFLIGHT');
      await retainSafe({role:'public_resource_blocked',url:p.request.url,method:'GET',resource_type:p.resourceType,
        request_id:p.requestId,session_id:event.sessionId,frame_id:p.frameId,dispatch_authority:false});
      await send('Fetch.failRequest',{requestId:p.requestId,errorReason:'BlockedByClient'},event.sessionId);return;
    }
    if (pending.size>=256||pending.has(p.requestId))throw new Error();
    if(phase==='password_accepted'&&appVerified&&p.request.method==='GET'&&p.resourceType==='Image'
        &&AUTH_PUBLIC_IMAGES.has(url.pathname)&&!url.search&&!url.hash&&!url.username&&!url.password
        &&!Object.hasOwn(p.request,'postData')) {
      await retainSafe({role:'auth_public_image_blocked',url:p.request.url,method:'GET',resource_type:'Image',
        source_sha256:pins.app_sha256,request_id:p.requestId,dispatch_authority:false});
      await send('Fetch.failRequest',{requestId:p.requestId,errorReason:'BlockedByClient'},event.sessionId);return;
    }
    // Method selection can lazily request a font. Deny this passive GET locally;
    // it receives no read grant, network dispatch or authentication authority.
    if(phase==='password_accepted'&&appVerified&&p.request.method==='GET'&&p.resourceType==='Font'
        &&!url.search&&!url.hash&&!url.username&&!url.password&&!Object.hasOwn(p.request,'postData')) {
      await retainSafe({role:'auth_public_font_blocked',url:p.request.url,method:'GET',resource_type:'Font',
        source_sha256:pins.app_sha256,request_id:p.requestId,dispatch_authority:false});
      await send('Fetch.failRequest',{requestId:p.requestId,errorReason:'BlockedByClient'},event.sessionId);return;
    }
    const auth=PHASES[url.pathname];
    if(auth) {
      if(!appVerified||!gate||phase!==auth[0]||url.search||url.hash)throw new Error();
      pending.set(p.requestId,{kind:'authentication',phase,url:p.request.url});
      await gate.paused({phase,candidate:candidate(auth[1],p.request.url,'POST'),event:envelope(event),
        expected:phase==='otp_uncertain'?{code:code.code,branding:'boursedirect'}:{login:selected.login,password:selected.password,branding:'boursedirect'},
        ...(phase==='otp_uncertain'?{otp:code.otp}:{})});return;
    }
    const read=READS[url.pathname];
    if(read) {
      if(!appVerified||url.search||url.hash||p.request.method!==read[1])throw new Error();
      if(['two_factor_systems','two_factor_state'].includes(read[0])&&phase!=='password_accepted')throw new Error();
      const count=(budgets.get(read[0])??0)+1;if(count>read[2])throw new Error();budgets.set(read[0],count);
      const grant=read[0]+'-'+count;pending.set(p.requestId,{kind:'read',role:read[0],url:p.request.url});
      await reads.paused({candidate:candidate(read[0],p.request.url,read[1]),event:envelope(event),grant,
        expected:read[1]==='POST'?{branding:'boursedirect'}:{}});return;
    }
    if(documentGrants.has(p.request.url)) {
      const pin=documentGrants.get(p.request.url);documentGrants.delete(p.request.url);
      pending.set(p.requestId,{kind:'document',url:p.request.url,role:pin.role});
      await reads.paused({candidate:candidate(pin.role,p.request.url,pin.method,'Document',pin.sha),event:envelope(event),
        grant:'document-'+randomUUID(),expected:pin.fields??{}});return;
    }
    if(['finalized','authenticated'].includes(phase))throw new Error();
    await publicRead(event,binding,send);
  }
  async function response({event,send}) {
    const p=event.params,record=pending.get(p.requestId);
    if(!record||responseSeen.has(p.requestId))throw new Error();responseSeen.add(p.requestId);
    // Public CSS and images are not source evidence. Reading their unbounded
    // bodies can exhaust the private CDP envelope before the pinned app loads.
    const appResponse=/^https:\/\/www\.boursedirect\.fr\/apps\/auth\/production\/auth\.js\?version=[0-9]{13}$/.test(record.url);
    const body=record.kind!=='public'||synthetic&&record.url===loginUrl||appResponse
      ?await send('Fetch.getResponseBody',{requestId:p.requestId},event.sessionId):undefined;
    if(record.kind==='authentication') {
      if(record.phase!==phase)throw new Error();
      const observed=inspectSourceAuthenticationResponse(policy,{phase,status:p.responseStatusCode,...body});
      await retainSafe({role:PHASES[new URL(record.url).pathname][1],request_id:p.requestId,...observed});
      if(observed.outcome==='known_totp_challenge') {authority.transition(handle,'password_accepted',now());phase='password_accepted';}
      else if(observed.outcome==='otp_accepted') {authority.transition(handle,'otp_accepted',now());authority.transition(handle,'finalization_uncertain',now());phase='finalization_uncertain';}
      else {
        finalDocument=observed.document_url;
        // Capture source documents inertly; the frontend callback does not acquire
        // assets, child frames or unqualified destinations after finalization.
        await session.disableScripts();phase='finalized';
        documentGrants.set(finalDocument,{role:'frame_document',sha:pins.app_sha256});
      }
    } else if(record.kind==='read') {
      if(p.responseStatusCode!==200&&!(record.role==='preliminary_verify'&&[401,403].includes(p.responseStatusCode)))throw new Error();
      const value=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(nativeBody(body,65536)));
      if(record.role==='preliminary_verify') {
        if(value&&typeof value==='object'&&Object.hasOwn(value,'redirect'))throw new Error();preliminaryVerified=true;
      } else if(record.role==='branding_config') {
        if(value?.two_factor_authentication?.client!==true)throw new Error();configVerified=true;
      } else if(record.role==='two_factor_state') {
        if(value?.state!=='ACTIVATED')throw new Error();stateVerified=true;
      } else {
        if(!Array.isArray(value?.systems)||value.systems.filter(row=>row.enabled===true&&row.type==='totp').length!==1)throw new Error();systemsVerified=true;
      }
      await retainSafe({role:record.role,request_id:p.requestId,status:p.responseStatusCode,known_source_response_verified:true});
    } else if(record.kind==='document') {
      if(p.responseStatusCode!==200)throw new Error();
      const raw=nativeBody(body);
      if(await onDocument({url:record.url,role:record.role,body:raw,
        representation:'CDP response body; text is UTF8 encoded, not a wire-byte claim'})!==true)throw new Error();
      await send('Fetch.fulfillRequest',{requestId:p.requestId,responseCode:200,
        responseHeaders:[{name:'Content-Type',value:'text/html; charset=utf-8'}],body:Buffer.from('<!doctype html><title>Source captured</title>').toString('base64')},event.sessionId);
      pending.delete(p.requestId);return;
    } else {
      if(p.responseStatusCode!==200)throw new Error();
      if(synthetic && record.url===loginUrl) {
        if(createHash('sha256').update(nativeBody(body)).digest('hex')!==pins.app_sha256)throw new Error();appVerified=true;
      }
      if(appResponse) {
        if(createHash('sha256').update(nativeBody(body)).digest('hex')!==pins.app_sha256)throw new Error();appVerified=true;
      }
    }
    pending.delete(p.requestId);
    await send('Fetch.continueResponse',{requestId:p.requestId},event.sessionId);
  }
  async function waitFor(condition,timeout=15000) {
    const deadline=Date.now()+timeout;
    while(!await condition()){if(fatal||session.fenced()||Date.now()>deadline)throw new Error();await new Promise(resolve=>setTimeout(resolve,50));}
  }
  try {
    session=await sourceNativeSession({...transport,paused,response,publicPreflight:()=>phase==='preflight'});
    const bound=session.binding();
    if(synthetic) {
      let used=false;const usedAssets=new Set();
      publicDecide=value=>{
        if(value.sessionId!==bound.sessionId || value.frameId!==Object.keys(bound.frames)[0]
            ||value.request.method!=='GET'||Object.hasOwn(value,'redirectedRequestId'))return false;
        if(!used&&value.request.url===loginUrl&&value.resourceType==='Document'){used=true;return true;}
        const key=JSON.stringify([value.request.url,value.resourceType]);
        if(!used||usedAssets.has(key)||value.resourceType!=='Stylesheet'
            ||!pins.assets.some(row=>row.url===value.request.url&&row.resourceType==='Stylesheet'))return false;
        usedAssets.add(key);return true;
      };
    } else publicDecide=publicLoginPolicy({sessionId:bound.sessionId,frameId:Object.keys(bound.frames)[0]},pins.assets,true);
    reads=sourceReadGate(policy,{binding:bound,retain:async value=>{await retainSafe(value);return true;},consume:consumeRead,
      continueRequest:id=>session.send('Fetch.continueRequest',{requestId:id}),stop});
    await session.send('Page.navigate',{url:loginUrl});
    await waitFor(()=>appVerified&&configVerified&&preliminaryVerified);
    if(await verifyBrowser()!==true)throw new Error();
    await waitFor(()=>session.evaluate(function(){return document.readyState==='complete'&&Boolean(document.querySelector('#bd_auth_login_type_login'));}));
    phase='credential_delivery';
    selected=await credentials();
    if(await enrollBound(authority,selected)!==true)throw new Error();
    handle=authority.acquirePrincipal(synthetic?undefined:selected.login);authority.startAttempt(handle,now(),'post-2fa-finalization');
    authority.transition(handle,'password_uncertain',now());phase='password_uncertain';
    gate=authority.gate({handle,source,binding:bound,now,retain:async value=>{await retainSafe(value);return true;},
      continueRequest:id=>session.send('Fetch.continueRequest',{requestId:id}),cancelAuth:()=>{throw new Error();},stop});
    await session.evaluate(submitSourceCredentials,[selected.login,selected.password]);
    await waitFor(()=>phase==='password_accepted'&&stateVerified&&systemsVerified);
    await waitFor(()=>session.evaluate(function(){return document.querySelectorAll('#list-system').length===1
      || document.querySelectorAll('.code-input.react-code-input input').length===6;}));
    const method=await session.evaluate(selectSourceTotpMethod);
    await retainSafe({role:'local_totp_method_selection',code:method.code,source_sha256:pins.app_sha256});
    await waitFor(()=>session.evaluate(function(){return document.querySelectorAll('.code-input.react-code-input input').length===6&&Boolean(document.querySelector('#distrusted'));}));
    await session.evaluate(inspectSourceTotpSelection,[true]);
    const selection=await session.evaluate(inspectSourceTotpSelection);
    authority.confirmLocalAppMethod(handle,source,{source_sha256:pins.app_sha256,page_epoch:bound.pageEpoch,
      frame_epoch:Object.values(bound.frames)[0].epoch,session_id:bound.sessionId,frame_id:Object.keys(bound.frames)[0],
      method:selection.method,trusted_device:selection.trusted_device,native_dom_checked:selection.native_dom_checked},now());
    // Leave the full period for the owned remote vault attestation and CLI read.
    if(now()%30>2)await new Promise(resolve=>setTimeout(resolve,(30-now()%30)*1000+50));
    const expected={runNonce:randomUUID(),stageNonce:randomUUID()};
    const provider=delayedOtpProvider({...expected,fetchCode:request=>lateCode(request,expected),now});
    code=await provider.request(expected);
    validateProviderCode({...expected,code:code.code,startedAt:code.otp.issuedAt,completedAt:now(),profile:selected.profile},expected,now());
    authority.transition(handle,'otp_uncertain',now());phase='otp_uncertain';
    await session.evaluate(submitSourceTotp,[code.code]);
    await waitFor(()=>phase==='finalized');code=undefined;
    return Object.freeze({
      document_url:finalDocument,
      captureDocument:async({url,role,sourceSha256,method='GET',fields})=>{
        if(!['finalized','authenticated'].includes(phase)||fatal||!['frame_document','monthly_statement','contract_note'].includes(role)
            ||new URL(url).origin!==policy.origin||!/^[a-f0-9]{64}$/.test(sourceSha256))throw new Error();
        const before=session.documentReady();
        if(method==='POST') {
          if(role!=='frame_document'||url!==policy.origin+'/priv/new/releves.php'
              ||!fields||Object.keys(fields).length!==2||!/^[0-9]{1,3}$/.test(fields.nc)
              ||!/^(?:[1-9]|1[0-9]|2[01])$/.test(fields.RlvCombo))throw new Error();
          documentGrants.set(url,{role,sha:sourceSha256,method,fields});
          await session.evaluate(function(url,fields){
            if(document.location.origin!==new URL(url).origin||document.forms.length!==0)throw new Error();
            const form=document.createElement('form');form.method='POST';form.action=url;
            for(const name of ['nc','RlvCombo']){const input=document.createElement('input');input.type='hidden';input.name=name;input.value=fields[name];form.append(input);}
            document.body.append(form);form.submit();return 'SOURCE_MONTH_FORM_SUBMITTED';
          },[url,fields]);
        } else {
          if(method!=='GET'||fields!==undefined)throw new Error();
          documentGrants.set(url,{role,sha:sourceSha256,method});await session.send('Page.navigate',{url});
        }
        await waitFor(()=>!documentGrants.has(url)&&![...pending.values()].some(row=>row.url===url)
          &&session.documentReady()!==null&&session.documentReady()>before);return true;
      },
      confirmAuthenticated:async evidence=>{if(phase!=='finalized'||fatal
        ||!(evidence?.two_distinct_account_wrappers_verified===true||evidence?.configured_account_verified===true))throw new Error();authority.transition(handle,'authenticated',now());phase='authenticated';await retainSafe({authentication_verified:true});},
      close:async()=>{await session.close();authority.releasePrincipal(handle);selected=code=undefined;},
      online_ready:false});
  } catch(error) {
    await retainSafe({role:'qualification_refusal',phase,native_failure:session?.failure()??null,code:/^[A-Z_]+$/.test(error?.message??'')?error.message:'SOURCE_QUALIFICATION_PILOT_REFUSED',
      app_verified:appVerified,configuration_verified:configVerified,preliminary_verified:preliminaryVerified}).catch(()=>{});
    if(session)await session.close().catch(()=>{});
    if(handle)authority.releasePrincipal(handle);selected=code=undefined;
    throw new Error('SOURCE_QUALIFICATION_PILOT_REFUSED');
  }
}

export function qualifyBrokerSource(input) {return runPilot(BROKER_POLICY,input);}

// Internal synthetic fixture composition; no command or ENV selects the policy.
export function qualifySourceForPolicy(policy,input) {requirePolicy(policy);return runPilot(policy,input);}
