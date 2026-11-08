#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Decrypt a NAND backup to a hash stream; never write plaintext to disk."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def verify(receipt, age, identity):
    meta = json.loads(receipt.read_text())
    expected = {"ecc": 536870912, "raw": 570425344}[meta["mode"]]
    if meta["plaintext_bytes"] != expected:
        raise ValueError("Unexpected NAND backup size")
    encrypted = Path(meta["encrypted_file"])
    digest = hashlib.sha256()
    with encrypted.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    if digest.hexdigest() != meta["encrypted_SHA256"]:
        raise ValueError("Encrypted backup digest mismatch")
    digest = hashlib.sha256()
    count = 0
    process = subprocess.Popen(
        [age, "--decrypt", "--identity", str(identity), str(encrypted)],
        stdout=subprocess.PIPE,
    )
    try:
        while block := process.stdout.read(1024 * 1024):
            count += len(block)
            if count > expected:
                raise ValueError("Decrypted backup exceeds NAND size")
            digest.update(block)
        if process.wait(timeout=30):
            raise ValueError("Backup authentication/decryption failed")
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.kill()
            process.wait()
    if count != expected or digest.hexdigest() != meta["plaintext_SHA256"]:
        raise ValueError("Decrypted backup size/digest mismatch")
    result = dict(
        mode=meta["mode"], plaintext_bytes=count,
        plaintext_SHA256=digest.hexdigest(),
        encrypted_SHA256=meta["encrypted_SHA256"],
        session_nonce=meta["session_nonce"],
        age_decryption_verified=True, plaintext_written_to_disk=False,
    )
    output = receipt.with_name(receipt.stem + "-verified.json")
    with output.open("x") as dest:
        output.chmod(0o600)
        json.dump(result, dest, indent=2)
        dest.write("\n")
    print("NAND_BACKUP_DECRYPT_VERIFIED", meta["mode"], count)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--age", required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("receipt", type=Path, nargs="+")
    args = parser.parse_args()
    for receipt in args.receipt:
        verify(receipt, args.age, args.identity)
