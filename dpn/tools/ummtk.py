#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Strict, single-tclinux UMMtk packaging. Does not upload, sign or select a slot.
Input is an independently verified target-compatible FIP, not a sysupgrade tar.
A target-derived FIP/header is private input; wrapping it does not make it public.
"""
import argparse,hashlib,json,struct,zlib
from pathlib import Path

def validate_fip(b, *, maximum_bytes=0x1200000):
 if maximum_bytes not in (0x1200000,0x3200000):raise ValueError('Unsupported FIP size policy')
 if not 0x2100<len(b)<=maximum_bytes:raise ValueError('FIP exceeds the selected firmware window')
 # This validates container lengths/checksum, not secure-boot certificate trust.
 if struct.unpack_from('<I',b)[0]!=0xaa640001:raise ValueError('No FIP magic')
 entries=[]
 for pos in range(16,216,40):
  ident,start,size,flags=struct.unpack_from('<16sQQQ',b,pos)
  if ident==bytes(16):break
  if start<216 or size==0 or start+size>len(b) or flags:raise ValueError('Invalid FIP entry range/flags')
  entries.append((start,start+size))
 if len(entries)!=4 or entries[-1]!=(0x2000,len(b)):raise ValueError('Require three certificates and the bounded HDR2 payload')
 if len({b[16+i*40:32+i*40] for i in range(4)})!=4 or any(a[1]>c[0] for a,c in zip(sorted(entries),sorted(entries)[1:])):raise ValueError('Duplicate UUID or overlapping FIP entries')
 fit=b[0x2100:]
 if struct.unpack_from('>II',fit)!= (0xd00dfeed,len(fit)):raise ValueError('FIT magic/size mismatch')
 if struct.unpack_from('<Q',b,160)[0]!=len(fit)+256:raise ValueError('FIP entry length mismatch')
 if struct.unpack_from('<4I',b,0x2000)!=(0x32524448,256,len(fit)+256,zlib.crc32(fit)^0xffffffff):raise ValueError('HDR2/JAMCRC mismatch')
 return {'FIP_bytes':len(b),'FIP_SHA256':hashlib.sha256(b).hexdigest(),'FIT_bytes':len(fit)}

def pack(fip, *, maximum_bytes=0x1200000):
 validate_fip(fip, maximum_bytes=maximum_bytes)
 b=bytearray(404+len(fip));b[:5]=b'UMMtk';b[200:212]=b'dpn-be7200gr';b[264:271]=b'tclinux';b[328:344]=hashlib.md5(fip).digest();struct.pack_into('>III',b,392,404,len(b)-1,len(fip));struct.pack_into('>II',b,192,len(b),1);b[404:]=fip;b[128:144]=hashlib.md5(fip).digest()
 return bytes(b)

def unpack(b, *, maximum_bytes=0x1200000):
 if len(b)<404 or b[:64]!=b'UMMtk'+bytes(59) or b[64:128]!=bytes(64) or b[144:200-8]!=bytes(48):raise ValueError('Noncanonical UMMtk header')
 if struct.unpack_from('>II',b,192)!=(len(b),1):raise ValueError('Require exactly one contiguous tclinux segment and no trailing bytes')
 if b[264:328]!=b'tclinux'+bytes(57) or b[344:392]!=bytes(48):raise ValueError('Forbidden segment type or noncanonical descriptor')
 if struct.unpack_from('>III',b,392)!=(404,len(b)-1,len(b)-404):raise ValueError('Noncanonical component range')
 fip=b[404:];digest=hashlib.md5(fip).digest()
 if b[128:144]!=digest or b[328:344]!=digest:raise ValueError('MD5 mismatch')
 validate_fip(fip, maximum_bytes=maximum_bytes);return fip

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['pack','inspect']);p.add_argument('input',type=Path);p.add_argument('--output',type=Path);a=p.parse_args();data=a.input.read_bytes()
 if a.action=='pack':
  if not a.output:p.error('pack requires --output')
  blob=pack(data);assert unpack(blob)==data
  with a.output.open('xb') as f:a.output.chmod(0o600);f.write(blob)
 else:blob=data;data=unpack(blob)
 print(json.dumps(validate_fip(data)|{'UMMtk_bytes':len(blob),'UMMtk_SHA256':hashlib.sha256(blob).hexdigest(),'segments':['tclinux'],'slot_not_encoded_in_container':True,'no_secure_boot_or_public_release_qualification_claimed':True},indent=2))
if __name__=='__main__':main()
