// Exact isolated synthetic journal only. Never enroll/reset or launch anything.
import {nativeComposition} from './native-composition.mjs';
const authority = nativeComposition(process.argv[2], process.argv[3]);
let handle;
try {
  handle = authority.acquirePrincipal(); authority.startAttempt(handle, 105);
  process.exitCode = 1;
} catch (error) {
  if (error.message === 'AUTH_PRINCIPAL_FENCED') console.log('FIXTURE_RESTART_FENCED');
  else process.exitCode = 1;
} finally {if (handle) authority.releasePrincipal(handle);}
