"""Isolated private files and fake daemon; no real runtime or shared state."""
import copy
import importlib.util
import io
import json
import selectors
import subprocess
from pathlib import Path
import sys
from types import SimpleNamespace
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fixture(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    spec = importlib.util.spec_from_file_location('vault_composition_fixture', ROOT / 'scripts/vault_composition.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tmp_path.chmod(0o700)
    profile = tmp_path / 'profile.json'
    profile.write_text('{"defaultAction":"synthetic-only","syscalls":[]}')
    state = {'run': str(uuid.uuid4()), 'daemon': 'synthetic-daemon', 'resources': {}}
    registry = tmp_path / 'registry.yaml'
    module.private._publish(registry, state, exclusive=True)
    calls = []
    image, identifier = 'sha256:' + 'a' * 64, 'b' * 64
    details = {}
    def fake_docker(args, **kwargs):
        calls.append(args)
        if args[0] == 'create':
            saved = module.private._read(registry)
            assert saved['resources']['worker']['state'] == 'intent'
            assert saved['resources']['worker']['id'] is None
            assert not any(value in ' '.join(args) for value in module.SECRETS)
            owner = args[args.index('--name') + 1]
            details.update({'Id': identifier, 'Image': image, 'Mounts': [],
                'Config': {'Labels': {'proof.owner': owner}, 'User': '1000:1000', 'Entrypoint': ['/usr/bin/node'],
                           'Cmd': [args[-1]], 'Env': ['HOME=/home/fixture','PATH=/usr/bin:/bin']},
                'HostConfig': {'NetworkMode':'none', 'LogConfig':{'Type':'none','Config':{}}, 'Privileged':False,
                    'RestartPolicy':{'Name':'no','MaximumRetryCount':0}, 'PidMode':'', 'IpcMode':'private',
                    'Memory':805306368,'NanoCpus':1000000000,'PidsLimit':256,'ShmSize':134217728,
                    'Ulimits':[{'Name':'core','Hard':0,'Soft':0}],
                    'Tmpfs':{'/vault':'rw,noexec,nosuid,mode=0700,uid=1000,gid=1000'},
                    'SecurityOpt':['seccomp=' + profile.read_text()]}, 'State':{'Running':False,'Status':'created'}})
            return SimpleNamespace(returncode=0, stdout=(identifier + '\n').encode(), stderr=b'')
        assert args[0] == 'cp'
        assert module.private._read(registry)['resources']['worker']['state'] == 'receipted'
        return SimpleNamespace(returncode=0, stdout=b'', stderr=b'')
    ops = {'daemon':lambda:'synthetic-daemon', 'docker':fake_docker, 'inspect':lambda value: details}
    return module, state, registry, profile, image, identifier, details, ops, calls


def allocate(f):
    module, state, registry, profile, image, *rest = f
    return module.allocate(state, registry, 'worker', image, profile, b'invented archive', rest[-2])


def test_fixed_runtime_receipt_precedes_copy_and_start(fixture):
    f = fixture
    module, state, registry, profile, image, identifier, details, ops, calls = f
    assert allocate(f) == identifier
    assert module.before_start(state, registry, 'worker', profile.read_bytes(), ops) == identifier
    assert module.private._read(registry)['resources']['worker']['state'] == 'started'
    assert [args[0] for args in calls] == ['create','cp']
    assert all('start' not in args and 'ls' not in args for args in calls)


@pytest.mark.parametrize('change', [
    lambda d:d['Config'].update(User='0:0'), lambda d:d['Config']['Env'].append('BW_PASSWORD=SYNTHETIC_UNLOCK'),
    lambda d:d['HostConfig'].update(NetworkMode='host'), lambda d:d['HostConfig'].update(LogConfig={'Type':'json-file','Config':{}}),
    lambda d:d.update(Mounts=[{'Source':'shared'}]), lambda d:d['Config']['Labels'].update({'proof.owner':'foreign'}),
    lambda d:d['HostConfig'].update(RestartPolicy={'Name':'always','MaximumRetryCount':0}),
])
def test_changed_runtime_cannot_start(fixture, change):
    module, state, registry, profile, _, _, details, ops, calls = fixture
    allocate(fixture)
    change(details)
    with pytest.raises(RuntimeError, match='VAULT_RUNTIME_MISMATCH'):
        module.before_start(state, registry, 'worker', profile.read_bytes(), ops)
    assert module.private._read(registry)['resources']['worker']['state'] == 'receipted'


def test_secret_in_unchecked_metadata_cannot_start(fixture):
    module, state, registry, profile, _, _, details, ops, _ = fixture
    allocate(fixture)
    details['Config']['Hostname'] = 'SYNTHETIC_UNLOCK'
    with pytest.raises(RuntimeError, match='VAULT_METADATA_LEAK'):
        module.before_start(state, registry, 'worker', profile.read_bytes(), ops)
    assert module.private._read(registry)['resources']['worker']['state'] == 'receipted'


@pytest.mark.parametrize('secret', ['SYNTHETIC_API', 'SYNTHETIC_UNLOCK'])
def test_worker_credentials_never_reach_browser_initialization(fixture, monkeypatch, secret):
    module, _, registry, profile, image, _, _, _, _ = fixture
    starts, messages = [], []
    process = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(), stderr=io.BytesIO(), wait=lambda **kwargs: 0)
    monkeypatch.setattr(module, 'daemon', lambda: 'synthetic-daemon')
    monkeypatch.setattr(module, 'allocate', lambda *args: 'b' * 64)
    monkeypatch.setattr(module, 'docker', lambda *args, **kwargs: SimpleNamespace(returncode=0))
    monkeypatch.setattr(module, 'before_start', lambda state, filename, role, profile: starts.append(role))
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *args, **kwargs: process)
    monkeypatch.setattr(module, 'send', lambda process, value: messages.append(value))
    monkeypatch.setattr(module, 'cleanup', lambda *args: None)
    monkeypatch.setattr(module, 'sources', lambda: (b'invented', {'proof/lab/fake-bw.mjs': 'a' * 64}))
    def selected(process):
        binding = messages[0]['configuration']['binding']
        return {'selected': {**binding, 'online_ready': False, 'password': 'SYNTHETIC_PASSWORD', 'extra': secret}}
    monkeypatch.setattr(module, 'receive', selected)
    with pytest.raises(RuntimeError, match='VAULT_COMPOSITION_INCOMPLETE'):
        module.run('success', image, '155.0.8059.39', profile, registry.parent / 'leak-proof',
                   b'invented', {'proof/lab/fake-bw.mjs': 'a' * 64})
    assert starts == ['worker']
    assert len(messages) == 1


@pytest.mark.parametrize('phase', ['intent','receipt','start'])
def test_fsync_failure_never_grants_start_or_replay(fixture, monkeypatch, phase):
    module, state, registry, profile, _, _, details, ops, calls = fixture
    real = module.private._publish
    def publish(path, value, **kwargs):
        row = value['resources'].get('worker', {})
        if row.get('state') == {'intent':'intent','receipt':'receipted','start':'started'}[phase]:
            raise OSError('synthetic fsync failure')
        return real(path, value, **kwargs)
    if phase == 'start':
        allocate(fixture)
    monkeypatch.setattr(module.private, '_publish', publish)
    with pytest.raises(OSError):
        if phase == 'start':
            module.before_start(state, registry, 'worker', profile.read_bytes(), ops)
        else:
            allocate(fixture)
    assert not any(args[0] == 'start' for args in calls)
    assert [args[0] for args in calls] == ([] if phase == 'intent' else ['create','cp'] if phase == 'start' else ['create'])
    # A new invocation cannot accept a memory-only receipt or failed start write.
    with pytest.raises(RuntimeError):
        module.before_start(state, registry, 'worker', profile.read_bytes(), ops)


def test_daemon_change_stops_before_create_and_before_start(fixture):
    module, state, registry, profile, _, _, details, ops, calls = fixture
    wrong = {**ops, 'daemon':lambda:'other-daemon'}
    with pytest.raises(RuntimeError, match='VAULT_DAEMON_MISMATCH'):
        module.allocate(state, registry, 'worker', fixture[4], profile, b'invented', wrong)
    assert calls == []
    allocate(fixture)
    with pytest.raises(RuntimeError, match='VAULT_DAEMON_MISMATCH'):
        module.before_start(state, registry, 'worker', profile.read_bytes(), wrong)


def test_intent_only_state_cannot_gain_authority_after_restart(fixture):
    module, state, registry, profile, _, _, details, ops, calls = fixture
    ops['docker'] = lambda args, **kwargs: SimpleNamespace(returncode=1, stdout=b'', stderr=b'')
    with pytest.raises(RuntimeError, match='VAULT_CREATE_UNCERTAIN'):
        allocate(fixture)
    retained = module.private._read(registry)
    assert retained['resources']['worker']['state'] == 'intent'
    with pytest.raises(RuntimeError, match='VAULT_RECEIPT_REQUIRED'):
        module.before_start(retained, registry, 'worker', profile.read_bytes(), ops)
    with pytest.raises(RuntimeError):
        module.allocate(retained, registry, 'worker', fixture[4], profile, b'invented', ops)


@pytest.mark.parametrize('failure', ['daemon','inspection','remove','absence','publication'])
def test_uncertain_cleanup_preserves_exact_receipt_and_never_claims_absence(fixture, monkeypatch, failure):
    module, state, registry, profile, _, identifier, details, ops, calls = fixture
    allocate(fixture)
    removed = []
    monkeypatch.setattr(module, 'daemon', lambda:'other-daemon' if failure == 'daemon' else 'synthetic-daemon')
    def inspected(value):
        assert value == identifier
        if failure == 'inspection':
            raise RuntimeError('VAULT_INSPECTION_FAILED')
        return details
    monkeypatch.setattr(module, 'inspect', inspected)
    def command(args, **kwargs):
        assert args[-1] == identifier or args[0] == 'stop'
        if args[0] == 'stop':
            return SimpleNamespace(returncode=0, stdout=b'', stderr=b'')
        if args[0] == 'rm':
            removed.append(identifier)
            return SimpleNamespace(returncode=1 if failure == 'remove' else 0, stdout=b'', stderr=b'')
        assert args[0] == 'inspect'
        return SimpleNamespace(returncode=1, stdout=b'[]',
                               stderr=('generic transport failure' if failure == 'absence' else 'Error: No such object: ' + identifier).encode())
    monkeypatch.setattr(module, 'docker', command)
    if failure == 'publication':
        monkeypatch.setattr(module.private, '_publish', lambda *a, **k: (_ for _ in ()).throw(OSError('synthetic fsync failure')))
    with pytest.raises((RuntimeError, OSError)):
        module.cleanup(state, registry, profile.read_bytes(), registry.parent)
    assert module.private._read(registry)['resources']['worker']['state'] == 'receipted'
    assert removed == ([] if failure in ('daemon','inspection') else [identifier])


@pytest.mark.parametrize('window', ['intent-before-create','create-before-receipt','receipt-before-start','started-before-dispatch'])
def test_abrupt_exit_retains_allocation_and_exact_cleanup_authority(fixture, window, monkeypatch):
    module, state, registry, profile, image, identifier, details, ops, calls = fixture
    # Obtain an invented exact runtime description, then provision a fresh
    # independent child registry. This subprocess never calls Docker or Beads.
    allocate(fixture)
    child_state = {'run':state['run'], 'daemon':state['daemon'], 'resources':{}}
    filename = registry.parent / 'child-registry.yaml'
    module.private._publish(filename, child_state, exclusive=True)
    data = registry.parent / 'child-input.json'
    data.write_text(json.dumps({'state':child_state,'details':details,'image':image,'id':identifier,
                               'registry':str(filename),'profile':str(profile),'window':window}))
    code = '''import sys,json,signal
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
import vault_composition as m
x=json.loads(Path(sys.argv[2]).read_text())
state=x['state']; filename=Path(x['registry']); profile=Path(x['profile'])
real=m.private._publish
def checkpoint():
 print('OWNED_CHECKPOINT',flush=True); signal.pause()
def publish(path,value,**kwargs):
 row=value['resources'].get('worker',{})
 if x['window']=='create-before-receipt' and row.get('state')=='receipted': checkpoint()
 real(path,value,**kwargs)
 if (x['window']=='intent-before-create' and row.get('state')=='intent') or (x['window']=='receipt-before-start' and row.get('state')=='receipted') or (x['window']=='started-before-dispatch' and row.get('state')=='started'): checkpoint()
m.private._publish=publish
ops={'daemon':lambda:state['daemon'],'inspect':lambda _:x['details'],
 'docker':lambda args,**kwargs:SimpleNamespace(returncode=0,stdout=(x['id']+'\\n').encode() if args[0]=='create' else b'',stderr=b'')}
m.allocate(state,filename,'worker',x['image'],profile,b'invented archive',ops)
m.before_start(state,filename,'worker',profile.read_bytes(),ops)
'''
    process = subprocess.Popen([sys.executable,'-c',code,str(ROOT / 'scripts'),str(data)],
                               env={'PATH':'/usr/bin:/bin'}, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with selectors.DefaultSelector() as ready:
            ready.register(process.stdout,selectors.EVENT_READ)
            assert ready.select(5), 'fixture did not reach its durable checkpoint'
        assert process.stdout.readline() == b'OWNED_CHECKPOINT\n'
        process.kill()
        assert process.wait(timeout=5) < 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()
    retained = module.private._read(filename)
    assert retained['resources']['worker']['state'] == {
        'intent-before-create':'intent','create-before-receipt':'intent',
        'receipt-before-start':'receipted','started-before-dispatch':'started'}[window]
    with pytest.raises(RuntimeError):
        module.allocate(retained,filename,'worker',image,profile,b'invented',ops)
    removed = []
    monkeypatch.setattr(module,'daemon',lambda:state['daemon'])
    monkeypatch.setattr(module,'inspect',lambda _:details)
    def command(args,**kwargs):
        assert args[-1] == identifier
        if args[0]=='rm': removed.append(identifier)
        return SimpleNamespace(returncode=1 if args[0]=='inspect' else 0,stdout=b'[]' if args[0]=='inspect' else b'',
                               stderr=('Error: No such object: '+identifier).encode() if args[0]=='inspect' else b'')
    monkeypatch.setattr(module,'docker',command)
    if window in ('intent-before-create','create-before-receipt'):
        with pytest.raises(RuntimeError,match='VAULT_UNRECEIPTED_ORPHAN'):
            module.cleanup(retained,filename,profile.read_bytes(),filename.parent)
        assert removed == []
    else:
        module.cleanup(retained,filename,profile.read_bytes(),filename.parent)
        assert removed == [identifier]
        assert module.private._read(filename)['resources']['worker']['state']=='absence_verified'
