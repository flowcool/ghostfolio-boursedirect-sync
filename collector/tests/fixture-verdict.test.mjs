import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {parse} from 'yaml';
import {fixtureVerdict} from '../lab/verdict.mjs';

const scenarios=parse(fs.readFileSync(new URL('../lab/scenarios.yaml',import.meta.url),'utf8'));
function observation(mode) {
  const c=scenarios[mode];
  const e={allowed:Array.isArray(c.allowed)?1:c.allowed,forbidden:c.forbidden,
    owned_browser_exit:true,counts:{'Target.attachedToTarget':2},
    trace:[{lifecycle:'stop-owned',fenced:true},{lifecycle:'owned-exit'},
      {lifecycle:'close-pipe',exited:true}],durableConsumes:1,restartedFenced:true,
    challenges:1,cancelled:1,fsyncFailed:true,crashed:true,lost:true,
    forceKilled:true,queuedForbidden:2,captureEvidence:{passed:true,
      activeNavigationRejected:true,identical_body:true,distinct_loaders:true,distinct_requests:true,
      native:[{requestId:'request-a',loaderId:'loader-a',browser_proven:false},
        {requestId:'request-b',loaderId:'loader-b',browser_proven:false}],
      rejectedMarkers:['wrong-account','wrong-day','wrong-role','unknown-operation'],
      rejected:['previous-commit','previous-load','missing-loader','wrong-account','wrong-day','changed-frame-epoch','unloaded']}};
  if(c.family==='fsync-failure')e.durableConsumes=0;
  e.trace.push({pause:'/forbidden',method:'POST',resource:'Document',ownedFrame:false,redirect:true},
    {pause:'/allowed',method:'POST'},{pause:'/allowed',method:'POST'},
    {event:'Target.targetCreated',type:c.family.replace('-','_')});
  return e;
}
for(const mode of Object.keys(scenarios)){
  test(`verdict accepts qualified ${mode} and rejects forbidden counter changes`,()=>{
    const e=observation(mode);
    assert.equal(fixtureVerdict(e,scenarios[mode]).passed,true);
    e.forbidden++;
    assert.ok(fixtureVerdict(e,scenarios[mode]).failures.includes('FIXTURE_FORBIDDEN_COUNT'));
  });
}
test('concurrent negative requires two allowed calls and no forbidden call',()=>{
  const e=observation('concurrent-negative');
  e.allowed=2;e.forbidden=0;
  assert.equal(fixtureVerdict(e,scenarios['concurrent-negative']).passed,true);
  for(const value of [0,1,3]){
    e.allowed=value;assert.equal(fixtureVerdict(e,scenarios['concurrent-negative']).passed,false);
  }
});
test('concurrent stop race accepts zero or one dispatch, always one durable consumption',()=>{
  const e=observation('concurrent');
  for(const value of [0,1]){e.allowed=value;assert.equal(fixtureVerdict(e,scenarios.concurrent).passed,true);}
  e.allowed=2;assert.equal(fixtureVerdict(e,scenarios.concurrent).passed,false);
  e.allowed=0;e.durableConsumes=0;assert.equal(fixtureVerdict(e,scenarios.concurrent).passed,false);
  e.durableConsumes=2;assert.equal(fixtureVerdict(e,scenarios.concurrent).passed,false);
});
for(const mode of ['worker','shared-worker','service-worker']){
  test(`${mode} accepts discovery or paused attachment but rejects missing/unpaused stimulus`,()=>{
    const e=observation(mode);e.trace=e.trace.filter(x=>!x.event);
    assert.equal(fixtureVerdict(e,scenarios[mode]).passed,false);
    e.trace.push({event:'Target.attachedToTarget',type:scenarios[mode].family.replace('-','_'),waiting:true});
    assert.equal(fixtureVerdict(e,scenarios[mode]).passed,true);
    e.trace.at(-1).waiting=false;assert.equal(fixtureVerdict(e,scenarios[mode]).passed,false);
  });
}
test('zero counters cannot mask missing pause, popup, redirect or queue stimuli',()=>{
  for(const mode of ['denied','frame','popup','redirect307','redirect308','second-auth','concurrent','pipe-loss','forced-stop']){
    const e=observation(mode);e.trace=e.trace.filter(x=>!x.pause);e.counts={};e.queuedForbidden=0;
    assert.equal(fixtureVerdict(e,scenarios[mode]).passed,false,mode);
  }
});
test('missing exit and reordered teardown cannot qualify',()=>{
  const e=observation('permitted');e.trace=e.trace.filter(x=>x.lifecycle!=='owned-exit');
  assert.equal(fixtureVerdict(e,scenarios.permitted).passed,false);
  e.trace=[{lifecycle:'close-pipe',exited:true},{lifecycle:'owned-exit'},{lifecycle:'stop-owned',fenced:true}];
  assert.equal(fixtureVerdict(e,scenarios.permitted).passed,false);
});
test('explicit failure, cancellation, restart and capture failure reject',()=>{
  for(const [mode,key,value] of [['permitted','failure','FIXTURE_STARTUP_FAILED'],
    ['permitted','owned_browser_exit',false],['http-auth','cancelled',0],
    ['browser-crash','restartedFenced',false],['browser-crash','crashed',false],
    ['fsync-failure','fsyncFailed',false],['pipe-loss','lost',false],
    ['forced-stop','forceKilled',false],['forced-stop','queuedForbidden',1],
    ['http-auth','challenges',2],
    ['capture','captureEvidence',{passed:false}]]){
    const e=observation(mode);e[key]=value;assert.equal(fixtureVerdict(e,scenarios[mode]).passed,false);
  }
});
test('capture passed flag cannot hide missing native freshness or marker evidence',()=>{
  const e=observation('capture');e.captureEvidence={passed:true};
  assert.equal(fixtureVerdict(e,scenarios.capture).passed,false);
  const stale=observation('capture');stale.captureEvidence.native[1]=stale.captureEvidence.native[0];
  assert.equal(fixtureVerdict(stale,scenarios.capture).passed,false);
});
