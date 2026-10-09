#!/usr/bin/env python3
"""Read-only aggregation of fixed synthetic CDP receipts; never runs a browser."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess

spec = importlib.util.spec_from_file_location('cdp_runner', Path(__file__).with_name('run-cdp-first-request.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def read_receipts(directory):
    receipts = {}
    for path in sorted(directory.glob('*-receipt.json')):
        runner.require(path.is_file() and not path.is_symlink(), 'PROOF_RECEIPT_REJECTED')
        runner.require(path.stat().st_size <= 1048576, 'PROOF_RECEIPT_LIMIT')
        value = json.loads(path.read_bytes())
        mode = value.get('mode')
        runner.require(mode in runner.SCENARIOS and mode not in receipts, 'PROOF_MODE_REJECTED')
        runner.require(path.name == mode + '-receipt.json', 'PROOF_FILENAME_REJECTED')
        receipts[mode] = value
    return receipts


def validate_receipt(receipt):
    runner.require(receipt.get('image') == runner.IMAGE and receipt.get('profile_sha256') == runner.PROFILE_SHA,
                   'PROOF_RUNTIME_PIN_MISMATCH')
    runner.require(receipt.get('cleanup_verified') is True
                   and receipt.get('browser_proven') is False, 'PROOF_CLEANUP_UNVERIFIED')
    runner.require(not receipt.get('cleanup_errors') and not receipt.get('execution_error'), 'PROOF_EXECUTION_FAILED')
    runner.require(receipt.get('owner_verified') is True, 'PROOF_OWNER_UNVERIFIED')
    runner.require(receipt.get('remove_returncode') == 0, 'PROOF_REMOVE_FAILED')
    runner.require(isinstance(receipt.get('source_sha256'), dict) and receipt['source_sha256'], 'PROOF_SOURCE_PINS_MISSING')
    runner.require(re.fullmatch(r'[0-9a-f]{64}', receipt.get('container', '')) is not None, 'PROOF_CONTAINER_ID_REJECTED')
    e = receipt.get('evidence', {})
    runner.require(e.get('mode') == receipt['mode'] and e.get('passed') is True
                   and e.get('owned_browser_exit') is True and e.get('browser_proven') is False
                   and e.get('node') == 'v20.19.2', 'PROOF_VERDICT_REJECTED')
    return e


def current_pins(root):
    # Reuse the exact allowlisted archive inventory, never a receipt-controlled path.
    runner.require(root.resolve() == runner.ROOT, 'PROOF_ROOT_REJECTED')
    _, hashes = runner.fixture_archive()
    return hashes


def consolidate(directory, capture_directory=None, verify_absent=False):
    receipts = read_receipts(directory)
    runner.require(set(receipts) == set(runner.SCENARIOS), 'PROOF_COVERAGE_INCOMPLETE')
    original = receipts['capture']
    replacement = None
    if capture_directory is not None:
        extras = read_receipts(capture_directory)
        runner.require(set(extras) == {'capture'}, 'PROOF_REPLACEMENT_SCOPE_REJECTED')
        replacement = extras['capture']
        old_pins = original['source_sha256']
        new_pins = replacement['source_sha256']
        runner.require(set(old_pins) == set(new_pins), 'PROOF_REPLACEMENT_INVENTORY_MISMATCH')
        runner.require(all(old_pins[k] == new_pins[k] for k in old_pins if k != 'capture-document.mjs')
                       and original['runner_sha256'] == replacement['runner_sha256'], 'PROOF_REPLACEMENT_COMMON_PIN_MISMATCH')
        validate_receipt(original)
        receipts['capture'] = replacement
    hashes = current_pins(runner.ROOT)
    runner_sha = hashlib.sha256(Path(runner.__file__).read_bytes()).hexdigest()
    evidence = []
    all_receipts = list(receipts.values()) + ([original] if replacement else [])
    identifiers = set()
    for receipt in all_receipts:
        e = validate_receipt(receipt)
        expected = dict(hashes)
        if replacement and receipt is not replacement:
            expected['capture-document.mjs'] = original['source_sha256']['capture-document.mjs']
        runner.require(receipt['source_sha256'] == expected
                       and receipt.get('runner_sha256') == runner_sha, 'PROOF_CURRENT_PIN_MISMATCH')
        runner.require(receipt['container'] not in identifiers, 'PROOF_CONTAINER_REUSED')
        identifiers.add(receipt['container'])
        if verify_absent:
            absent = runner.docker(['inspect', receipt['container']])
            runner.require(absent.returncode == 1 and b'no such object' in absent.stderr.lower(), 'PROOF_RESOURCE_ABSENCE_UNVERIFIED')
        evidence.append(e)
    # The same pure evaluator used by the live fixture rechecks observations, not just passed=true.
    result = subprocess.run(['/usr/bin/node', str(runner.ROOT / 'collector/lab/verify-observations.mjs')],
                            input=json.dumps(evidence).encode(), capture_output=True, timeout=10,
                            env={'PATH': '/usr/bin:/bin'})
    runner.require(result.returncode == 0, 'PROOF_OBSERVATIONS_REJECTED')
    return {'passed': True, 'modes': len(receipts), 'receipts': len(all_receipts),
            'current_pins_verified': True, 'live_absence_verified': verify_absent,
            'capture_replaced': replacement is not None, 'browser_proven': False,
            'validator_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in [Path(__file__), runner.ROOT / 'collector/lab/verify-observations.mjs']},
            'superseded_capture_sha256': (hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest()
                                          if replacement else None),
            'receipt_sha256': {mode: hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
                               for mode, value in receipts.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--replace-capture', type=Path)
    parser.add_argument('--verify-owned-absence', action='store_true')
    args = parser.parse_args()
    print(json.dumps(consolidate(args.directory, args.replace_capture, args.verify_owned_absence)))


if __name__ == '__main__':
    main()
