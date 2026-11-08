#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only stock-return input inspection. No device access or flash writer.

Checks a single-tclinux UMMtk container or an explicitly selected local slot
backup. Container checksums are not signatures or proof of board compatibility.
"""
from pathlib import Path
import argparse, hashlib, json, struct, zlib

SLOT=0x3200000
class InvalidImage(ValueError): pass
def need(ok, message):
    if not ok: raise InvalidImage(message)
def cstring(data, label, limit=128):
    b=bytes(data)
    need(0<len(b)<=limit and b[-1:]==b'\0' and b'\0' not in b[:-1],label)
    try:return b[:-1].decode('ascii')
    except UnicodeDecodeError:raise InvalidImage(label)

def fdt_nodes(blob):
    b=memoryview(blob);need(len(b)>=40,'truncated FDT header')
    magic,total,off,strings,reserve,version,compat,_,ssize,size=struct.unpack_from('>10I',b)
    need(magic==0xd00dfeed and total==len(b),'FDT magic/length')
    need(version==17 and compat<=17,'unsupported FDT version')
    need(off%4==0 and reserve%8==0 and 40<=reserve<off and off+size<=strings and strings+ssize<=total,'FDT block bounds')
    # Reservation entries must terminate before the structure block.
    at=reserve
    while True:
        need(at+16<=off,'unterminated reservation map')
        address,length=struct.unpack_from('>QQ',b,at);at+=16
        if not address and not length:break
    names=bytes(b[strings:strings+ssize]);end=off+size;stack=[];nodes={};ended=False
    while off<end:
        need(off+4<=end,'truncated FDT token');token=struct.unpack_from('>I',b,off)[0];off+=4
        if token==1:
            stop=off
            while stop<end and stop-off<=255 and b[stop]:stop+=1
            need(stop<end and stop-off<=255,'unterminated node name')
            try:name=bytes(b[off:stop]).decode('ascii')
            except UnicodeDecodeError:raise InvalidImage('non-ASCII node name')
            need('/' not in name and (not stack or name),'invalid node name')
            need(stack or (not name and not nodes),'invalid root node')
            stack.append(name);need(len(stack)<=64 and len(nodes)<20000,'FDT complexity limit')
            path='/'+ '/'.join(stack[1:]);need(path not in nodes,'duplicate FDT node');nodes[path]={}
            off=(stop+4)&~3
        elif token==2:
            need(bool(stack),'unmatched END_NODE');stack.pop()
        elif token==3:
            need(stack and off+8<=end,'property outside node')
            length,nameoff=struct.unpack_from('>II',b,off);off+=8
            need(off+length<=end and nameoff<len(names),'FDT property bounds')
            stop=names.find(b'\0',nameoff);need(stop>=nameoff,'unterminated property name')
            try:name=names[nameoff:stop].decode('ascii')
            except UnicodeDecodeError:raise InvalidImage('non-ASCII property name')
            need(0<len(name)<=128,'property name length')
            props=nodes['/'+ '/'.join(stack[1:])];need(name not in props,'duplicate property')
            props[name]=b[off:off+length];off=(off+length+3)&~3
        elif token==4:pass
        elif token==9:
            need(not stack and '/' in nodes,'incomplete FDT tree')
            need(not any(b[off:end]),'data after FDT_END');ended=True;break
        else:raise InvalidImage('unknown FDT token')
    need(ended,'missing FDT_END');return nodes

def stock_component(blob):
    need(404<=len(blob)<=SLOT+65536,'UMMtk input size')
    need(blob[:5]==b'UMMtk','UMMtk magic')
    total,count=struct.unpack_from('>II',blob,192)
    need(total==len(blob) and 1<=count<=16,'UMMtk length/segment count')
    cursor=200+204*count;need(cursor<=total,'UMMtk descriptor bounds')
    need(hashlib.md5(blob[cursor:]).digest()==blob[128:144],'UMMtk total MD5')
    selected=None
    for i in range(count):
        d=200+204*i;kind=blob[d+64:d+128].split(b'\0',1)[0].lower()
        need(kind in [b'tclinux',b'verinfo'],'stock return refuses non-firmware write targets')
        start,last,size=struct.unpack_from('>III',blob,d+192)
        need(size>=2 and start==cursor and last==start+size-1 and size<=total-start,'UMMtk component bounds/order')
        value=blob[start:start+size];need(hashlib.md5(value).digest()==blob[d+128:d+144],'UMMtk component MD5')
        if kind==b'tclinux':
            need(selected is None and size<=SLOT,'duplicate/oversized tclinux');selected=value
        else:need(size<=4096,'oversized version metadata')
        cursor+=size
    need(cursor==total and selected is not None,'missing tclinux or incomplete container');return selected

def inspect_fip(blob, allow_erased_tail=False):
    need(0x2100<len(blob)<=SLOT,'stock FIP size')
    need(struct.unpack_from('<I',blob)[0]==0xaa640001,'FIP magic')
    entries=[];ids=set();terminator=None
    for pos in range(16,216,40):
        ident,start,size,flags=struct.unpack_from('<16sQQQ',blob,pos)
        if not any(ident):
            need(not size and not flags,'invalid FIP terminator');terminator=start;break
        need(ident not in ids,'duplicate FIP UUID');ids.add(ident)
        need(start>=216 and size and start+size<=len(blob) and not flags,'FIP range/flags')
        entries.append((start,start+size))
    need(len(entries)==4 and len(ids)==4 and terminator is not None,'FIP entry count/terminator')
    ordered=sorted(entries);need(all(a[1]<=b[0] for a,b in zip(ordered,ordered[1:])),'overlapping FIP entries')
    need(entries[-1][0]==0x2000,'HDR2 FIP entry')
    used=entries[-1][1];need(used==max(x[1] for x in entries),'unexpected trailing FIP entry')
    need(terminator in (used,(used+1023)&~1023),'FIP terminator end offset')
    need(terminator<=len(blob),'FIP terminator outside input')
    need(not any(memoryview(blob)[used:terminator]),'nonzero FIP alignment padding')
    if terminator!=len(blob):
        tail=memoryview(blob)[terminator:]
        need(allow_erased_tail and tail[0] in (0,255) and all(x==tail[0] for x in tail),'nonuniform/unapproved slot padding')
    magic,hsize,payload,crc=struct.unpack_from('<4I',blob,0x2000)
    fit=memoryview(blob)[0x2100:used]
    need((magic,hsize,payload)==(0x32524448,256,len(fit)+256),'HDR2 length/magic')
    need(crc==(zlib.crc32(fit)^0xffffffff),'HDR2 JAMCRC')
    nodes=fdt_nodes(fit);need('/images' in nodes and '/configurations' in nodes,'FIT structure')
    default=cstring(nodes['/configurations'].get('default',b''),'FIT default')
    conf=nodes.get('/configurations/'+default);need(conf is not None,'missing default configuration')
    need(cstring(conf.get('kernel',b''),'FIT kernel')=='kernel@1','unexpected kernel reference')
    need(cstring(conf.get('fdt',b''),'FIT FDT')=='fdt@1','unexpected FDT reference')
    need('ramdisk' not in conf,'stock ramdisk configuration unsupported')
    image_paths=[x for x in nodes if x.startswith('/images/') and x.count('/')==2]
    need(set(image_paths)=={'/images/kernel@1','/images/fdt@1','/images/filesystem@1'},'stock FIT images')
    images=[]
    for path in sorted(image_paths):
        props=nodes[path];data=props.get('data');need(data is not None and len(data)>0,'missing inline image data')
        for external in ['data-position','data-offset','data-size']:need(external not in props,'external FIT data unsupported')
        info=dict(name=path.rsplit('/',1)[1],bytes=len(data),SHA256=hashlib.sha256(data).hexdigest(),verified_hashes=[])
        for field in ['type','arch','os','compression']:
            if field in props:info[field]=cstring(props[field],'invalid image '+field)
        need(info.get('arch')=='arm64','unsupported architecture')
        expected={'kernel@1':'kernel','fdt@1':'flat_dt','filesystem@1':'filesystem'}[info['name']]
        need(info.get('type')==expected,'image type')
        for field in ['load','entry']:
            if field in props:
                need(len(props[field]) in [4,8],'load/entry size');info[field]=hex(int.from_bytes(props[field],'big'))
        for child in nodes:
            if not child.startswith(path+'/') or child.count('/')!=3:continue
            need(child.rsplit('/',1)[1].startswith('hash'),'unsupported FIT image child')
            h=nodes[child];algo=cstring(h.get('algo',b''),'hash algorithm')
            need(algo in ['sha1','sha256','sha384','sha512'],'unsupported FIT hash')
            need(bytes(h.get('value',b''))==hashlib.new(algo,data).digest(),'FIT image hash mismatch')
            info['verified_hashes'].append(algo)
        if info['name']=='kernel@1':need(info['verified_hashes'],'stock kernel hash required')
        if info['name']=='fdt@1':fdt_nodes(data)
        images.append(info)
    return dict(FIP_bytes=used,slot_padding_bytes=len(blob)-used,FIP_SHA256=hashlib.sha256(memoryview(blob)[:used]).hexdigest(),FIT_bytes=len(fit),HDR2_JAMCRC_verified=True,images=images)

def inspect_input(blob, expected_sha256, slot_backup=False):
    need(len(expected_sha256)==64 and all(x in '0123456789abcdef' for x in expected_sha256),'expected SHA256 must be lowercase hex')
    need(hashlib.sha256(blob).hexdigest()==expected_sha256,'input SHA256 differs from owner-supplied reference')
    component=blob if slot_backup else stock_component(blob)
    report=inspect_fip(component,allow_erased_tail=slot_backup)
    return report|dict(source_kind='private-local-slot-backup' if slot_backup else 'single-tclinux-stock-Web-container',
        input_bytes=len(blob),input_SHA256=expected_sha256,read_only=True,
        board_compatibility_proven=False,manufacturer_signature_verified=False,
        stock_bootability_proven=False,write_operation_available=False,
        limits=['Checks bind an exact input and its structure, not its provenance or compatibility.',
                'Existing factory-specific state is not restored by this component.',
                'A local slot backup is private input and is not a portable public recovery package.'])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path)
    p.add_argument('--sha256',required=True);p.add_argument('--local-slot-backup',action='store_true')
    a=p.parse_args();need(a.input.stat().st_size<=SLOT+65536,'input too large')
    print(json.dumps(inspect_input(a.input.read_bytes(),a.sha256,a.local_slot_backup),indent=2))
if __name__=='__main__':main()
