#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check the boundary that prevents private research trees entering releases."""
import tempfile
from pathlib import Path
from check_source_stage import audit

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    stage = root / 'stage'
    stage.mkdir()
    (stage / 'README.md').write_text('Portable public source.\n')
    assert not audit(stage)
    outside = root / 'sensitive.txt'
    outside.write_text('secret outside release stage')
    (stage / 'escape').symlink_to(outside)
    assert any(x['reason'] == 'symlink_not_permitted' for x in audit(stage))
    (stage / 'escape').unlink()
    cases = [
        ('key.txt', '-----BEGIN ' + 'OPENSSH PRIVATE KEY-----\nbody\n', 'private_key_material'),
        ('config.py', 'ROOT="/' + 'home/example/work"\n', 'host_specific_absolute_path'),
        ('board.dts', 'mediatek,' + 'eeprom-data = /incbin/("board-eeprom.bin");\n', 'inline_calibration_requires_device_nvmem'),
        ('board.dts', 'local-' + 'mac-address = [02 00 00 00 00 01];\n', 'fixed_mac_requires_device_nvmem'),
        ('image.itb', 'even text with this extension is not a reviewed image', 'binary_or_archive_needs_separate_artifact_review'),
        ('opaque.txt', '\x00binary', 'binary_content_needs_review'),
        ('shadow', 'not a real hash', 'device_authentication_material'),
    ]
    for name, data, reason in cases:
        p = stage / name
        p.write_text(data)
        assert any(x['reason'] == reason for x in audit(stage)), reason
        p.unlink()
    (stage / 'private').mkdir()
    (stage / 'private' / 'config.txt').write_text('private')
    assert any(x['reason'] == 'private_or_build_path' for x in audit(stage))
print('Source staging boundary: clean tree, escaping symlink, key, host path, EEPROM, MAC, opaque artifact and private paths checked')
