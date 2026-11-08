#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compare the real writer's libmd helpers against Python hashlib, on host and ARM."""
from pathlib import Path
import argparse,hashlib,os,subprocess,tempfile,json
p=argparse.ArgumentParser();p.add_argument('executable',type=Path);p.add_argument('--runner',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
lengths=[0,1,3,55,56,63,64,65,127,128,129,65535,65536,65537,1000000]
with tempfile.TemporaryDirectory(prefix='dpn-digest-vectors-') as td:
 file=Path(td)/'fixture';cases=[]
 for n in lengths:
  data=(b'abc' if n==3 else b'a'*n if n==1000000 else bytes((i*37+11)%256 for i in range(n)));file.write_bytes(data)
  args=([str(a.runner)] if a.runner else [])+[str(a.executable.resolve()),str(file)]
  r=subprocess.run(args,capture_output=True,check=True);out=r.stdout.decode().splitlines();expected=[hashlib.sha256(data).hexdigest(),hashlib.sha1(data).hexdigest(),hashlib.sha256(data).hexdigest()];assert out==expected,(n,out,expected);assert b'AddressSanitizer' not in r.stderr and b'runtime error:' not in r.stderr;cases.append(n)
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(dict(actual_writer_helpers=True,reference='Python hashlib SHA1/SHA256',lengths=cases,empty_abc_million_a_and_padding_stream_boundaries=True,target_ARM_via_QEMU=bool(a.runner)),indent=2)+'\n');print('WRITER_LIBMD_HASHLIB_KNOWN_AND_STREAM_BOUNDARIES_PASS',len(cases),'cases')
