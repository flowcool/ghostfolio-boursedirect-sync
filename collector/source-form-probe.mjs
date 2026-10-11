// Fixed dummy values only. The caller must deny every non-public request.
export function sourceFormProbe() {
  const login = document.querySelectorAll('#bd_auth_login_type_login');
  const password = document.querySelectorAll('#bd_auth_login_type_password');
  if (login.length !== 1 || password.length !== 1) throw new Error('SOURCE_FORM_PROBE_REFUSED');
  const inputs = [login[0], password[0]], form = inputs[0].form;
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
  if (!form || form !== inputs[1].form || typeof form.requestSubmit !== 'function' || typeof setter !== 'function'
      || inputs.some(input => input.ownerDocument !== document || input.tagName !== 'INPUT'
        || input.disabled || input.readOnly || input.value !== '')
      || inputs[0].type !== 'text' || inputs[1].type !== 'password') throw new Error('SOURCE_FORM_PROBE_REFUSED');
  for (const [index, input] of inputs.entries()) {
    setter.call(input, index === 0 ? 'SOURCE_PROBE_LOGIN' : 'SOURCE_PROBE_NOT_A_PASSWORD');
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.dispatchEvent(new Event('change', {bubbles: true}));
  }
  form.requestSubmit();
  return {code: 'SOURCE_SYNTHETIC_FORM_SUBMIT_REQUESTED', fields: 2};
}
