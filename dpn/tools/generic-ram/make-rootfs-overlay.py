#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Public initrd containing only the generic SquashFS as /initrd.image."""
import argparse,io
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('squashfs',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
data=a.squashfs.read_bytes();assert data[:4]==b'hsqs' and len(data)<0x1200000
b=io.BytesIO()
for ino,(name,mode,body) in enumerate([('initrd.image',0o100600,data),('TRAILER!!!',0,b'')],1):
 fields=[ino,mode,0,0,1,0,len(body),0,0,0,0,len(name)+1,0]
 b.write(b'070701'+b''.join(f'{n:08x}'.encode() for n in fields));b.write(name.encode()+b'\0');b.write(b'\0'*((-b.tell())%4));b.write(body);b.write(b'\0'*((-b.tell())%4))
a.output.write_bytes(b.getvalue());print('PUBLIC_SQUASHFS_CPIO_CREATED',b.tell())
