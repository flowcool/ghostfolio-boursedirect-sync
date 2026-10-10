#!/usr/bin/node
// Synthetic executable, never a real Bitwarden client. No network capability.
import fs from 'node:fs';
const args = process.argv.slice(2), directory = process.env.BITWARDENCLI_APPDATA_DIR;
const allowed = ['PATH','HOME','BITWARDENCLI_APPDATA_DIR','BW_CLIENTID','BW_CLIENTSECRET','BW_PASSWORD','BW_SESSION'];
if (Object.keys(process.env).some(key => !allowed.includes(key))) process.exit(1);
if (args[0] === '--version') {console.log('synthetic-1'); process.exit(0);}
const history = directory + '/calls.json';
const calls = fs.existsSync(history) ? JSON.parse(fs.readFileSync(history)) : [];
const sequence = [['config','server','https://vault.synthetic.invalid'], ['login','--apikey'],
  ['unlock','--passwordenv','BW_PASSWORD','--raw'], ['sync'], ['get','item'], ['get','totp']];
const expected = sequence[calls.length];
if (!expected || !expected.every((x,i) => args[i] === x)
    || args.length !== (calls.length >= 4 ? 3 : expected.length)) process.exit(1);
if (calls.length === 1 && (process.env.BW_CLIENTID !== 'SYNTHETIC_CLIENT' || process.env.BW_CLIENTSECRET !== 'SYNTHETIC_API')) process.exit(1);
if (calls.length === 2 && process.env.BW_PASSWORD !== 'SYNTHETIC_UNLOCK') process.exit(1);
if (calls.length >= 3 && process.env.BW_SESSION !== 'SYNTHETIC_SESSION') process.exit(1);
calls.push(args); fs.writeFileSync(history, JSON.stringify(calls), {mode: 0o600});
if (calls.length === 3) console.log('SYNTHETIC_SESSION');
if (calls.length === 5) console.log(JSON.stringify({id: args[2], type: 1, name: 'invented',
  login: {username: 'SYNTHETIC', password: 'SYNTHETIC_PASSWORD', uris: [{uri: 'https://www.boursedirect.fr/synthetic'}],
    totp: 'otpauth://totp/invented?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&algorithm=SHA1&digits=6&period=30'}}));
if (calls.length === 6) console.log('123456');
