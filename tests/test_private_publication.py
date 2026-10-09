import os
from pathlib import Path
import socket
import stat

import pytest
import boursedirect_to_ghostfolio as bd


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('No sockets')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


@pytest.mark.parametrize('rename_fails', [False, True])
def test_parent_swap_anchors_publication_cleanup_and_fsync(monkeypatch, rename_fails):
    Path('outputs').mkdir(mode=0o700)
    Path('inputs').mkdir(mode=0o700)
    source = Path('inputs/config.yaml')
    source.write_bytes(b'SYNTHETIC CONFIG')
    original = Path('outputs/config.yaml')
    original.write_bytes(b'PREVIOUS OUTPUT')
    source_inode, output_inode = source.stat().st_ino, original.stat().st_ino
    directory_identity = Path('outputs').stat().st_ino
    real_open, real_replace, real_sync = os.open, os.replace, os.fsync
    events = []
    def open_file(path, flags, *args, **kwargs):
        if flags & os.O_CREAT:
            Path('outputs').rename('moved-output')
            Path('outputs').symlink_to('inputs', target_is_directory=True)
            assert kwargs.get('dir_fd') is not None
            assert os.fstat(kwargs['dir_fd']).st_ino == directory_identity
            assert Path(path).name == path
        return real_open(path, flags, *args, **kwargs)
    def replace(source_name, target_name, **kwargs):
        assert source_name == Path(source_name).name
        assert target_name == 'config.yaml'
        assert kwargs['src_dir_fd'] == kwargs['dst_dir_fd']
        assert os.fstat(kwargs['dst_dir_fd']).st_ino == directory_identity
        events.append('rename')
        if rename_fails:
            raise OSError('synthetic rename failure')
        return real_replace(source_name, target_name, **kwargs)
    def sync(fd):
        info = os.fstat(fd)
        if stat.S_ISDIR(info.st_mode):
            assert info.st_ino == directory_identity
            events.append('directory-sync')
        else:
            events.append('file-sync')
        return real_sync(fd)
    monkeypatch.setattr(bd.os, 'open', open_file)
    monkeypatch.setattr(bd.os, 'replace', replace)
    monkeypatch.setattr(bd.os, 'fsync', sync)
    if rename_fails:
        with pytest.raises(OSError):
            bd.atomic_private_bytes(original, b'NEW OUTPUT')
    else:
        bd.atomic_private_bytes(original, b'NEW OUTPUT')
    assert source.read_bytes() == b'SYNTHETIC CONFIG'
    assert source.stat().st_ino == source_inode
    assert list(Path('inputs').iterdir()) == [source]
    moved = Path('moved-output/config.yaml')
    assert moved.read_bytes() == (b'PREVIOUS OUTPUT' if rename_fails else b'NEW OUTPUT')
    assert list(Path('moved-output').iterdir()) == [moved]
    if rename_fails:
        assert moved.stat().st_ino == output_inode
        assert events == ['file-sync', 'rename']
    else:
        assert stat.S_IMODE(moved.stat().st_mode) == 0o600
        assert events == ['file-sync', 'rename', 'directory-sync']


@pytest.mark.parametrize('kind', ['parent', 'destination', 'dangling'])
def test_symlink_boundaries_refuse_without_changing_source(kind):
    Path('inputs').mkdir()
    source = Path('inputs/config.yaml')
    source.write_bytes(b'SYNTHETIC CONFIG')
    inode = source.stat().st_ino
    if kind == 'parent':
        Path('outputs').symlink_to('inputs', target_is_directory=True)
    else:
        Path('outputs').mkdir()
        Path('outputs/config.yaml').symlink_to('../inputs/config.yaml' if kind == 'destination' else '../absent')
    with pytest.raises((RuntimeError, OSError)):
        bd.atomic_private_bytes('outputs/config.yaml', b'NEW OUTPUT')
    assert source.read_bytes() == b'SYNTHETIC CONFIG'
    assert source.stat().st_ino == inode
    assert not list(Path('outputs').glob('.*'))


def test_exclusive_creation_failure_never_unlinks_unowned_entry(monkeypatch):
    from types import SimpleNamespace
    Path('outputs').mkdir()
    collision = Path('outputs/.config.yaml.synthetic')
    collision.write_bytes(b'UNOWNED ENTRY')
    monkeypatch.setattr(bd.uuid, 'uuid4', lambda: SimpleNamespace(hex='synthetic'))
    with pytest.raises(FileExistsError):
        bd.atomic_private_bytes('outputs/config.yaml', b'NEW OUTPUT')
    assert collision.read_bytes() == b'UNOWNED ENTRY'


@pytest.mark.parametrize('stage', ['fdopen', 'file-sync', 'directory-sync'])
def test_failure_closes_descriptors_and_preserves_pre_rename_output(monkeypatch, stage):
    Path('outputs').mkdir()
    destination = Path('outputs/config.yaml')
    destination.write_bytes(b'PREVIOUS OUTPUT')
    real_open, real_sync = os.open, os.fsync
    opened = []
    def open_file(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd
    def fdopen(*args, **kwargs):
        raise OSError('synthetic stream construction failure')
    def sync(fd):
        directory = stat.S_ISDIR(os.fstat(fd).st_mode)
        if directory == (stage == 'directory-sync'):
            raise OSError('synthetic persistence failure')
        return real_sync(fd)
    monkeypatch.setattr(bd.os, 'open', open_file)
    if stage == 'fdopen':
        monkeypatch.setattr(bd.os, 'fdopen', fdopen)
    else:
        monkeypatch.setattr(bd.os, 'fsync', sync)
    with pytest.raises(OSError):
        bd.atomic_private_bytes(destination, b'NEW OUTPUT')
    for fd in opened:
        with pytest.raises(OSError):
            os.fstat(fd)
    assert not list(Path('outputs').glob('.*'))
    assert destination.read_bytes() == (b'NEW OUTPUT' if stage == 'directory-sync' else b'PREVIOUS OUTPUT')
