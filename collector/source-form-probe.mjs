// Fixed dummy values only. The caller must deny every non-public request.
// The caller records metadata first; retain the reason even if parsing refuses.
export function observeBlockedFormEnvelope(row, request) {
  try {return blockedFormEnvelope(request);}
  catch {
    row.envelope_refusal_code = 'SOURCE_FORM_ENVELOPE_REFUSED';
    throw new Error('SOURCE_FORM_ENVELOPE_REFUSED');
  }
}

export function verifyBlockedFormProbe(rows, owner) {
  const matched = rows.some(row => {
    if (row.method !== 'POST' || row.continued !== false || row.redirect !== false
        || row.session_id !== owner.sessionId || row.frame_id !== owner.frameId
        || row.blocked_form_envelope?.content_type !== 'application/json') return false;
    try {
      const body = JSON.parse(row.blocked_form_envelope.body);
      return body.username === 'SOURCE_PROBE_LOGIN' && body.password === 'SOURCE_PROBE_NOT_A_PASSWORD';
    } catch {return false;}
  });
  if (!matched) throw new Error('SOURCE_FORM_PROBE_REFUSED');
  return true;
}

export function blockedFormEnvelope(request) {
  const refuse = () => {throw new Error('SOURCE_FORM_ENVELOPE_REFUSED');};
  if (!request || request.method !== 'POST' || !request.headers
      || typeof request.headers !== 'object' || Array.isArray(request.headers)) refuse();
  const types = Object.entries(request.headers).filter(([key]) => key.toLowerCase() === 'content-type');
  if (types.length !== 1 || typeof types[0][1] !== 'string' || types[0][1].length > 256
      || /[\r\n\0]/.test(types[0][1]) || typeof request.postData !== 'string'
      || Buffer.byteLength(request.postData) > 8192 || request.postData.length === 0) refuse();
  // Private observation only: do not retain Cookie, Authorization or other headers.
  return {content_type: types[0][1], body: request.postData};
}

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
