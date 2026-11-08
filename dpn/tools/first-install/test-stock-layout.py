#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
from stock_layout import find_art
for i in [13,11,9]:assert find_art(f'dev: size erasesize name\nmtd0: 00080000 00040000 "bootloader"\nmtd{i}: 00380000 00040000 "art"\n'.encode())==f'mtd{i}'
for table in [b'',b'mtd13: 00380000 00040000 "art"\nmtd11: 00380000 00040000 "art"\n',b'mtd13: 00300000 00040000 "art"\n',b'mtd13: 00380000 00020000 "art"\n']:
 try:find_art(table)
 except ValueError:pass
 else:raise AssertionError('Accepted absent/ambiguous/wrong geometry ART')
print('STOCK_ART_BY_NAME_INDEX_CHANGES_AMBIGUITY_AND_GEOMETRY_REFUSAL_PASS')
