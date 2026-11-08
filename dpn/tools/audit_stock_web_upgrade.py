#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only UMMtk inspector and optional offline vendor/QEMU fixture checks.

Never uploads anything. Test containers contain only synthetic text bytes and
live in a temporary directory; no installable router image is generated.
"""
import argparse
import hashlib
import json
import struct
import subprocess
import tempfile
from pathlib import Path

HEADER = 200
ENTRY = 204
ALLOWED = {"oneimage", "verinfo", "tcboot", "tclinux", "um_ext"}


def u32(b, off):
    return struct.unpack_from(">I", b, off)[0]


def text(b):
    return b.split(b"\0", 1)[0].decode("ascii", errors="replace")


def inspect(b):
    if len(b) <= HEADER:
        raise ValueError("input must exceed 200 bytes")
    if b[:5] != b"UMMtk":
        raise ValueError("bad UMMtk prefix")
    total, count = u32(b, 192), u32(b, 196)
    payload_start = HEADER + ENTRY * count
    if not payload_start <= total <= len(b):
        raise ValueError("invalid header/table/total length")
    if hashlib.md5(b[payload_start:total]).digest() != b[128:144]:
        raise ValueError("whole payload MD5 mismatch")
    parts = []
    for i in range(count):
        d = HEADER + ENTRY * i
        start, end, size = struct.unpack_from(">III", b, d + 192)
        name, magic = text(b[d:d+64]), text(b[d+64:d+128])
        if not (start < end and end < len(b) and size <= len(b)
                and end-start+1 == size and start+size <= len(b)):
            raise ValueError(f"part {i}: invalid range")
        if magic.lower() not in ALLOWED:
            raise ValueError(f"part {i}: unsupported magic {magic!r}")
        if hashlib.md5(b[start:start+size]).digest() != b[d+128:d+144]:
            raise ValueError(f"part {i}: MD5 mismatch")
        parts.append(dict(name=name, magic=magic, start=start, end_inclusive=end,
                          bytes=size, md5_valid=True))
    if payload_start + sum(p["bytes"] for p in parts) != total:
        raise ValueError("sum of component lengths differs from declared total")
    return dict(input_bytes=len(b), declared_bytes=total, count=count,
                payload_start=payload_start, trailing_bytes=len(b)-total,
                payload_md5_valid=True, parts=parts,
                limits="Static reconstruction for sane bounded inputs; not a memory-safety emulator or signing check.")


def fixture(magic="tclinux", data=None):
    # This is deliberately NOT firmware, and is never saved as an artifact.
    if data is None:
        data = b"OFFLINE SYNTHETIC TEXT; NOT ROUTER FIRMWARE\n" * 4
    b = bytearray(HEADER + ENTRY + len(data))
    b[:5] = b"UMMtk"
    b[200:200+12] = b"fixture-name"
    b[264:264+len(magic)] = magic.encode()
    b[328:344] = hashlib.md5(data).digest()
    struct.pack_into(">III", b, 392, 404, len(b)-1, len(data))
    struct.pack_into(">II", b, 192, len(b), 1)
    b[404:] = data
    b[128:144] = hashlib.md5(data).digest()
    return b


def run_checks(rootfs, qemu, harness):
    lib = rootfs / "lib/libumlib_devctl.so"
    if hashlib.sha256(lib.read_bytes()).hexdigest() != "72de151857ae1a36b3d1aa2f6ec2109a47bbae7fd308cd75ee083e5877c468dc":
        raise ValueError("vendor library differs from the audited build; function offsets are unsafe to reuse")
    base = fixture()
    cases = [("valid", base, 0), ("trailing_input_accepted", base+b"TRAILER", 0)]
    for name, offset, expected in [
        ("bad_prefix", 0, 9851), ("bad_payload", 410, 9851),
        ("bad_global_md5", 128, 9851), ("bad_part_md5", 328, 9851),
        ("name_unchecked", 200, 0), ("header_reserved_unchecked", 64, 0),
        ("digest_padding_unchecked", 144, 0), ("end_range_mismatch", 399, 9851),
    ]:
        b = bytearray(base); b[offset] ^= 1; cases.append((name, b, expected))
    for magic, expected in [("TCLINUX", 0), ("tcboot", 0), ("oneimage", 0),
                            ("um_ext", 0), ("verinfo", 0), ("osgi", 9851),
                            ("arbitrary", 9851)]:
        cases.append(("magic_"+magic, fixture(magic), expected))
    results = []
    with tempfile.TemporaryDirectory(prefix="ummtk-offline-", dir="/dev/shm") as td:
        path = Path(td)/"synthetic-only.bin"
        for name, b, expected in cases:
            path.write_bytes(b)
            p = subprocess.run([str(qemu), str(harness), str(lib), str(path)],
                               capture_output=True, text=True, timeout=10)
            marker = f"VALIDATE_RC {expected}"
            passed = p.returncode == 0 and marker in p.stdout
            try:
                inspect(b)
                inspector_accepted = True
            except ValueError:
                inspector_accepted = False
            passed &= inspector_accepted == (expected == 0)
            results.append(dict(name=name, expected_vendor_rc=expected,
                                inspector_accepted=inspector_accepted,
                                passed=passed, stdout=p.stdout if not passed else None,
                                stderr=p.stderr if p.returncode else None))
        for magic in ["tclinux", "oneimage"]:
            path.write_bytes(fixture(magic))
            for slot in [0, 1]:
                p = subprocess.run([str(qemu), str(harness), str(lib), str(path), f"write:{slot}"],
                                   capture_output=True, text=True, timeout=10)
                target = "tclinux_slave" if slot else "tclinux"
                passed = p.returncode == 0 and "VALIDATE_RC 0" in p.stdout
                if magic == "tclinux":
                    passed &= f"WRITE_STUB partition={target}" in p.stdout
                    passed &= f"COMMAND_STUB echo {slot} > /tmp/image_boot_flag" in p.stdout
                else:
                    passed &= "writes=0 commands=2" in p.stdout
                    passed &= "ecnt_sys set bootflag" not in p.stdout
                results.append(dict(name=f"dispatch_{magic}_slot{slot}", passed=bool(passed),
                                    stdout=p.stdout, stderr=p.stderr if p.returncode else None))
        httpd = rootfs / "usr/sbin/httpd"
        if hashlib.sha256(httpd.read_bytes()).hexdigest() != "35b979c2762d5f929ce6a7c1b955388ea498c4d06719cfa44961fef18d41e708":
            raise ValueError("httpd differs from the audited build")
        path.write_bytes(base)
        p = subprocess.run([str(qemu), str(harness), str(lib), str(path), "write:1", "fail"],
                           capture_output=True, text=True, timeout=10)
        results.append(dict(name="writer_helper_failure_not_checked",
                            passed=p.returncode == 0 and "WRITE_DISPATCH_RC 0" in p.stdout
                            and "COMMAND_STUB echo 1 > /tmp/image_boot_flag" in p.stdout,
                            stdout=p.stdout, stderr=p.stderr if p.returncode else None))
        path.write_bytes(base)
        for current, rc, upload_type, target in [(0, 0, 3, 1), (1, 0, 3, 0),
                                                (0, -1, 3, 0), (0, -1, 8, 1)]:
            p = subprocess.run([str(qemu), str(harness), str(httpd), str(path),
                                f"post:{current}:{rc}:{upload_type}"],
                               capture_output=True, text=True, timeout=10)
            results.append(dict(name=f"http_post_current{current}_rc{rc}_type{upload_type}",
                                passed=p.returncode == 0 and f"HTTP_TARGET slot={target}" in p.stdout
                                and "REBOOT_STUB" in p.stdout,
                                stdout=p.stdout, stderr=p.stderr if p.returncode else None))
        for new, old, expected in [("1.1", "1.2", 9849), ("1.2", "1.2", 0),
                                   ("1.3", "1.2", 0), (None, "1.2", 0)]:
            path.write_bytes(fixture("verinfo", new.encode()) if new else base)
            p = subprocess.run([str(qemu), str(harness), str(httpd), str(path), "version:"+old],
                               capture_output=True, text=True, timeout=10)
            results.append(dict(name=f"version_new{new}_current{old}",
                                passed=p.returncode == 0 and f"VERSION_RC {expected}" in p.stdout,
                                stdout=p.stdout, stderr=p.stderr if p.returncode else None))
    return dict(library_sha256=hashlib.sha256(lib.read_bytes()).hexdigest(),
                httpd_sha256=hashlib.sha256(httpd.read_bytes()).hexdigest(),
                tests=results, all_passed=all(r["passed"] for r in results),
                actual_vendor_validation_executed=True,
                actual_vendor_write_dispatch_executed=True,
                mtd_writer_replaced_with_recording_stub=True,
                external_commands_stubbed=True, device_access=False,
                note="Tests exercise vendor AArch64 code under QEMU with inert imports; not a hardware write/boot test.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", nargs="?", type=Path)
    ap.add_argument("--rootfs", type=Path)
    ap.add_argument("--qemu", type=Path)
    ap.add_argument("--harness", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if args.rootfs:
        if not args.qemu or not args.harness:
            ap.error("--rootfs requires --qemu and --harness")
        report = run_checks(args.rootfs, args.qemu, args.harness)
    elif args.image:
        report = inspect(args.image.read_bytes())
    else:
        ap.error("provide image or --rootfs/--qemu/--harness")
    s = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text(s)
    print(s)
    if report.get("all_passed") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
