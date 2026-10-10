import test from 'node:test';
import assert from 'node:assert/strict';
import {sandboxStatus, loopbackNamespace} from '../lab/browser-sandbox-proof.mjs';
const baseline = 'Seccomp:\t2\nSeccomp_filters:\t1\n';
const renderer = 'NoNewPrivs:\t1\nSeccomp:\t2\nSeccomp_filters:\t2\nNSpid:\t123 7\n';
test('renderer proof requires extra Chromium seccomp and nested PID namespace', () => {
  assert.equal(sandboxStatus(renderer, baseline).nested_pid_namespace, true);
});
for (const [name, raw] of [
  ['no added filter', renderer.replace('filters:\t2', 'filters:\t1')],
  ['no sandbox seccomp', renderer.replace('Seccomp:\t2', 'Seccomp:\t0')],
  ['no no-new-privileges', renderer.replace('NoNewPrivs:\t1', 'NoNewPrivs:\t0')],
  ['no nested namespace', renderer.replace('123 7', '123')],
  ['malformed namespace', renderer.replace('123 7', '123 unknown')],
  ['duplicate field', renderer + 'Seccomp:\t2\n'],
]) test('sandbox proof refuses ' + name, () => {
  assert.throws(() => sandboxStatus(raw, baseline), /SANDBOX_STATUS_REFUSED/);
});

const header = 'Inter-| Receive | Transmit\n face |bytes packets|bytes packets\n';
test('network proof uses namespace proc interfaces rather than host sysfs visibility', () => {
  assert.equal(loopbackNamespace(header + ' lo: 0 0 0 0\n'), true);
});
for (const [name, rows] of [
  ['external interface', ' lo: 0\n eth0: 0\n'],
  ['missing loopback', ''],
  ['duplicate loopback', ' lo: 0\n lo: 0\n'],
  ['malformed namespace observation', ' malformed\n'],
]) test('network proof refuses ' + name, () => {
  assert.throws(() => loopbackNamespace(header + rows), /SANDBOX_NETWORK_REFUSED/);
});
