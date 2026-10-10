import test from 'node:test';
import assert from 'node:assert/strict';
import {sandboxStatus, loopbackNamespace, processIdentity, sameProcess, ownedDescendants} from '../lab/browser-sandbox-proof.mjs';
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

const root = {pid: 20, ppid: 1, group: 20, start: '100', state: 'S'};
const rendererChild = {pid: 30, ppid: 25, group: 30, start: '120', state: 'S'};
const tree = [rendererChild, root, {pid: 25, ppid: 20, group: 25, start: '110', state: 'S'},
  {pid: 40, ppid: 1, group: 20, start: '130', state: 'S'}];
test('ownership follows ancestry across groups and excludes a foreign process in the root group', () => {
  assert.deepEqual([...ownedDescendants(tree, root).keys()].sort(), [20, 25, 30]);
});
test('ownership rejects a reused root PID', () => {
  assert.throws(() => ownedDescendants(tree, {...root, start: '99'}), /SANDBOX_OWNERSHIP_REFUSED/);
});
test('identity pin prevents signaling a reused descendant PID', () => {
  assert.equal(sameProcess(rendererChild, {...rendererChild, start: '121'}), false);
  assert.equal(sameProcess(rendererChild, undefined), false);
  assert.equal(sameProcess(rendererChild, {...rendererChild, group: 50}), true);
});
test('orphaned and cyclic parent chains are never adopted', () => {
  assert.equal(ownedDescendants([root, {...rendererChild, ppid: 99},
    {pid: 98, ppid: 99, start: '1'}, {pid: 99, ppid: 98, start: '2'}], root).size, 1);
});
test('kernel stat parsing preserves start ticks and tolerates parentheses in command names', () => {
  const fields = ['S', '25', '30', ...Array(16).fill('0'), '12345678901234567890'];
  assert.deepEqual(processIdentity('30 (headless (shell)) ' + fields.join(' ')),
    {...rendererChild, start: '12345678901234567890'});
  assert.throws(() => processIdentity('30 (shell) S bad'), /SANDBOX_PROCESS_REFUSED/);
});
