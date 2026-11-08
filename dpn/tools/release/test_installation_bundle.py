#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prevent automatic firmware and old host-mode instructions being confused."""
from pathlib import Path
import tempfile
import zipfile
from package_layout4_set import add_installation_bundle

R = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory() as temporary:
    for mode in ('automatic', 'host'):
        out = Path(temporary)/mode; out.mkdir()
        add_installation_bundle(out, R, mode)
        manual = 'generic-first-install.md' if mode == 'automatic' else 'host-first-install.md'
        assert (out/'INSTALL.md').read_bytes() == (R/'docs'/manual).read_bytes()
        assert (out/'tools/first-install/layout4_install.py').exists() == (mode == 'host')
        with zipfile.ZipFile(out/'dpn-be7200gr-layout4-install.zip') as archive:
            assert archive.read('INSTALL.md') == (R/'docs'/manual).read_bytes()
            assert 'automatic-first-install.md' in archive.namelist()
        readme = (out/'README.txt').read_text()
        assert ('without host tools' in readme) == (mode == 'automatic')
        assert ('Python 3, OpenSSH and age are required' in readme) == (mode == 'host')
print('Automatic/legacy bundles carry matching instructions and host tools only for legacy mode')
