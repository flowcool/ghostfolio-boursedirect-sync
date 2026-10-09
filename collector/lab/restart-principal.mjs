// Fresh process reads only the fixture's own journal; never starts a browser.
import * as core from './core.mjs';
let handle;
try {
  handle = core.acquirePrincipal('SYNTHETIC-CAPABILITY');
  core.startAttempt(handle, 102);
  process.exitCode = 1;
} catch (error) {
  if (error.message === 'AUTH_PRINCIPAL_FENCED') console.log('FIXTURE_RESTART_FENCED');
  else process.exitCode = 1;
} finally {
  if (handle) core.releasePrincipal(handle);
}
