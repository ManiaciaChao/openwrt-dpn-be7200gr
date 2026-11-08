#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Stream a full physical NAND read over pinned SSH directly into age encryption."""
from pathlib import Path
import argparse,hashlib,json,subprocess,time
from transport import RAM
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--session',type=Path,required=True);p.add_argument('--client-key',type=Path,required=True);p.add_argument('--reader',type=Path,required=True);p.add_argument('--age',required=True);p.add_argument('--recipient',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--mode',choices=['ecc','raw'],default='ecc');a=p.parse_args()
assert a.recipient.startswith('age1') and not a.output.exists();a.output.parent.mkdir(parents=True,exist_ok=True)
r=RAM(a.session,a.client_key);assert r.call('cat /tmp/dpn-session').decode().strip()==r.state['nonce']
r.call('umask 077; cat > /tmp/dpn-nand-reader',a.reader.read_bytes());r.call('chmod 700 /tmp/dpn-nand-reader')
expected=536870912 if a.mode=='ecc' else 570425344
log=a.session/('nand-'+a.mode+'-read.log');total=0;h=hashlib.sha256();start=time.monotonic()
with log.open('wb') as err,a.output.open('xb') as encrypted:
 a.output.chmod(0o600);read=subprocess.Popen(r.args+['/tmp/dpn-nand-reader '+a.mode],stdout=subprocess.PIPE,stderr=err)
 enc=subprocess.Popen([a.age,'-r',a.recipient],stdin=subprocess.PIPE,stdout=encrypted)
 try:
  while True:
   block=read.stdout.read(1024*1024)
   if not block:break
   total+=len(block);assert total<=expected;h.update(block);enc.stdin.write(block)
  enc.stdin.close();assert read.wait(timeout=30)==0,'NAND reader reported failure';assert enc.wait(timeout=30)==0,'Encryption failed';assert total==expected,(total,expected)
 except BaseException:
  read.kill();enc.kill();read.wait();enc.wait();raise
meta=dict(mode=a.mode,plaintext_bytes=total,plaintext_SHA256=h.hexdigest(),encrypted_file=str(a.output.resolve()),encrypted_SHA256=hashlib.sha256(a.output.read_bytes()).hexdigest(),reader_exit_success=True,ECC_decoder_verified=a.mode=='ecc',direct_age_encryption=True,session_nonce=r.state['nonce'],elapsed_seconds=round(time.monotonic()-start,2))
out=a.session/('nand-'+a.mode+'-backup.json');out.write_text(json.dumps(meta,indent=2)+'\n');out.chmod(0o600);print('ENCRYPTED_NAND_BACKUP_COMPLETE',a.mode,total,'bytes')
