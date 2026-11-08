# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic parser tests; no private firmware fixture or device is required."""
import hashlib
import struct
import unittest
import zlib
from inspect_image import inspect_input, InvalidImage, fdt_nodes, stock_component

def tree(node):
    names=bytearray(); offsets={}; structure=bytearray()
    def word(n):structure.extend(struct.pack('>I',n))
    def padded(b):structure.extend(b);structure.extend(bytes((-len(structure))%4))
    def emit(name,props,children):
        word(1);padded(name.encode()+b'\0')
        for key,value in props.items():
            if key not in offsets:offsets[key]=len(names);names.extend(key.encode()+b'\0')
            word(3);word(len(value));word(offsets[key]);padded(value)
        for child in children:emit(*child)
        word(2)
    emit(*node);word(9)
    return struct.pack('>10I',0xd00dfeed,56+len(structure)+len(names),56,56+len(structure),40,17,16,0,len(names),len(structure))+bytes(16)+structure+names

def fixture():
    dt=tree(('',{},[]));kernel=b'synthetic kernel';fs=b'synthetic filesystem'
    images=[]
    for name,kind,data in [('kernel@1','kernel',kernel),('fdt@1','flat_dt',dt),('filesystem@1','filesystem',fs)]:
        hashes=[('hash@1',{'algo':b'sha1\0','value':hashlib.sha1(data).digest()},[])] if kind=='kernel' else []
        images.append((name,{'type':kind.encode()+b'\0','arch':b'arm64\0','data':data},hashes))
    fit=tree(('',{},[('images',{},images),('configurations',{'default':b'conf@1\0'},[('conf@1',{'kernel':b'kernel@1\0','fdt':b'fdt@1\0'},[])])]))
    b=bytearray(0x2100+len(fit));struct.pack_into('<I',b,0,0xaa640001)
    for i,(start,size) in enumerate([(0x400,16),(0x1000,16),(0x1800,16),(0x2000,256+len(fit))]):
        struct.pack_into('<16sQQQ',b,16+40*i,bytes([i+1])*16,start,size,0)
    struct.pack_into('<16sQQQ',b,176,bytes(16),len(b),0,0)
    struct.pack_into('<4I',b,0x2000,0x32524448,256,len(fit)+256,zlib.crc32(fit)^0xffffffff)
    b[0x2100:]=fit;return b

def container(payload,kind=b'tclinux'):
    b=bytearray(404+len(payload));b[:5]=b'UMMtk';b[264:264+len(kind)]=kind
    b[404:]=payload;b[128:144]=b[328:344]=hashlib.md5(payload).digest()
    struct.pack_into('>II',b,192,len(b),1);struct.pack_into('>III',b,392,404,len(b)-1,len(payload));return b

class InspectionTests(unittest.TestCase):
    def check(self,b,backup=True):return inspect_input(b,hashlib.sha256(b).hexdigest(),backup)
    def test_valid_raw_and_web(self):
        b=fixture();r=self.check(b);self.assertFalse(r['write_operation_available'])
        self.assertEqual(self.check(container(b),False)['FIP_SHA256'],r['FIP_SHA256'])
    def test_pinned_digest(self):
        with self.assertRaises(InvalidImage):inspect_input(fixture(),'0'*64,True)
    def test_crc_corruption(self):
        b=fixture();b[-1]^=1
        with self.assertRaises(InvalidImage):self.check(b)
    def test_kernel_hash_even_with_recomputed_crc(self):
        b=fixture();b[b.index(b'synthetic kernel')]^=1
        struct.pack_into('<I',b,0x200c,zlib.crc32(b[0x2100:])^0xffffffff)
        with self.assertRaisesRegex(InvalidImage,'hash mismatch'):self.check(b)
    def test_overlap(self):
        b=fixture();struct.pack_into('<Q',b,56+16,0x400)
        with self.assertRaisesRegex(InvalidImage,'overlapping'):self.check(b)
    def test_padding_requires_explicit_backup(self):
        b=fixture()+bytes(256);self.check(b)
        with self.assertRaises(InvalidImage):self.check(container(b),False)
        b[-1]=1
        with self.assertRaises(InvalidImage):self.check(b)
    def test_no_bootloader_write_target(self):
        with self.assertRaisesRegex(InvalidImage,'write targets'):stock_component(container(fixture(),b'tcboot'))
    def test_container_md5_and_truncation(self):
        b=container(fixture());b[-1]^=1
        with self.assertRaises(InvalidImage):stock_component(b)
        with self.assertRaises(InvalidImage):stock_component(b[:-1])
    def test_fdt_truncated_and_bad_offset(self):
        b=bytearray(tree(('',{},[])))
        with self.assertRaises(InvalidImage):fdt_nodes(b[:-1])
        struct.pack_into('>I',b,8,len(b)+4)
        with self.assertRaises(InvalidImage):fdt_nodes(b)

if __name__=='__main__':unittest.main()
