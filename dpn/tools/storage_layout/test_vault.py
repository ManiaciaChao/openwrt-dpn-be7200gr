# SPDX-License-Identifier: GPL-2.0-only
import hashlib
import struct
import unittest
from vault import build,parse,fingerprint,VENDOR_BYTES,HEADER

def art():
    b=bytearray(0x380000);b[0x40000:0x40002]=b'\x92\x79'
    b[0x301055:0x301066]=b'02:00:00:00:00:01';return b

class VaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.art=art();cls.fp=fingerprint(cls.art)
        cls.image=build(cls.art,b'S'*32,bytes(VENDOR_BYTES),b'ssh-ed25519 Tk9UX0FfUkVBTF9LRVk= synthetic-only\n',b'NOT_A_REAL_PRIVATE_HOST_KEY')
    def test_roundtrip_and_auth_extraction(self):
        p=parse(self.image,self.fp,True);self.assertTrue(p['essential_plain_digest_verified'])
        self.assertEqual(p['objects']['dropbear_ed25519_host_key'],b'NOT_A_REAL_PRIVATE_HOST_KEY')
    def test_wrong_device(self):
        with self.assertRaisesRegex(ValueError,'another device'):parse(self.image,b'x'*32)
    def test_header_corruption(self):
        b=bytearray(self.image);b[112]^=1
        with self.assertRaisesRegex(ValueError,'header digest'):parse(b,self.fp)
    def test_payload_corruption(self):
        b=bytearray(self.image);b[HEADER+20]^=1
        with self.assertRaisesRegex(ValueError,'object digest'):parse(b,self.fp)
    def test_bounds_even_with_new_header_digest(self):
        b=bytearray(self.image);struct.pack_into('<I',b,160,HEADER-1)
        b[HEADER-32:HEADER]=hashlib.sha256(b[:HEADER-32]).digest()
        with self.assertRaisesRegex(ValueError,'bounds/order'):parse(b,self.fp)
    def test_nonempty_tail_and_truncation(self):
        b=bytearray(self.image);b[-1]=0
        with self.assertRaisesRegex(ValueError,'trailing'):parse(b,self.fp)
        with self.assertRaisesRegex(ValueError,'vault size'):parse(b[:-1],self.fp)
    def test_bootflag_does_not_change_factory_identity(self):
        b=bytearray(self.art);before=fingerprint(b);b[0x340000]=ord('1')
        self.assertEqual(fingerprint(b),before)

if __name__=='__main__':unittest.main()
