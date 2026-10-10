// Mock-only startup ownership experiment. No browser launcher or broker input.
export function bootstrapExperiment({send, registerSession, initialize, stop}) {
  if ([send, registerSession, initialize, stop].some(f => typeof f !== 'function')) throw new Error('CAPABILITY_CALLBACK_REQUIRED');
  let phase = 'idle', attachment, creation, owner, stopped;
  let resolveAttachment;
  const attached = new Promise(resolve => {resolveAttachment = resolve;});
  function abort() {
    phase = 'failed';
    if (!stopped) stopped = Promise.resolve().then(() => stop());
    resolveAttachment(null);
    return stopped;
  }
  function reject() {void abort().catch(() => {}); throw new Error('CAPABILITY_TARGET_REJECTED');}
  function event(message) {
    if (phase === 'failed') throw new Error('CAPABILITY_BOOTSTRAP_FENCED');
    if (message?.method === 'Target.targetCreated') {
      const info = message.params?.targetInfo;
      if (['browser', 'tab'].includes(info?.type) && phase !== 'creating') return;
      if (phase !== 'creating' || creation || info?.type !== 'page' || info.url !== 'about:blank'
          || info.subtype !== undefined || typeof info.targetId !== 'string' || !info.targetId) reject();
      creation = structuredClone(info);
    } else if (message?.method === 'Target.attachedToTarget') {
      const params = message.params, info = params?.targetInfo;
      if (phase !== 'creating' || attachment || params?.waitingForDebugger !== true
          || info?.type !== 'page' || info.url !== 'about:blank' || info.subtype !== undefined
          || typeof info.targetId !== 'string' || !info.targetId
          || typeof params.sessionId !== 'string' || !params.sessionId) reject();
      attachment = structuredClone(params); resolveAttachment(attachment);
    } else reject();
  }
  function check() {if (phase === 'failed') throw new Error('CAPABILITY_BOOTSTRAP_FENCED');}
  async function start() {
    if (phase !== 'idle') reject();
    phase = 'bootstrap';
    try {
      const version = await send('Browser.getVersion'); check();
      if (version?.product !== 'Chrome/148.0.7778.97') throw new Error('CAPABILITY_VERSION_REJECTED');
      await send('Target.setAutoAttach', {autoAttach: true, waitForDebuggerOnStart: true, flatten: true,
        filter: [{type: 'browser', exclude: true}, {type: 'tab', exclude: true}, {}]}); check();
      await send('Target.setDiscoverTargets', {discover: true}); check();
      phase = 'creating';
      const response = await send('Target.createTarget', {url: 'about:blank'}); check();
      const page = await attached; check();
      if (!page || !response || response.targetId !== page.targetInfo.targetId
          || (creation && creation.targetId !== response.targetId)) throw new Error('CAPABILITY_TARGET_REJECTED');
      owner = response.targetId;
      phase = 'initializing';
      registerSession(page.sessionId);
      await initialize(page.sessionId, page.waitingForDebugger, owner); check();
      phase = 'ready';
      return {targetId: owner, sessionId: page.sessionId, browser_proven: false};
    } catch {
      await abort(); throw new Error('CAPABILITY_BOOTSTRAP_FAILED');
    }
  }
  return {start, event, abort, ready: () => phase === 'ready'};
}
