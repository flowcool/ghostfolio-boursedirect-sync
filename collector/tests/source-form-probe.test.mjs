import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {sourceFormProbe} from '../source-form-probe.mjs';
import {publicLoginPolicy, PUBLIC_LOGIN_URL} from '../public-login-policy.mjs';

function fixture() {
  const events = [], inputs = [], owner = {frameId: 'synthetic-frame', sessionId: 'synthetic-session'};
  const decide = publicLoginPolicy(owner, [], true);
  decide({requestId: 'public', ...owner, resourceType: 'Document', request: {url: PUBLIC_LOGIN_URL, method: 'GET'}});
  let submits = 0, dispatched = 0;
  const form = {requestSubmit() {
    submits++;
    if (decide({requestId: 'synthetic-post', ...owner, resourceType: 'XHR',
      request: {method: 'POST', url: 'https://www.boursedirect.fr/synthetic-password'}})) dispatched++;
  }};
  function Input() {}
  Object.defineProperty(Input.prototype, 'value', {
    get() {return this.saved ?? '';}, set(value) {this.saved = value;},
  });
  const document = {querySelectorAll(selector) {return selector.endsWith('login') ? inputs.slice(0, 1) : inputs.slice(1);}};
  for (const type of ['text', 'password']) inputs.push(Object.assign(Object.create(Input.prototype), {
    type, form, tagName: 'INPUT', ownerDocument: document, disabled: false, readOnly: false,
    dispatchEvent(event) {events.push(event.type);},
  }));
  const invoke = () => vm.runInNewContext('(' + sourceFormProbe.toString() + ')()', {
    document, HTMLInputElement: Input, Event,
  });
  return {inputs, document, form, events, invoke, submits: () => submits, dispatched: () => dispatched};
}
test('fixed dummy form action cannot dispatch a password POST under public policy', () => {
  const f = fixture(), result = f.invoke();
  assert.equal(result.code, 'SOURCE_SYNTHETIC_FORM_SUBMIT_REQUESTED');
  assert.equal(f.submits(), 1); assert.equal(f.dispatched(), 0);
  assert.deepEqual(f.inputs.map(input => input.value), ['SOURCE_PROBE_LOGIN', 'SOURCE_PROBE_NOT_A_PASSWORD']);
  assert.deepEqual(f.events, ['input', 'change', 'input', 'change']);
});
for (const [name, change] of [
  ['prefilled login', f => {f.inputs[0].value = 'PRIVATE_SYNTHETIC_SENTINEL';}],
  ['prefilled password', f => {f.inputs[1].value = 'PRIVATE_SYNTHETIC_SENTINEL';}],
  ['foreign document', f => {f.inputs[1].ownerDocument = {};}],
  ['different forms', f => {f.inputs[1].form = {};}],
  ['disabled input', f => {f.inputs[1].disabled = true;}],
  ['readonly input', f => {f.inputs[0].readOnly = true;}],
  ['missing submit method', f => {delete f.form.requestSubmit;}],
  ['wrong input type', f => {f.inputs[1].type = 'text';}],
  ['duplicate input', f => {f.inputs.push(f.inputs[1]);}],
]) test('source form probe refuses ' + name + ' before any mutation', () => {
  const f = fixture(); change(f);
  const values = f.inputs.map(input => input.value);
  assert.throws(f.invoke, /^Error: SOURCE_FORM_PROBE_REFUSED$/);
  assert.deepEqual(f.inputs.map(input => input.value), values);
  assert.equal(f.submits(), 0); assert.deepEqual(f.events, []);
});
