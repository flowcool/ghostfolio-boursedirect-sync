// Native CDP evidence from an owned, invented loopback document only.
import {captureExperiment, FIXTURE} from './capability-policy.mjs';

const ticket = {target:FIXTURE.target, frame:FIXTURE.frame, account:FIXTURE.account,
  day:FIXTURE.day, url:FIXTURE.document, pageEpoch:1, frameEpoch:1, role:'statement'};

function replay(evidence, identity) {
  const capture=captureExperiment();
  capture.arm(ticket); capture.request(evidence.request);
  capture.commit(evidence.commit); capture.load(evidence.load);
  return capture.capture(identity);
}

export async function proveCapture({pipe,owner,rootFrame,origin,events,setDocumentVariant}) {
  const captures=[], rejectedMarkers=[];
  for(let action=0;action<6;action++){
    const armed=captureExperiment();armed.arm(ticket);
    setDocumentVariant(action);
    const start=events.length;
    const navigation=await pipe.send('Page.navigate',{url:origin+'/document'},owner.sessionId);
    if(navigation.frameId!==rootFrame || !navigation.loaderId || navigation.errorText)throw new Error('FIXTURE_NAVIGATION_REJECTED');
    const deadline=Date.now()+5000;
    let relevant;
    while(Date.now()<deadline){
      relevant=events.slice(start).filter(event=>event.sessionId===owner.sessionId);
      if(relevant.some(event=>event.method==='Page.lifecycleEvent'&&event.params.name==='load'
        &&event.params.frameId===rootFrame&&event.params.loaderId===navigation.loaderId))break;
      await new Promise(resolve=>setTimeout(resolve,10));
    }
    const requests=relevant.filter(event=>event.method==='Network.requestWillBeSent'
      &&event.params.type==='Document'&&event.params.frameId===rootFrame);
    const commits=relevant.filter(event=>event.method==='Page.frameNavigated'&&event.params.frame.id===rootFrame);
    const loads=relevant.filter(event=>event.method==='Page.lifecycleEvent'&&event.params.name==='load'
      &&event.params.frameId===rootFrame&&event.params.loaderId===navigation.loaderId);
    if(requests.length!==1||commits.length!==1||loads.length!==1)throw new Error('FIXTURE_DOCUMENT_AMBIGUOUS');
    if(relevant.indexOf(requests[0])>=relevant.indexOf(commits[0])
      ||relevant.indexOf(commits[0])>=relevant.indexOf(loads[0]))throw new Error('FIXTURE_DOCUMENT_ORDER_REJECTED');
    const native=requests[0].params;
    const pauses=relevant.filter(event=>event.method==='Fetch.requestPaused'
      &&event.params.networkId===native.requestId&&event.params.frameId===rootFrame);
    if(pauses.length!==1||native.request.url!==origin+'/document'||native.loaderId!==navigation.loaderId
      ||commits[0].params.frame.url!==origin+'/document')throw new Error('FIXTURE_DOCUMENT_BINDING_REJECTED');
    // Fixed driver-owned expression, no user or fixture text interpolated as code.
    const before=(await pipe.send('Page.getFrameTree',{},owner.sessionId)).frameTree.frame;
    if(before.id!==rootFrame||before.loaderId!==navigation.loaderId||before.url!==origin+'/document')throw new Error('FIXTURE_ACTIVE_NAVIGATION');
    const result=await pipe.send('Runtime.evaluate',{expression:"JSON.stringify({account:document.querySelector('main')?.dataset.account,day:document.querySelector('main')?.dataset.day,role:document.querySelector('main')?.dataset.role,operation:document.querySelector('main')?.dataset.operation,body:document.body.innerHTML})",returnByValue:true},owner.sessionId);
    const after=(await pipe.send('Page.getFrameTree',{},owner.sessionId)).frameTree.frame;
    if(after.id!==rootFrame||after.loaderId!==navigation.loaderId||after.url!==origin+'/document')throw new Error('FIXTURE_ACTIVE_NAVIGATION');
    const markers=JSON.parse(result.result.value);
    const validMarkers=markers.account===ticket.account&&markers.day===ticket.day&&markers.role===ticket.role&&markers.operation==='known';
    if(action>=2){
      if(validMarkers)throw new Error('FIXTURE_BAD_MARKERS_ACCEPTED');
      rejectedMarkers.push(['wrong-account','wrong-day','wrong-role','unknown-operation'][action-2]);continue;
    }
    if(!validMarkers)throw new Error('FIXTURE_IDENTITY_REJECTED');
    // Map native handles only after exact owner/frame/URL/request correlations.
    const evidence={request:{...native,sessionId:FIXTURE.session,frameId:FIXTURE.frame,
      request:{...native.request,url:FIXTURE.document}},
      commit:{sessionId:FIXTURE.session,frame:{...commits[0].params.frame,id:FIXTURE.frame,url:FIXTURE.document}},
      load:{...loads[0].params,sessionId:FIXTURE.session,frameId:FIXTURE.frame}};
    const identity={...ticket,account:markers.account,day:markers.day};
    armed.request(evidence.request);armed.commit(evidence.commit);armed.load(evidence.load);
    const accepted=armed.capture(identity);
    captures.push({evidence,identity,accepted,body:markers.body});
    if(action===1){
      const replacement=await pipe.send('Page.navigate',{url:origin+'/root'},owner.sessionId);
      const current=(await pipe.send('Page.getFrameTree',{},owner.sessionId)).frameTree.frame;
      if(!replacement.loaderId||replacement.loaderId===accepted.loaderId
        ||current.loaderId!==replacement.loaderId||current.url!==origin+'/root')throw new Error('FIXTURE_ACTIVE_NAVIGATION_ACCEPTED');
    }
  }
  if(captures[0].accepted.loaderId===captures[1].accepted.loaderId
    ||captures[0].accepted.requestId===captures[1].accepted.requestId
    ||captures[0].body!==captures[1].body)throw new Error('FIXTURE_FRESHNESS_REJECTED');
  const rejected=[];
  function reject(name,mutate){
    const evidence=structuredClone(captures[1].evidence),identity=structuredClone(captures[1].identity);
    mutate(evidence,identity);
    try{replay(evidence,identity);}catch(error){
      if(error.message==='CAPABILITY_CAPTURE_REJECTED'){rejected.push(name);return;}
      throw error;
    }
    throw new Error('FIXTURE_STALE_ACCEPTED');
  }
  reject('previous-commit',e=>{e.commit.frame.loaderId=captures[0].accepted.loaderId;});
  reject('previous-load',e=>{e.load.loaderId=captures[0].accepted.loaderId;});
  reject('missing-loader',e=>{delete e.request.loaderId;});
  reject('wrong-account',(_,i)=>{i.account='invented-other-account';});
  reject('wrong-day',(_,i)=>{i.day='2026-09-18';});
  reject('changed-frame-epoch',(_,i)=>{i.frameEpoch=2;});
  reject('unloaded',e=>{e.load.name='DOMContentLoaded';});
  return {activeNavigationRejected:true,passed:true,identical_body:true,distinct_loaders:true,distinct_requests:true,
    rejectedMarkers,native:captures.map(c=>c.accepted),rejected,browser_proven:false};
}
