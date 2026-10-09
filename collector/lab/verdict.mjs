// Pure evaluator for invented fixture observations; no browser or filesystem IO.
export function fixtureVerdict(e, contract) {
  const failures=[];
  const check=(condition,code)=>{if(!condition)failures.push(code);};
  if(!e||!contract)return {passed:false,failures:['FIXTURE_MODE_REJECTED'],signal:false};
  const allowed=Array.isArray(contract.allowed)?contract.allowed:[contract.allowed];
  check(!e.failure,'FIXTURE_EXECUTION_FAILED');
  check(Number.isInteger(e.allowed)&&allowed.includes(e.allowed),'FIXTURE_ALLOWED_COUNT');
  check(e.forbidden===contract.forbidden,'FIXTURE_FORBIDDEN_COUNT');
  check(e.owned_browser_exit===true,'FIXTURE_EXIT_UNVERIFIED');
  const trace=e.trace??[], pauses=trace.filter(item=>item.pause), counts=e.counts??{};
  const exit=trace.findIndex(item=>item.lifecycle==='owned-exit');
  const close=trace.findIndex(item=>item.lifecycle==='close-pipe');
  check(trace.some(item=>item.lifecycle==='stop-owned'&&item.fenced===true)
    &&exit>=0&&close>exit&&trace[close].exited===true,'FIXTURE_TEARDOWN_ORDER');
  let signal=true;
  const scenario=contract.family;
  if(scenario==='popup')signal=(counts['Target.attachedToTarget']??0)>=2;
  else if(!contract.negative){
    if(['worker','shared-worker','service-worker'].includes(scenario))signal=trace.some(item=>
      ['Target.targetCreated','Target.attachedToTarget'].includes(item.event)
      &&item.type===scenario.replace('-','_')&&(item.event==='Target.targetCreated'||item.waiting===true));
    else if(scenario==='frame')signal=pauses.some(item=>item.pause==='/forbidden'
      &&item.method==='POST'&&item.resource==='Document'&&item.ownedFrame===false);
    else if(scenario.startsWith('redirect'))signal=pauses.some(item=>item.pause==='/forbidden'&&item.redirect===true);
    else if(['second-auth','concurrent'].includes(scenario))signal=pauses.filter(item=>item.pause==='/allowed'&&item.method==='POST').length===2;
    else if(['denied','pipe-loss','forced-stop'].includes(scenario))signal=pauses.some(item=>item.pause==='/forbidden'&&item.method==='POST');
  }
  check(signal,'FIXTURE_STIMULUS_MISSING');
  if(contract.durable)check(e.restartedFenced===true
    &&e.durableConsumes===(scenario==='fsync-failure'?0:1),'FIXTURE_DURABLE_AUTHORITY');
  if(scenario==='http-auth')check(e.challenges===1&&e.cancelled===1,'FIXTURE_AUTH_CANCELLATION');
  if(scenario==='fsync-failure')check(e.fsyncFailed===true,'FIXTURE_FSYNC_NOT_EXERCISED');
  if(scenario==='browser-crash')check(e.crashed===true,'FIXTURE_CRASH_NOT_EXERCISED');
  if(scenario==='pipe-loss')check(e.lost===true&&e.queuedForbidden===2,'FIXTURE_PIPE_LOSS_NOT_EXERCISED');
  if(scenario==='forced-stop')check(e.forceKilled===true&&e.queuedForbidden===2,'FIXTURE_FORCE_STOP_NOT_EXERCISED');
  if(scenario==='capture'){
    const capture=e.captureEvidence;
    const native=capture?.native;
    check(capture?.passed===true&&capture.activeNavigationRejected===true
      &&capture.identical_body===true&&capture.distinct_loaders===true&&capture.distinct_requests===true
      &&Array.isArray(native)&&native.length===2
      &&native.every(item=>typeof item.requestId==='string'&&item.requestId
        &&typeof item.loaderId==='string'&&item.loaderId&&item.browser_proven===false)
      &&native[0].requestId!==native[1].requestId&&native[0].loaderId!==native[1].loaderId
      &&['wrong-account','wrong-day','wrong-role','unknown-operation'].every(code=>capture.rejectedMarkers?.includes(code))
      &&['previous-commit','previous-load','missing-loader','wrong-account','wrong-day','changed-frame-epoch','unloaded']
        .every(code=>capture.rejected?.includes(code)), 'FIXTURE_CAPTURE_REJECTED');
  }
  return {passed:failures.length===0,failures,signal};
}
