#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Fail-closed checks for an explicitly staged public SOURCE tree.
This does not inspect firmware internals and must never approve binary images.
Reports paths/reason codes only; matching secret text is never printed.
"""
import argparse
import json
from pathlib import Path
import re
import stat

FORBIDDEN = {'.git', '.codex-attachments', 'backups', 'build', 'logs', '__pycache__'}
OPAQUE = {'.bin', '.itb', '.fip', '.img', '.squashfs', '.cpio', '.gz', '.xz', '.zst', '.zip', '.age', '.ko', '.o', '.pyc'}
PRIVATE_KEY = re.compile(rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----\r?\n')
HOST_PATH = re.compile(rb'/(?:home/[^/\s]+/|nix/store/|dev/shm/)')
EEPROM_INLINE = re.compile(rb'mediatek,eeprom-data\s*=')
MAC_INLINE = re.compile(rb'local-mac-address\s*=\s*\[')
MAX_FILE_BYTES = 4 * 1024 * 1024


def audit(stage):
    stage = Path(stage)
    findings = []
    def issue(path, reason):
        findings.append({'path': str(path), 'reason': reason})
    if stage.is_symlink() or not stage.is_dir():
        return [{'path': '.', 'reason': 'stage_must_be_a_real_directory'}]
    for path in sorted(stage.rglob('*')):
        name = path.relative_to(stage)
        # lstat and reject links before reading: never follow private symlinks.
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            issue(name, 'symlink_not_permitted'); continue
        if any(p in FORBIDDEN for p in name.parts) or 'private' in name.parts:
            issue(name, 'private_or_build_path'); continue
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            issue(name, 'non_regular_file'); continue
        if path.suffix.lower() in OPAQUE:
            issue(name, 'binary_or_archive_needs_separate_artifact_review'); continue
        if path.name in {'shadow', 'authorized_keys'} or re.fullmatch(r'dropbear_.+_host_key', path.name):
            issue(name, 'device_authentication_material'); continue
        if path.stat().st_size > MAX_FILE_BYTES:
            issue(name, 'source_file_exceeds_review_limit'); continue
        data = path.read_bytes()
        try:
            data.decode('utf-8')
        except UnicodeDecodeError:
            issue(name, 'non_text_source_needs_review'); continue
        if b'\0' in data:
            issue(name, 'binary_content_needs_review')
        for pattern, reason in [
            (PRIVATE_KEY, 'private_key_material'),
            (HOST_PATH, 'host_specific_absolute_path'),
            (EEPROM_INLINE, 'inline_calibration_requires_device_nvmem'),
            (MAC_INLINE, 'fixed_mac_requires_device_nvmem'),
        ]:
            if pattern.search(data):
                issue(name, reason)
    if not any(p.is_file() and not p.is_symlink() for p in stage.iterdir()):
        issue('.', 'empty_or_incomplete_source_stage')
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', type=Path)
    args = parser.parse_args()
    findings = audit(args.stage)
    print(json.dumps({'scope': 'staged_source_only', 'passed': not findings,
                      'firmware_release_approved': False, 'findings': findings}, indent=2))
    return 1 if findings else 0


if __name__ == '__main__':
    raise SystemExit(main())
