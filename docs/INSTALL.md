# Installing PhonixPBX

PhonixPBX ships as a complete disk image for three boards:

| Board | Image | Hardware |
|---|---|---|
| `rpi-arm64` | `phonix-<version>-rpi-arm64.img.zst` | Raspberry Pi 3B+, 4, 400, 5, Zero 2 W (64-bit) |
| `pc-amd64` | `phonix-<version>-pc-amd64.img.zst` | 64-bit PCs, servers and VMs; UEFI or legacy BIOS |
| `pc-x86` | `phonix-<version>-pc-x86.img.zst` | 32-bit PCs, legacy BIOS only. Best effort. |

Each release also includes a signed update bundle per board, `phonix-<version>-<board>.update`, and a `SHA256SUMS` file.

Downloads are on the GitHub releases page:

- **Releases** (`v*` tags) are the versions to install.
- **Nightly** (pre-release tagged `nightly`) is rebuilt from the default branch on every push. It is for testing only, and its assets are replaced each time.

The image needs at least a 2 GB card or disk. Use 8 GB or more if you plan to keep voicemail and recordings. Check the download first:

```sh
sha256sum -c SHA256SUMS --ignore-missing
```

## 1. Write the image

The image holds four partitions. The last one, `PHXDATA`, is enlarged to fill the whole card or disk on first boot.

### Raspberry Pi Imager (Windows, macOS, Linux)

1. Open Raspberry Pi Imager and pick your Pi model.
2. For the operating system choose **Use custom** and select `phonix-<version>-rpi-arm64.img.zst`. Imager decompresses `.zst` files itself.
3. Pick the SD card or USB drive and write it.
4. If Imager offers OS customisation (user name, Wi-Fi, SSH), choose **No**. PhonixPBX does not use these settings.

You can write PC images with Imager too: choose *Use custom* and write to a USB stick or disk.

### dd (Linux, macOS)

```sh
# find the device first (lsblk / diskutil list) - everything on it is erased!
zstd -dc phonix-<version>-pc-amd64.img.zst | sudo dd of=/dev/sdX bs=4M conv=fsync status=progress
```

On macOS, write to `/dev/rdiskN` and leave out `status=progress` and `conv=fsync`.

For a virtual machine:
- Decompress the image with `zstd -d`.
- Attach the `.img` as a raw disk, or convert it: `qemu-img convert -O qcow2 phonix.img phonix.qcow2`.
- Enlarge the virtual disk to the size you want. The first boot grows the data partition into the free space.
- Use a virtio or SATA disk and one network card. UEFI and BIOS firmware both work.

## 2. First boot

1. Connect the network cable. The first network card, `eth0`, gets its address via DHCP.
2. Power on. On Wi-Fi-only boards such as the Pi Zero 2 W, a USB Ethernet adapter is needed; Wi-Fi is not supported yet.

The first boot takes 1–2 minutes. During it the system:

- enlarges the data partition
- creates the database, a self-signed HTTPS certificate and the SSH host keys
- generates a **random administrator password**

If a `config.xml` from an old AskoziaPBX is on the boot partition, it is imported automatically. The file can be at `config.xml` or `conf/config.xml`. See [Migrating](#migrating-from-askoziapbx-1x--2x).

The console (screen and serial port, 115200 baud) shows a menu with:

```
  PhonixPBX 3.0.0

  LAN (eth0, DHCP): 192.168.1.23
  Web interface: https://192.168.1.23/

  Initial login: admin / 3W7YaMJMUei5
  (you must change the password at the first login)
```

If the box has no screen, find its IP address in your router's DHCP lease list.

## 3. Log in

1. Open `https://<ip-address>/`. Port 80 redirects to HTTPS.
2. The certificate is self-signed, so the browser shows a warning the first time. Check that the address is right and accept the warning. You can upload your own certificate later under *System → General*.
3. Log in as `admin` with the password from the console. You are asked to choose a new password straight away.

If you lose the password, use the console menu: **Reset administrator password**.

### Console menu

The menu runs on the local screen (`tty1`) and on the serial console. It offers:
- show status
- set the LAN IP address (DHCP or static)
- reset the administrator password
- reboot
- shut down
- reset to factory defaults

Access to the console means physical access, so the menu has no login.

### SSH

SSH is off by default. When you switch it on under *System → General*:
- Only public-key logins are accepted, as `root`.
- Put your keys in `/data/ssh/authorized_keys`.
- The root filesystem is read-only and changes to it are lost on reboot.
- The configuration lives in the database at `/data/phonix.db` and is managed with the web interface or the `phonix` command.

## 4. Updates and rollback

PhonixPBX uses two system slots, A and B. An update is written to the slot that is not running. Your configuration and data on `PHXDATA` are never touched.

1. Go to *System → Firmware*. Upload `phonix-<version>-<board>.update`, or let the box download it.
2. The bundle is checked before anything is written. Bundles that fail any check are refused:
   - the ed25519 signature, against the public key built into the image
   - the board type
   - every checksum
3. The update is written to the inactive slot, and that slot is set for **one trial boot**. Then the system reboots.
4. After the reboot, the health check waits until the web interface and Asterisk respond. Only then does it make the new slot permanent.
5. If the new system does not come up, the box boots the previous version again. This covers:
   - a failed boot
   - a crash
   - a health check that has not passed within 10 minutes; the box then reboots by itself
   - any reboot before the new slot was confirmed

The kernel log records which slot runs and whether it was confirmed:

```
phonix: boot slot B marked good (update confirmed)
```

How the slots are switched:
- **PC:** GRUB keeps `boot_slot` and `try_slot` in `PHXBOOT:/grub/grubenv`. The GRUB menu, shown for 3 seconds, also lets you start the other slot by hand.
- **Raspberry Pi:** `PHXBOOT:/slot.txt` selects the slot directory through `os_prefix=slotA/` or `os_prefix=slotB/`. The Pi firmware cannot write files, so the initramfs counts the trial boots in `PHXBOOT:/trial.txt`.
  - If the kernel of an update hangs before the initramfs runs, power-cycling does not help. Remove the card, edit `slot.txt` on another computer to point to the previous slot, and delete `trial.txt`.
  - Updates replace the kernel, device trees and overlays of a slot. They do not replace the Pi firmware (`start*.elf`, `fixup*.dat`, `bootcode.bin`). The firmware changes only when you flash a new image.

## 5. Factory reset

Factory reset wipes the data partition: configuration, voicemail, certificates and keys. The installed system version stays.

Start it from the web interface (*System → Factory defaults*) or from the console menu. The data partition is formatted during the next boot. After that, the box behaves exactly as on its first boot, including a new random admin password.

## 6. Partition layout

| # | Label | Type | Size | Contents |
|---|---|---|---|---|
| 1 | `PHXBOOT` | FAT32 | 256 MB | GRUB (`EFI/BOOT/BOOTX64.EFI`, `grub/`) or the Pi firmware and `config.txt`. Also `slotA/` and `slotB/` with kernel and initramfs. |
| 2 | – | squashfs | 512 MB | System slot A (read-only) |
| 3 | – | squashfs | 512 MB | System slot B (read-only) |
| 4 | `PHXDATA` | ext4 | rest of disk | `/data`: database, media, voicemail (`/var/spool/asterisk`), TLS certificate, SSH keys |

How the running system is put together:
- The root filesystem is the squashfs of the active slot with a RAM overlay on top. Changes outside `/data` are lost when the box restarts.
- `/media/boot` is the boot partition. It is mounted read-only and remounted read-write only for updates.
- Logs are in RAM under `/var/log`. They are rotated small.

### Kernel command line options

These options are for service work. Add them in the GRUB menu (press `e`) or in `slotX/cmdline.txt` on a Pi.

| Option | Effect |
|---|---|
| `phonix.console=shell` | Root shell instead of the menu on the console(s) |
| `phonix.debug=1` | Rescue shell when the initramfs fails, instead of a reboot |
| `phonix.break=1` | Shell in the initramfs just before the system starts |

## Migrating from AskoziaPBX 1.x / 2.x

1. Before flashing, copy `config.xml` from the old box. Use the old web interface (*System → Backup*), or copy `conf/config.xml` from its first partition.
2. Flash the new image.
3. Before the first boot, copy `config.xml` to the root of the `PHXBOOT` partition.
4. At the first boot the file is imported and renamed to `config.xml.imported`.
5. The import report is shown at the first login. It lists the features that were not carried over, such as analog/ISDN hardware and DAHDI.

You can also import the file later under *System → Backup/Restore*.

## Building the images yourself

You need Linux with rootless podman, or docker with `CONTAINER=docker`. No root rights, loop devices or qemu-user are needed.

```sh
image/build.sh pc-amd64             # or rpi-arm64, pc-x86, all
image/test-qemu.sh --update         # QEMU boot test (UEFI + BIOS), update and rollback
```

`image/build.sh` does the following, all inside an `alpine:3.24` container:

1. Builds the `phonix` apk from this repository with abuild.
2. Installs the package lists in `image/profiles/` with `apk --root --arch`.
3. Builds the initramfs.
4. Assembles `out/phonix-<version>-<board>.img.zst`, the `.update` bundle, a `.packages` list with the exact package versions, and `SHA256SUMS`.

### Signing keys

- **Update signing key** (ed25519). Create it once with `image/keys.sh`; it writes to `image/keys/`, which git ignores.
  - Keep `update-signing.pem` offline or in a CI secret, `PHONIX_UPDATE_SIGNING_KEY`.
  - Every image contains the public half as `/etc/phonix/update-key.pub` and accepts only bundles signed with that private key.
  - If no key is present, the build makes a throwaway key and prints a warning. Images built that way can only be updated with bundles from the same build tree.
- **Package signing key** (RSA, abuild). Pass it with `PHONIX_ABUILD_KEY=/path/key.rsa`, with the `.pub` file next to it. Otherwise a throwaway key is made in `image/keys/abuild/`. Its public half is installed into the image's `/etc/apk/keys`.
