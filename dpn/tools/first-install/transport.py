# SPDX-License-Identifier: GPL-2.0-only
from pathlib import Path
import json,subprocess
class RAM:
 def __init__(self,session,client_key):
  self.session=Path(session).resolve();self.state=json.loads((self.session/'state.json').read_text())
  self.args=['ssh','-F','/dev/null','-i',str(Path(client_key).resolve()),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','HostKeyAlgorithms=ssh-ed25519','-o','HostKeyAlias=dpn-session-ram','-o','UserKnownHostsFile='+str(self.session/'known-hosts'),'-o','ConnectTimeout=5','root@'+self.state['ram_host']]
 def call(self,cmd,data=None,timeout=120):
  p=subprocess.run(self.args+[cmd],input=data,capture_output=True,timeout=timeout)
  if p.returncode:raise RuntimeError(p.stderr.decode(errors='replace'))
  return p.stdout
