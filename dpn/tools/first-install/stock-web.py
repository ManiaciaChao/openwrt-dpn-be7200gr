#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Owner-authenticated stock Dropbear toggle for the tested DPN vendor profile.
No built-in credential, certificate, host address, or password guessing.
"""
import argparse,base64,getpass,hashlib,http.client,http.cookies,json,os,re,socket,ssl,time,urllib.parse
from pathlib import Path

def private_dir(path):
 path.mkdir(mode=0o700,parents=True,exist_ok=True)
 if path.stat().st_uid!=os.getuid() or path.stat().st_mode&0o077:raise ValueError('Session directory must be owned by you and mode 0700')

def fields(body):
 pairs=re.findall(r"objBuf\['MDMOID_DROP_BEAR'\]\['([^']+)'\]='([^']*)';",body.decode(errors='replace'))
 result=dict(pairs)
 if len(result)!=len(pairs) or result.get('Enable') not in ['0','1'] or not result.get('Port','').isdigit() or not 1<=int(result['Port'])<=65535:raise ValueError('No unambiguous authenticated Dropbear object')
 return result

class Client:
 def __init__(self,host,pin):self.host=host;self.pin=pin;self.cookies={}
 def get(self,path):
  ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);ctx.check_hostname=False;ctx.verify_mode=ssl.CERT_NONE
  raw=socket.create_connection((self.host,443),timeout=15)
  with ctx.wrap_socket(raw,server_hostname=None) as tls:
   if hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest()!=self.pin:raise ValueError('TLS fingerprint mismatch; no credentials sent')
   c=http.client.HTTPSConnection(self.host,port=443,timeout=15);c.sock=tls
   host=self.host.split('%')[0];host='['+host+']' if ':' in host else host
   headers={'Host':host,'Connection':'close'}
   if self.cookies:headers['Cookie']='; '.join(k+'='+v for k,v in self.cookies.items())
   c.request('GET',path,headers=headers);r=c.getresponse();body=b'';complete=False
   try:
    while True:
     b=r.read1(65536)
     if not b:complete=True;break
     body+=b
     if len(body)>2*1024*1024:raise ValueError('Unexpectedly large stock response')
     if b'</html>' in body.lower():complete=True;break
   except (TimeoutError,http.client.IncompleteRead):
    # Never retry a mutation; caller re-reads the independent settings page.
    pass
   for k,v in r.getheaders():
    if k.lower()=='set-cookie':
     jar=http.cookies.SimpleCookie();jar.load(v)
     for key,m in jar.items():self.cookies[key]=m.value
   status=r.status;c.close();return status,body,complete
 def settings(self):
  status,body,_=self.get('/x_myset1.html')
  if status!=200:raise ValueError('Authenticated settings page unavailable')
  return fields(body)
 def login(self,username,password):
  if not all(v and v.isascii() and v.isalnum() for v in [username,password]):raise ValueError('Only the verified stock ASCII alphanumeric login transformation is supported')
  query='&'.join(k+'='+base64.b64encode(v.encode()).decode() for k,v in [('username',username),('psd',password)])
  self.get('/login.cgi?'+query)
  return self.settings()
 def toggle(self,before,want):
  if before['Enable']==want:return before
  value=f"<MDMOID_DROP_BEAR>Enable={want}&Port={int(before['Port'])}</MDMOID_DROP_BEAR>"
  self.get('/x_myset1.cgi?type=objOperate&action=edit&id=MDMOID_DROP_BEAR&value='+urllib.parse.quote(value,safe='=&/'))
  time.sleep(2);after=self.settings()
  expected=before|{'Enable':want}
  if after!=expected:raise ValueError('Dropbear object verification failed; no automatic retry')
  return after

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('action',choices=['inspect','enable','restore']);p.add_argument('--host',required=True)
 p.add_argument('--tls-sha256',required=True,help='Certificate SHA256 verified by the owner before sending credentials')
 p.add_argument('--session',type=Path,required=True);p.add_argument('--username',default='admin')
 p.add_argument('--credential-file',type=Path,help='Private JSON containing username and password; otherwise prompt')
 a=p.parse_args();pin=a.tls_sha256.replace(':','').lower()
 if not re.fullmatch('[0-9a-f]{64}',pin):p.error('Require a SHA256 certificate fingerprint')
 # No URLs, paths, userinfo, or ports; IPv6 scope is permitted.
 if not re.fullmatch(r'[A-Za-z0-9_.:%-]+',a.host):p.error('Invalid host')
 private_dir(a.session);statefile=a.session/'stock-web.json'
 if a.credential_file:
  st=a.credential_file.stat()
  if st.st_uid!=os.getuid() or st.st_mode&0o077:p.error('Credential file must be private and owned by you')
  cred=json.loads(a.credential_file.read_text());username,password=cred['username'],cred['password']
 else:username,password=a.username,getpass.getpass('Stock web password: ')
 w=Client(a.host,pin);before=w.login(username,password);del password
 if statefile.exists():
  state=json.loads(statefile.read_text())
  if state['host']!=a.host or state['tls_SHA256']!=pin:raise ValueError('Session belongs to a different stock endpoint')
 else:
  state={'host':a.host,'tls_SHA256':pin,'original':before}
  # Exclusive creation prevents replacing the original service state.
  fd=os.open(statefile,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'w') as f:json.dump(state,f,indent=2);f.write('\n')
 want={'inspect':before['Enable'],'enable':'1','restore':state['original']['Enable']}[a.action]
 if a.action=='restore' and before['Port']!=state['original']['Port']:raise ValueError('Port changed independently; refusing restore')
 after=w.toggle(before,want)
 result={'action':a.action,'authenticated_settings':True,'before_enabled':before['Enable'],'after_enabled':after['Enable'],'port':int(after['Port']),'other_fields_unchanged':True,'password_saved':False}
 if a.action=='enable':
  with socket.create_connection((a.host,int(after['Port'])),timeout=10) as s:
   s.settimeout(10);banner=s.recv(256).split(b'\n',1)[0]
   if not banner.startswith(b'SSH-2.0-'):raise ValueError('No SSH service banner after enabling')
  result['SSH_banner_verified']=True
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
