// Read-only fixed evaluator subprocess. Never imports the browser-launching fixture.
import fs from 'node:fs';
import {parse} from 'yaml';
import {fixtureVerdict} from './verdict.mjs';
const scenarios=parse(fs.readFileSync(new URL('./scenarios.yaml',import.meta.url),'utf8'));
const bytes=fs.readFileSync(0);
if(bytes.length>16*1048576)throw new Error('PROOF_OBSERVATIONS_LIMIT');
const evidence=JSON.parse(bytes);
if(!Array.isArray(evidence)||evidence.length>29)throw new Error('PROOF_OBSERVATIONS_LIMIT');
for(const item of evidence){
  if(!fixtureVerdict(item,scenarios[item.mode]).passed)throw new Error('PROOF_OBSERVATIONS_REJECTED');
}
