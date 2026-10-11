import test from 'node:test';
import assert from 'node:assert/strict';
import {sourceNativeSession} from '../source-native-session.mjs';
async function fixture(overrides = {}) {
  let channel, stops = 0;
  const commands = [];
  const emit = value => channel.receive(Buffer.from(JSON.stringify(value)+'\0'));
  const event = (method,params,sessionId='session') => emit({method,params,sessionId});
  const session = await sourceNativeSession({
    installReceive:value=>{channel=value;}, closePipe:()=>{commands.push({method:'close'});},
    stopOwned:()=>{stops++;commands.push({method:'stop'});return true;},
    paused:()=>{},response:()=>{},...overrides,
    write:bytes=>{
      const request=JSON.parse(bytes.toString().slice(0,-1));commands.push(request);
      setImmediate(()=>{
        let result={};
        if(request.method==='Browser.getVersion')result={product:'HeadlessChrome/155.0.8059.39'};
        if(request.method==='Target.createTarget') {
          emit({method:'Target.targetCreated',params:{targetInfo:{targetId:'page',type:'page',url:'about:blank'}}});
          emit({method:'Target.attachedToTarget',params:{sessionId:'session',waitingForDebugger:true,targetInfo:{targetId:'page',type:'page',url:'about:blank'}}});
          result={targetId:'page'};
        }
        if(request.method==='Page.getFrameTree')result={frameTree:{frame:{id:'frame',url:'about:blank'}}};
        if(request.method==='Runtime.enable')event('Runtime.executionContextCreated',{context:{id:1,uniqueId:'native-unique',auxData:{isDefault:true,frameId:'frame'}}});
        if(request.method==='Runtime.evaluate')result={result:{value:'SAFE_SYNTHETIC_RESULT'}};
        emit({id:request.id,result,...(request.sessionId?{sessionId:request.sessionId}:{})});
      });
    }});
  return {session,event,emit,commands,stops:()=>stops,channel};
}
test('guards and response interception precede resume; evaluation binds the native unique realm',async()=>{
  const f=await fixture();await f.session.evaluate(function(){return 'SAFE_SYNTHETIC_RESULT';});
  const methods=f.commands.map(row=>row.method),resume=methods.indexOf('Runtime.runIfWaitingForDebugger');
  assert.ok(methods.lastIndexOf('Fetch.enable')<resume);assert.ok(methods.indexOf('Runtime.enable')<resume);
  const call=f.commands.find(row=>row.method==='Runtime.evaluate');
  assert.equal(call.params.uniqueContextId,'native-unique');assert.equal(call.sessionId,'session');
  await f.session.close();assert.equal(f.stops(),1);assert.deepEqual(f.commands.slice(-2).map(row=>row.method),['stop','close']);
});
for(const [name,method,params] of [
  ['foreign frame','Fetch.requestPaused',{requestId:'request',frameId:'other',resourceType:'XHR',request:{url:'SYNTHETIC',method:'POST'}}],
  ['request redirect','Fetch.requestPaused',{requestId:'request',frameId:'frame',redirectedRequestId:'prior',request:{url:'SYNTHETIC',method:'GET'}}],
  ['HTTP response redirect','Fetch.requestPaused',{requestId:'request',frameId:'frame',responseStatusCode:302,request:{url:'SYNTHETIC',method:'GET'}}],
  ['new frame','Page.frameAttached',{frameId:'child',parentFrameId:'frame'}],
])test(`native session fences ${name} before owner callback`,async()=>{
  let callbacks=0;const f=await fixture({paused:()=>{callbacks++;},response:()=>{callbacks++;}});
  assert.throws(()=>f.event(method,params),/CAPABILITY_EVENT_REJECTED/);
  await f.session.close();assert.equal(callbacks,0);assert.equal(f.stops(),1);
});
test('a foreign default realm fences before evaluation',async()=>{
  const f=await fixture();
  assert.throws(()=>f.event('Runtime.executionContextCreated',{context:{id:2,uniqueId:'foreign',auxData:{isDefault:true,frameId:'other'}}}),/CAPABILITY_EVENT_REJECTED/);
  await assert.rejects(f.session.evaluate(function(){return 'SAFE';}),/SOURCE_NATIVE_SESSION_FENCED/);
  await f.session.close();
});
test('HTTP authentication uses CancelAuth then verifies stop before closing the pipe',async()=>{
  const f=await fixture();f.event('Fetch.authRequired',{requestId:'challenge'});
  for(let i=0;i<10&&!f.session.fenced();i++)await new Promise(resolve=>setImmediate(resolve));
  await f.session.close();
  const cancel=f.commands.find(row=>row.method==='Fetch.continueWithAuth');
  assert.deepEqual(cancel.params,{requestId:'challenge',authChallengeResponse:{response:'CancelAuth'}});
  assert.equal(f.stops(),1);
});
