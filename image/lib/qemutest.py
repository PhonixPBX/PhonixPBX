#!/usr/bin/env python3
"""QEMU boot / update / rollback test for PhonixPBX PC images (see image/test-qemu.sh)."""

from __future__ import annotations

import argparse
import functools
import glob
import http.server
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

TOP = Path(__file__).resolve().parents[2]
WORK = TOP / "image" / "work" / "qemu"
OVMF_CODE = ["/usr/share/OVMF/OVMF_CODE_4M.fd", "/usr/share/OVMF/OVMF_CODE.fd", "/usr/share/ovmf/OVMF.fd"]
OVMF_VARS = ["/usr/share/OVMF/OVMF_VARS_4M.fd", "/usr/share/OVMF/OVMF_VARS.fd"]
BOOT_OFFSET = 1024 * 1024  # PHXBOOT starts at sector 2048


def log(msg: str) -> None:
    print(f"[test-qemu {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def free_port(kind: int = socket.SOCK_STREAM) -> int:
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def container_tool() -> str:
    return os.environ.get("CONTAINER") or ("podman" if shutil.which("podman") else "docker")


def in_builder(*cmd: str) -> None:
    """Run a command in the image build container with the repository at /src."""
    subprocess.run(
        [
            container_tool(),
            "run",
            "--rm",
            "-v",
            f"{TOP}:/src:z",
            "-e",
            "MTOOLS_SKIP_CHECK=1",
            "phonix-imgbuild:3.24",
            *cmd,
        ],
        check=True,
    )


class Vm:
    def __init__(self, disk: Path, firmware: str, arch: str, name: str):
        self.disk, self.firmware, self.arch, self.name = disk, firmware, arch, name
        self.https = free_port()
        self.sip = free_port(socket.SOCK_DGRAM)
        self.sock_path = Path(tempfile.mkdtemp(prefix="phonix-qemu-")) / "serial.sock"
        self.logfile = WORK / f"serial-{name}.log"
        self.buf = ""
        self.offset = 0
        self.proc: subprocess.Popen[bytes] | None = None
        self.conn: socket.socket | None = None
        self.lock = threading.Lock()
        self.reader: threading.Thread | None = None

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        qemu = "qemu-system-x86_64" if self.arch == "x86_64" else "qemu-system-i386"
        cmd = [
            qemu,
            "-m",
            "1536",
            "-smp",
            "2",
            "-display",
            "none",
            "-name",
            self.name,
            "-drive",
            f"file={self.disk},format=raw,if=virtio",
            "-netdev",
            f"user,id=n0,hostfwd=tcp:127.0.0.1:{self.https}-:443,hostfwd=udp:127.0.0.1:{self.sip}-:5060",
            "-device",
            "virtio-net-pci,netdev=n0",
            "-serial",
            f"unix:{self.sock_path},server=on,wait=on",
            "-monitor",
            "none",
        ]
        if os.access("/dev/kvm", os.W_OK):
            cmd += ["-enable-kvm", "-cpu", "host"]
        if self.firmware == "uefi":
            code = next(p for p in OVMF_CODE if os.path.exists(p))
            vars_src = next((p for p in OVMF_VARS if os.path.exists(p)), None)
            if code.endswith("OVMF.fd") or vars_src is None:
                cmd += ["-bios", code]
            else:
                vars_copy = WORK / f"vars-{self.name}.fd"
                shutil.copyfile(vars_src, vars_copy)
                cmd += [
                    "-drive",
                    f"if=pflash,format=raw,readonly=on,file={code}",
                    "-drive",
                    f"if=pflash,format=raw,file={vars_copy}",
                ]
        log(f"starting {self.name}: https://localhost:{self.https}/ sip udp/{self.sip} ({self.firmware})")
        self.logfh = open(self.logfile, "w")  # noqa: SIM115
        self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL)
        for _ in range(100):
            try:
                c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                c.connect(str(self.sock_path))
                self.conn = c
                break
            except OSError:
                time.sleep(0.1)
        if self.conn is None:
            raise RuntimeError("cannot connect to the serial console")
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self) -> None:
        assert self.conn
        while True:
            try:
                data = self.conn.recv(4096)
            except OSError:
                return
            if not data:
                return
            text = data.decode("utf-8", "replace").replace("\r", "")
            with self.lock:
                self.buf += text
            self.logfh.write(text)
            self.logfh.flush()

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.conn:
            self.conn.close()

    # ------------------------------------------------------------ console
    def mark(self) -> None:
        """Only look at console output produced after this point."""
        with self.lock:
            self.offset = len(self.buf)

    def wait_for(self, pattern: str, timeout: float) -> re.Match[str]:
        rx = re.compile(pattern)
        end = time.time() + timeout
        while time.time() < end:
            with self.lock:
                m = rx.search(self.buf, self.offset)
            if m:
                return m
            if self.proc and self.proc.poll() is not None:
                raise RuntimeError(f"QEMU exited while waiting for {pattern!r}")
            time.sleep(0.5)
        raise TimeoutError(f"timeout waiting for {pattern!r} (see {self.logfile})")

    def send(self, text: str) -> None:
        assert self.conn
        self.conn.sendall(text.encode())

    _n = 0

    def sh(self, command: str, timeout: float = 120) -> tuple[int, str]:
        """Run a command in the service shell on the serial console."""
        Vm._n += 1
        tag = f"__PHONIX_{Vm._n}__"
        self.mark()
        start = len(self.buf)
        self.send(f"{command}; echo {tag} $?\n")
        m = self.wait_for(re.escape(tag) + r" (\d+)", timeout)
        with self.lock:
            out = self.buf[start : m.start()]
        self.offset = m.end()
        return int(m.group(1)), out

    # ------------------------------------------------------------ checks
    def https_status(self, path: str = "/login") -> int | None:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            with urllib.request.urlopen(f"https://localhost:{self.https}{path}", context=ctx, timeout=5) as r:
                return int(r.status)
        except urllib.error.HTTPError as exc:
            return int(exc.code)
        except OSError:
            return None

    def sip_options(self) -> str | None:
        branch = f"z9hG4bK{int(time.time() * 1000)}"
        msg = (
            f"OPTIONS sip:ping@127.0.0.1 SIP/2.0\r\n"
            f"Via: SIP/2.0/UDP 127.0.0.1:5999;branch={branch};rport\r\n"
            f"Max-Forwards: 70\r\nTo: <sip:ping@127.0.0.1>\r\n"
            f"From: <sip:test@127.0.0.1>;tag=phonix\r\nCall-ID: {branch}@phonix-test\r\n"
            f"CSeq: 1 OPTIONS\r\nContent-Length: 0\r\n\r\n"
        )
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(3)
            try:
                s.sendto(msg.encode(), ("127.0.0.1", self.sip))
                data, _ = s.recvfrom(4096)
            except OSError:
                return None
        first = data.decode("utf-8", "replace").split("\r\n", 1)[0]
        return first if first.startswith("SIP/2.0") else None

    def wait_healthy(self, timeout: float, slot: str) -> None:
        end = time.time() + timeout
        web = sip = None
        while time.time() < end:
            if web != 200:
                web = self.https_status("/login")
            if not sip:
                sip = self.sip_options()
            if web == 200 and sip:
                break
            if self.proc and self.proc.poll() is not None:
                raise RuntimeError("QEMU exited")
            time.sleep(3)
        log(f"  https /login -> {web}")
        log(f"  SIP OPTIONS  -> {sip}")
        if web != 200 or not sip:
            raise RuntimeError(f"system did not come up (web={web}, sip={sip}); see {self.logfile}")
        m = self.wait_for(r"phonix: boot slot ([AB]) marked good[^\n]*", max(60.0, end - time.time()))
        log(f"  healthcheck  -> {m.group(0).strip()}")
        if m.group(1) != slot:
            raise RuntimeError(f"expected slot {slot}, booted {m.group(1)}")


# ---------------------------------------------------------------- image prep
def prepare_disk(image: Path, name: str, size_gb: int, service_shell: bool) -> Path:
    WORK.mkdir(parents=True, exist_ok=True)
    disk = WORK / f"{name}.img"
    log(f"preparing {disk} from {image.name}")
    if image.suffix == ".zst":
        subprocess.run(["zstd", "-q", "-d", "-f", str(image), "-o", str(disk)], check=True)
    else:
        shutil.copyfile(image, disk)
    with open(disk, "r+b") as fh:
        fh.truncate(size_gb * 1024**3)
    # loglevel=7: the "marked good" boot marker is logged at info level (kept
    # off the console of a production box), the tests wait for it on the
    # serial console
    rel = disk.relative_to(TOP)
    script = (
        f"set -e; img=/src/{rel}@@{BOOT_OFFSET}; "
        "mcopy -n -i $img ::/grub/grub.cfg /tmp/g; "
        "sed -i 's/loglevel=6/loglevel=7/' /tmp/g; grep -q loglevel=7 /tmp/g; "
    )
    if service_shell:
        script += (
            "sed -i 's/phonix.trial=${t}/phonix.trial=${t} phonix.console=shell/' /tmp/g; "
            "grep -q phonix.console=shell /tmp/g; "
        )
    script += "mcopy -o -i $img /tmp/g ::/grub/grub.cfg"
    in_builder("sh", "-c", script)
    return disk


def make_broken_bundle(board: str, version: str, key: Path, out: Path) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="phonix-broken-"))
    payload = WORK / f"broken-{board}"
    shutil.rmtree(payload, ignore_errors=True)
    payload.mkdir(parents=True)
    # take kernel + initramfs from the real image's work dir, garbage rootfs
    parts = TOP / "image" / "work" / board / "parts" / "payload"
    shutil.copyfile(parts / "vmlinuz", payload / "vmlinuz")
    shutil.copyfile(parts / "initramfs", payload / "initramfs")
    (payload / "rootfs.squashfs").write_bytes(os.urandom(4 * 1024 * 1024))
    subprocess.run(
        [str(TOP / "image" / "mkbundle.sh"), board, f"{version}-broken", str(payload), str(key), str(out)], check=True
    )
    shutil.rmtree(tmp, ignore_errors=True)


class Server(threading.Thread):
    def __init__(self, directory: Path):
        super().__init__(daemon=True)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
        handler.log_message = lambda *a, **k: None  # type: ignore[method-assign]
        self.httpd = http.server.ThreadingHTTPServer(("0.0.0.0", 0), handler)  # noqa: S104 - QEMU guest fetches from the host
        self.port = self.httpd.server_address[1]

    def run(self) -> None:
        self.httpd.serve_forever()


# ---------------------------------------------------------------- tests
def boot_test(image: Path, board: str, firmware: str, timeout: float) -> None:
    arch = "i386" if board == "pc-x86" else "x86_64"
    disk = prepare_disk(image, f"{board}-{firmware}", 4, service_shell=False)
    vm = Vm(disk, firmware, arch, f"{board}-{firmware}")
    try:
        vm.start()
        vm.wait_for(r"phonix-init: booting slot A", 120)
        log("  initramfs running")
        vm.wait_healthy(timeout, "A")
        log(f"PASS boot test {board} ({firmware})")
    finally:
        vm.stop()


def update_test(image: Path, board: str, firmware: str, timeout: float, bundle: Path, key: Path) -> None:
    arch = "i386" if board == "pc-x86" else "x86_64"
    name = f"{board}-{firmware}-update"
    disk = prepare_disk(image, name, 4, service_shell=True)
    broken = WORK / f"{board}-broken.update"
    version = bundle.name.removeprefix("phonix-").removesuffix(f"-{board}.update")
    make_broken_bundle(board, version, key, broken)
    serve = WORK / "serve"
    shutil.rmtree(serve, ignore_errors=True)
    serve.mkdir()
    os.link(bundle, serve / "good.update") if bundle.stat().st_dev == serve.stat().st_dev else shutil.copyfile(
        bundle, serve / "good.update"
    )
    shutil.move(str(broken), serve / "broken.update")
    srv = Server(serve)
    srv.start()

    vm = Vm(disk, firmware, arch, name)
    priv = "/usr/libexec/phonix/priv"
    try:
        vm.start()
        vm.wait_healthy(timeout, "A")
        vm.send("\n")
        vm.wait_for(r"service shell|# $", 30)

        log("installing the update bundle into slot B")
        rc, out = vm.sh(f"wget -q -O /data/update.bundle http://10.0.2.2:{srv.port}/good.update", 300)
        assert rc == 0, out
        rc, out = vm.sh(f"{priv} install-update /data/update.bundle", 600)
        log("  " + out.strip().splitlines()[-1])
        assert rc == 0 and "slot B" in out, out
        rc, out = vm.sh(f"{priv} boot-status")
        assert "pending_trial=B" in out, out
        vm.mark()
        vm.send("rm -f /data/update.bundle; reboot\n")
        vm.wait_for(r"phonix-init: booting slot B \(trial\)", 180)
        log("  rebooted into slot B (trial)")
        vm.wait_healthy(timeout, "B")
        vm.wait_for(r"update confirmed", 30)
        vm.send("\n")
        time.sleep(2)
        rc, out = vm.sh(f"{priv} boot-status")
        assert "permanent=B" in out and "trial=0" in out, out
        log("PASS update A -> B")

        log("installing a broken (signed) bundle into slot A")
        rc, out = vm.sh(f"wget -q -O /data/update.bundle http://10.0.2.2:{srv.port}/broken.update", 300)
        assert rc == 0, out
        rc, out = vm.sh(f"{priv} install-update /data/update.bundle", 600)
        assert rc == 0, out
        vm.mark()
        vm.send("rm -f /data/update.bundle; reboot\n")
        vm.wait_for(r"phonix-init: booting slot A \(trial\)", 180)
        vm.wait_for(r"rebooting into the previous slot", 120)
        log("  trial boot of slot A failed as expected, rolling back")
        vm.wait_for(r"phonix-init: booting slot B\n", 180)
        vm.wait_healthy(timeout, "B")
        vm.send("\n")
        time.sleep(2)
        rc, out = vm.sh(f"{priv} boot-status")
        assert "permanent=B" in out and "current=B" in out, out
        log("PASS rollback after failed trial boot")
    finally:
        vm.stop()
        srv.httpd.shutdown()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--board", default="pc-amd64", choices=["pc-amd64", "pc-x86"])
    ap.add_argument("--firmware", default="both", choices=["uefi", "bios", "both"])
    ap.add_argument("--image")
    ap.add_argument("--bundle")
    ap.add_argument(
        "--key",
        default=os.environ.get("PHONIX_UPDATE_SIGNING_KEY", str(TOP / "image" / "keys" / "update-signing.pem")),
    )
    ap.add_argument("--update", action="store_true", help="also test update and rollback")
    ap.add_argument("--timeout", type=float, default=600)
    args = ap.parse_args()

    def newest(pattern: str) -> Path:
        found = sorted(glob.glob(str(TOP / "out" / pattern)), key=os.path.getmtime)
        if not found:
            sys.exit(f"no {pattern} in out/ - run image/build.sh {args.board}")
        return Path(found[-1])

    image = Path(args.image) if args.image else newest(f"phonix-*-{args.board}.img.zst")
    firmwares = ["uefi", "bios"] if args.firmware == "both" else [args.firmware]
    if args.board == "pc-x86":
        firmwares = ["bios"]
    for fw in firmwares:
        boot_test(image, args.board, fw, args.timeout)
    if args.update:
        bundle = Path(args.bundle) if args.bundle else newest(f"phonix-*-{args.board}.update")
        update_test(image, args.board, firmwares[0], args.timeout, bundle, Path(args.key))
    log("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
