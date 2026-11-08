#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Factory-independent FIP container for the tested original boot profile.
Certificate entries contain EMPTY DER sequences, not vendor certificates or
signatures. Real boot was tested on one recorded DPN-BE7200GR factory profile;
this does not implement certificate signing or qualify other secure-boot states.
Caller must validate the generic FIT. No device/Flash access is performed.
UUIDs: TF-A include/tools_share/firmware_image_package.h (standard TBBR types).
"""
from pathlib import Path
import argparse,hashlib,json,struct,zlib
UUIDS=['827ee890f860e411a1b4777a21b4f94c','8ad5832afb60e4118aafdf30bbc49859','8ec4c1f35d63e411a7a987ee40b23fa7','d6d0eea7fcead54b97829934f234b6e4']
def build(fit, *, maximum_bytes=0x1200000):
 if maximum_bytes not in (0x1200000,0x3200000):raise ValueError('Unsupported FIP size policy')
 if len(fit)<40 or struct.unpack_from('>II',fit)!=(0xd00dfeed,len(fit)) or len(fit)>maximum_bytes-0x2100:raise ValueError('Require bounded FIT')
 h=bytearray(0x2100);struct.pack_into('<IIQ',h,0,0xaa640001,0x12345678,0)
 for i,u in enumerate(UUIDS):
  off=[0x400,0x1000,0x1800,0x2000][i];size=2 if i<3 else len(fit)+256
  struct.pack_into('<16sQQQ',h,16+i*40,bytes.fromhex(u),off,size,0)
  if i<3:h[off:off+2]=b'\x30\x00'
 struct.pack_into('<4I',h,0x2000,0x32524448,256,len(fit)+256,zlib.crc32(fit)^0xffffffff)
 return bytes(h)+fit
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('fit',type=Path);p.add_argument('output',type=Path);a=p.parse_args();b=build(a.fit.read_bytes())
 with a.output.open('xb') as f:f.write(b)
 print(json.dumps({'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'private_factory_input':False,'real_certificates_or_signatures':False,'requires_matching_tested_factory_profile':True,'public_binary_release_qualified':False},indent=2))
