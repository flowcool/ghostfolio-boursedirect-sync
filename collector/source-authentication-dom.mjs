// Fixed source-described actions. Execute only in the attested owned main realm.
// Never return input contents, authentication DOM, cookie material or credentials.
export function submitSourceCredentials(login, password) {
  const refuse = () => {throw new Error('SOURCE_AUTHENTICATION_DOM_REFUSED');};
  if (typeof login !== 'string' || typeof password !== 'string' || !login || !password) refuse();
  const logins = document.querySelectorAll('#bd_auth_login_type_login');
  const passwords = document.querySelectorAll('#bd_auth_login_type_password');
  if (logins.length !== 1 || passwords.length !== 1) refuse();
  const inputs = [logins[0], passwords[0]], form = inputs[0].form;
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
  if (!form || form !== inputs[1].form || typeof form.requestSubmit !== 'function' || typeof setter !== 'function'
      || inputs.some(input => input.ownerDocument !== document || input.tagName !== 'INPUT'
        || input.disabled || input.readOnly || input.value !== '')
      || inputs[0].type !== 'text' || inputs[1].type !== 'password') refuse();
  for (const [index, input] of inputs.entries()) {
    setter.call(input, index === 0 ? login : password);
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.dispatchEvent(new Event('change', {bubbles: true}));
  }
  form.requestSubmit();
  return {code: 'SOURCE_CREDENTIAL_SUBMIT_REQUESTED', fields: 2};
}

export function inspectSourceTotpSelection(selectDistrusted = false) {
  const refuse = () => {throw new Error('SOURCE_AUTHENTICATION_DOM_REFUSED');};
  if (typeof selectDistrusted !== 'boolean') refuse();
  const headings = [...document.querySelectorAll('h6')].filter(node =>
    node.textContent === 'Authentification par application (TOTP)');
  if (headings.length !== 1 || headings[0].ownerDocument !== document) refuse();
  const section = headings[0].closest('section');
  const groups = section?.querySelectorAll('.code-input.react-code-input');
  if (groups?.length !== 1) refuse();
  const inputs = [...groups[0].querySelectorAll('input')];
  if (inputs.length !== 6 || inputs.some((input, index) => input.ownerDocument !== document
      || input.tagName !== 'INPUT' || input.type !== 'number' || input.inputMode !== 'numeric'
      || input.dataset.id !== String(index) || input.disabled || input.readOnly || input.value !== '')) refuse();
  const distrusted = section.querySelectorAll('#distrusted'), trusted = section.querySelectorAll('#trusted');
  // This qualification profile requires the observed trust-device control.
  if (distrusted.length !== 1 || trusted.length !== 1 || [distrusted[0], trusted[0]].some(input =>
    input.ownerDocument !== document || input.type !== 'radio' || input.name !== 'devicestate' || input.disabled)
      || distrusted[0].value !== 'distrusted' || trusted[0].value !== 'trusted') refuse();
  if (selectDistrusted) {
    if (trusted[0].checked) refuse();
    distrusted[0].click();
    return {code: 'SOURCE_DISTRUSTED_SELECTION_REQUESTED'};
  }
  if (!distrusted[0].checked || trusted[0].checked) refuse();
  return {method: 'TOTP', trusted_device: false, native_dom_checked: true, fields: 6};
}

export function submitSourceTotp(code) {
  // Kept self-contained for serialization into one checked native realm.
  const refuse = () => {throw new Error('SOURCE_AUTHENTICATION_DOM_REFUSED');};
  if (typeof code !== 'string' || !/^[0-9]{6}$/.test(code)) refuse();
  const headings = [...document.querySelectorAll('h6')].filter(node =>
    node.textContent === 'Authentification par application (TOTP)');
  if (headings.length !== 1) refuse();
  const section = headings[0].closest('section'), groups = section?.querySelectorAll('.code-input.react-code-input');
  if (groups?.length !== 1) refuse();
  const inputs = [...groups[0].querySelectorAll('input')];
  const distrusted = section.querySelectorAll('#distrusted'), trusted = section.querySelectorAll('#trusted');
  if (distrusted.length !== 1 || trusted.length !== 1
      || [distrusted[0], trusted[0]].some(input => input.ownerDocument !== document || input.type !== 'radio'
        || input.name !== 'devicestate' || input.disabled)
      || distrusted[0].value !== 'distrusted' || trusted[0].value !== 'trusted'
      || !distrusted[0].checked || trusted[0].checked
      || inputs.length !== 6 || inputs.some((input, index) => input.ownerDocument !== document
        || input.type !== 'number' || input.inputMode !== 'numeric' || input.dataset.id !== String(index)
        || input.disabled || input.readOnly || input.value !== '')) refuse();
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
  if (typeof setter !== 'function') refuse();
  // Source's multi-character input handler distributes all six digits and submits
  // once. Do not click Continuer or fill again after the native request appears.
  setter.call(inputs[0], code);
  inputs[0].dispatchEvent(new Event('input', {bubbles: true}));
  return {code: 'SOURCE_TOTP_SUBMIT_REQUESTED', fields: 6};
}
