// Only synthetic process-contention fixture; never a production command.
import * as c from '../core.mjs';
let handle;
try{handle=c.acquirePrincipal('SYNTHETIC');c.startAttempt(handle,105);}
catch(error){console.log(c.diagnostic(error).code);}
finally{if(handle)c.releasePrincipal(handle);}
