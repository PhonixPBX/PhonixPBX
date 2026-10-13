#!/bin/sh
# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
# QEMU boot smoke test for the pc-amd64 / pc-x86 images.
#
#   image/test-qemu.sh [--firmware uefi|bios|both] [--update] [--board pc-amd64]
#                      [--image out/phonix-<v>-<board>.img.zst] [--timeout 600]
#
# Boots a copy of the image (grown to 4 GiB to exercise the first-boot
# resize) with user networking (host port -> 443 and -> 5060/udp) and waits
# until https://localhost:<port>/login answers 200, Asterisk answers a SIP
# OPTIONS request and the boot slot was confirmed by the health check.
# With --update the image copy is booted in service mode
# (phonix.console=shell, root shell on the serial console) to install the
# update bundle into slot B, boot it, and then to install a deliberately
# broken (but correctly signed) bundle into slot A and verify that the
# trial boot fails and the system rolls back to slot B.
# Needs qemu-system-x86_64 (or -i386), OVMF for UEFI, curl, python3, openssl
# and podman/docker (mtools in the build container to edit the copy).
exec python3 "$(dirname "$0")/lib/qemutest.py" "$@"
