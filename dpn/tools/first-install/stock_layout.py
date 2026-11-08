# SPDX-License-Identifier: GPL-2.0-only
"""Locate stock ART by name and geometry, independently of child enumeration."""
import re

def find_art(table: bytes) -> str:
 if len(table)>65536:raise ValueError('Unexpectedly large stock partition table')
 matches=re.findall(rb'^(mtd[0-9]+): ([0-9a-fA-F]+) ([0-9a-fA-F]+) "art"$',table,re.M)
 if len(matches)!=1:raise ValueError('Require one unambiguous named ART partition')
 device,size,erase=matches[0]
 if int(size,16)!=0x380000 or int(erase,16)!=0x40000:raise ValueError('Unsupported ART partition geometry')
 return device.decode('ascii')
