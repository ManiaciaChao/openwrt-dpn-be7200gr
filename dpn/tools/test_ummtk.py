#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Container boundary checks on synthetic in-memory bytes; no firmware upload."""
import struct,zlib
from ummtk import pack,unpack
from audit_stock_web_upgrade import inspect
fit=struct.pack('>II',0xd00dfeed,16)+b'NOT-FW!!'
b=bytearray(0x2100)+fit;struct.pack_into('<I',b,0,0xaa640001)
for i in range(4):
 ident=bytes([i+1])*16;start=256+i*16 if i<3 else 0x2000;size=2 if i<3 else len(fit)+256
 struct.pack_into('<16sQQQ',b,16+40*i,ident,start,size,0)
struct.pack_into('<4I',b,0x2000,0x32524448,256,len(fit)+256,zlib.crc32(fit)^0xffffffff)
fip=bytes(b);blob=pack(fip);assert len(blob)==len(fip)+404 and unpack(blob)==fip
v=inspect(blob);assert v['count']==1 and v['parts'][0]['magic']=='tclinux'
for name,offset in [('magic',0),('count',199),('whole-MD5',128),('part-MD5',328),('segment-type',264),('end',399),('payload',420)]:
 bad=bytearray(blob);bad[offset]^=1
 try:unpack(bytes(bad))
 except ValueError:pass
 else:raise AssertionError('Accepted '+name)
try:unpack(blob+b'trailing')
except ValueError:pass
else:raise AssertionError('Accepted trailing data')
bad=bytearray(fip);struct.pack_into('<Q',bad,16+24,0x4000)
try:pack(bytes(bad))
except ValueError:pass
else:raise AssertionError('Accepted overlapping FIP entry')
print('UMMTK_SINGLE_SEGMENT_BOUNDS_CHECKSUM_TYPES_TRAILING_AND_FIP_ENTRY_TESTS_PASS')
