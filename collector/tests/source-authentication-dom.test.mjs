import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {submitSourceCredentials, selectSourceTotpMethod, inspectSourceTotpSelection, submitSourceTotp} from '../source-authentication-dom.mjs';
import {validateSourceBrowserRuntime} from '../lab/source-browser-pipe.mjs';

function fixture() {
  const actions = [];
  class Input {
    constructor(type, id = '') {this.type = type; this.tagName = 'INPUT'; this.dataset = {id}; this.inputMode = 'numeric'; this.disabled = false; this.readOnly = false; this._value = '';}
    get value() {return this._value;} set value(value) {this._value = value; actions.push('set');}
    dispatchEvent(event) {actions.push(event.type);}
    click() {this.checked = true; actions.push('distrusted');}
  }
  const login = new Input('text'), password = new Input('password');
  const digits = Array.from({length: 6}, (_, i) => new Input('number', String(i)));
  const distrust = new Input('radio'), trust = new Input('radio');
  distrust._value = 'distrusted'; trust._value = 'trusted'; distrust.name = trust.name = 'devicestate';
  distrust.checked = true; trust.checked = false;
  const form = {requestSubmit() {actions.push('submit');}}; login.form = password.form = form;
  const group = {querySelectorAll: () => digits};
  const section = {querySelectorAll(selector) {return selector === '.code-input.react-code-input' ? [group] : selector === '#distrusted' ? [distrust] : selector === '#trusted' ? [trust] : [];}};
  const heading = {textContent: 'Authentification par application (TOTP)', closest: () => section};
  const document = {querySelectorAll(selector) {return selector === 'h6' ? [heading]
    : selector === '#bd_auth_login_type_login' ? [login] : selector === '#bd_auth_login_type_password' ? [password] : [];}};
  for (const input of [login, password, ...digits, distrust, trust, heading]) input.ownerDocument = document;
  const context = vm.createContext({document, HTMLInputElement: Input, Event: class {constructor(type) {this.type = type;}}});
  return {actions, login, password, digits, distrust, trust, document, context,
    run(fn, args = []) {return vm.runInContext('(' + fn.toString() + ')(...' + JSON.stringify(args) + ')', context);}};
}

test('fixed login action fills only bound blank controls and submits once without returning values', () => {
  const f = fixture(), result = f.run(submitSourceCredentials, ['SYNTHETIC', 'SYNTHETIC_PASSWORD']);
  assert.equal(result.code, 'SOURCE_CREDENTIAL_SUBMIT_REQUESTED'); assert.equal(f.actions.filter(x => x === 'submit').length, 1);
  assert.equal(JSON.stringify(result).includes('SYNTHETIC'), false);
});
for (const [name, mutate] of [
  ['prefill', f => {f.login._value = 'OTHER';}],
  ['disabled', f => {f.password.disabled = true;}],
  ['foreign owner', f => {f.login.ownerDocument = {};}],
  ['foreign form', f => {f.password.form = {};}],
]) test(`login refuses ${name} before any action`, () => {
  const f = fixture(); mutate(f); assert.throws(() => f.run(submitSourceCredentials, ['SYNTHETIC', 'SYNTHETIC_PASSWORD']), /SOURCE_AUTHENTICATION_DOM_REFUSED/);
  assert.deepEqual(f.actions, []);
});
test('local TOTP inspection binds six empty source controls and distrust without submitting', () => {
  const f = fixture(); const result = f.run(inspectSourceTotpSelection);
  assert.equal(result.native_dom_checked, true); assert.equal(result.trusted_device, false); assert.deepEqual(f.actions, []);
  f.run(inspectSourceTotpSelection, [true]); assert.deepEqual(f.actions, ['distrusted']);
});
function methodFixture() {
  const f=fixture();
  const image={ownerDocument:f.document,title:'TOTP',alt:'TOTP'};
  const list={ownerDocument:f.document,querySelectorAll:()=>[anchor]};
  const anchor={ownerDocument:f.document,tagName:'A',querySelectorAll:()=>[image],
    getAttribute:()=> 'javascript:void(0)',closest:()=>list,click:()=>f.actions.push('select-totp')};
  const query=f.document.querySelectorAll;
  f.document.querySelectorAll=selector=>selector==='#list-system'?[list]:query(selector);
  return {...f,list,anchor,image};
}
test('source method list selects the unique local TOTP choice once without submitting',()=>{
  const f=methodFixture();assert.equal(f.run(selectSourceTotpMethod).code,'SOURCE_TOTP_METHOD_SELECTED');
  assert.deepEqual(f.actions,['select-totp']);
});
for(const mutate of [f=>{f.list.querySelectorAll=()=>[f.anchor,f.anchor];},
  f=>{f.image.alt='SMS';},f=>{f.anchor.ownerDocument={};},f=>{f.anchor.getAttribute=()=>'/unqualified';}])
test('method selection refuses ambiguous or unqualified controls before clicking',()=>{
  const f=methodFixture();mutate(f);assert.throws(()=>f.run(selectSourceTotpMethod),/SOURCE_AUTHENTICATION_DOM_REFUSED/);
  assert.deepEqual(f.actions,[]);
});
test('already displayed TOTP form needs no method click',()=>{
  const f=fixture();assert.equal(f.run(selectSourceTotpMethod).code,'SOURCE_TOTP_METHOD_ALREADY_SELECTED');
  assert.deepEqual(f.actions,[]);
});
test('single multi-character TOTP input does not click or submit the form again', () => {
  const f = fixture(); const result = f.run(submitSourceTotp, ['123456']);
  assert.deepEqual(f.actions, ['set', 'input']); assert.equal(result.code, 'SOURCE_TOTP_SUBMIT_REQUESTED');
  assert.equal(JSON.stringify(result).includes('123456'), false);
});
for (const [name, mutate] of [
  ['trusted device', f => {f.trust.checked = true;}],
  ['missing distrust', f => {f.distrust.checked = false;}],
  ['prefilled code', f => {f.digits[1]._value = '9';}],
  ['foreign code input', f => {f.digits[2].ownerDocument = {};}],
  ['wrong code order', f => {f.digits[2].dataset.id = '4';}],
]) test(`TOTP refuses ${name} before code fill`, () => {
  const f = fixture(); mutate(f);
  assert.throws(() => f.run(inspectSourceTotpSelection), /SOURCE_AUTHENTICATION_DOM_REFUSED/);
  assert.throws(() => f.run(submitSourceTotp, ['123456']), /SOURCE_AUTHENTICATION_DOM_REFUSED/);
  assert.deepEqual(f.actions, []);
});
test('browser runtime refuses alternate users, inherited secrets and nonnumeric proxies before spawn', () => {
  const env = {HOME: '/home/fixture', PATH: '/usr/bin:/bin'};
  assert.equal(validateSourceBrowserRuntime('http://10.1.2.3:8080', env, 1000), 'http://10.1.2.3:8080');
  for (const [proxy, values, uid] of [['http://host:8080', env, 1000], ['http://10.1.2.3:8080', env, 0],
    ['http://10.1.2.3:8080', {...env, BD_PASSWORD: 'SYNTHETIC_PASSWORD'}, 1000], ['http://300.1.2.3:8080', env, 1000]])
    assert.throws(() => validateSourceBrowserRuntime(proxy, values, uid), /SOURCE_BROWSER_RUNTIME_REFUSED/);
});
