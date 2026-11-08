#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Per-device recovery identity/state vault. Offline format, no Flash access.

Private vaults are generated per device; they are never part of public firmware.
Full stock firmware and the complete vendor-state backup remain external owner
backups. The vault additionally preserves the small essential vendor regions.
"""
import gzip
import hashlib
import re
import struct
import zlib

MAGIC=b'DPNVLT1\0'
SIZE=0x400000
PAGE=4096
HEADER=4096
VENDOR_START=0x6480000
VENDOR_END=0xb800000
VENDOR_BYTES=VENDOR_END-VENDOR_START
ESSENTIAL_BYTES=25*1048576+0x80000
ENTRY_NAMES=('essential-state-gzip','authorized_keys','dropbear_ed25519_host_key')

def need(ok,message):
    if not ok:raise ValueError(message)
def sha(data):return hashlib.sha256(data).digest()
def fingerprint(art):
    need(len(art)==0x380000,'ART length')
    eeprom=art[0x40000:0x41e00];mac=art[0x301055:0x301066].lower()
    need(eeprom[:2]==b'\x92\x79','EEPROM chip marker')
    need(re.fullmatch(rb'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',mac),'factory MAC shape')
    raw=bytes.fromhex(mac.decode().replace(':',''))
    need(not raw[0]&1 and any(raw),'factory MAC must be unicast/nonzero')
    return sha(b'DPN-BE7200GR-factory-v1\0'+eeprom+raw)

def critical_state(vendor):
    need(len(vendor)==VENDOR_BYTES,'complete vendor state size')
    return vendor[:25*1048576]+vendor[-0x80000:]

def build(art,stock_sha,vendor,authorized_keys,host_key):
    need(len(stock_sha)==32,'stock SHA256 bytes')
    need(0<len(authorized_keys)<=16384 and b'\0' not in authorized_keys,'authorized_keys length/shape')
    need(re.search(rb'(?:ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp\d+) [A-Za-z0-9+/=]+',authorized_keys),'SSH public key required')
    need(0<len(host_key)<=4096,'host key length')
    essential=critical_state(vendor)
    objects=[gzip.compress(essential,compresslevel=9,mtime=0),authorized_keys,host_key]
    b=bytearray(b'\xff'*SIZE)
    struct.pack_into('<8sII',b,0,MAGIC,1,SIZE)
    b[16:48]=fingerprint(art);b[48:80]=stock_sha;b[80:112]=sha(vendor);b[112:144]=sha(essential)
    struct.pack_into('<4I',b,144,VENDOR_BYTES,ESSENTIAL_BYTES,3,0)
    at=HEADER
    for i,data in enumerate(objects):
        need(at+len(data)<=SIZE,'per-device vault capacity exceeded')
        struct.pack_into('<II32s',b,160+i*40,at,len(data),sha(data))
        b[at:at+len(data)]=data;at=(at+len(data)+PAGE-1)&~(PAGE-1)
    struct.pack_into('<4I',b,280,VENDOR_START,25*1048576,0xb780000,0x80000)
    b[HEADER-32:HEADER]=sha(b[:HEADER-32])
    parse(b,fingerprint(art),verify_essential=True)
    return bytes(b)

def parse(blob,expected_fingerprint,verify_essential=False):
    b=memoryview(blob);need(len(b)==SIZE,'vault size')
    need(len(expected_fingerprint)==32,'expected factory fingerprint size')
    need(bytes(b[:8])==MAGIC and struct.unpack_from('<II',b,8)==(1,SIZE),'vault magic/version')
    need(bytes(b[HEADER-32:HEADER])==sha(b[:HEADER-32]),'vault header digest')
    need(bytes(b[16:48])==expected_fingerprint,'vault belongs to another device')
    need(struct.unpack_from('<4I',b,144)==(VENDOR_BYTES,ESSENTIAL_BYTES,3,0),'vault state metadata')
    need(struct.unpack_from('<4I',b,280)==(VENDOR_START,25*1048576,0xb780000,0x80000),'essential state ranges')
    need(all(x==255 for x in b[296:HEADER-32]),'vault reserved bytes')
    at=HEADER;objects={};descriptors=[]
    for i,name in enumerate(ENTRY_NAMES):
        start,size,digest=struct.unpack_from('<II32s',b,160+i*40)
        need(start==at and 0<size<=SIZE-start,'vault object bounds/order')
        data=b[start:start+size];need(sha(data)==digest,'vault object digest')
        end=(start+size+PAGE-1)&~(PAGE-1)
        need(end<=SIZE and all(x==255 for x in b[start+size:end]),'vault object alignment padding')
        objects[name]=bytes(data);descriptors.append(dict(name=name,offset=start,bytes=size,SHA256=digest.hex()));at=end
    need(all(x==255 for x in b[at:]),'vault trailing bytes')
    need(len(objects['authorized_keys'])<=16384 and b'\0' not in objects['authorized_keys'],'vault authorized_keys')
    need(len(objects['dropbear_ed25519_host_key'])<=4096,'vault host key')
    if verify_essential:
        obj=zlib.decompressobj(16+zlib.MAX_WBITS)
        plain=obj.decompress(objects['essential-state-gzip'],ESSENTIAL_BYTES+1)
        need(len(plain)==ESSENTIAL_BYTES and obj.eof and not obj.unused_data and not obj.unconsumed_tail,'essential state gzip size/termination')
        need(sha(plain)==bytes(b[112:144]),'essential state plain digest')
    return dict(factory_fingerprint=bytes(b[16:48]).hex(),original_stock_SHA256=bytes(b[48:80]).hex(),
                full_external_vendor_state_SHA256=bytes(b[80:112]).hex(),essential_plain_SHA256=bytes(b[112:144]).hex(),
                essential_plain_digest_verified=verify_essential,objects=objects,descriptors=descriptors,
                full_vendor_state_external_backup_required=True)
