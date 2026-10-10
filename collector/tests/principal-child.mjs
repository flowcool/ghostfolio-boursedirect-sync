// Only synthetic process-contention fixture; never a production command.
import * as c from '../core.mjs';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {nativeComposition} from '../lab/native-composition.mjs';
const fixture = path.join(os.homedir(), 'native-restart.json');
const native = fs.existsSync(fixture) ? JSON.parse(fs.readFileSync(fixture, 'utf8')) : null;
const authority = native ? nativeComposition(native.origin, native.allocation) : c;
let handle;
try{handle=authority.acquirePrincipal(...(native?[]:['SYNTHETIC']));authority.startAttempt(handle,105);}
catch(error){console.log(c.diagnostic(error).code);}
finally{if(handle)authority.releasePrincipal(handle);}
