# Installing PhonixPBX

PhonixPBX ships as a complete disk image for three boards:

| Board | Image | Hardware |
|---|---|---|
| `rpi-arm64` | `phonix-<version>-rpi-arm64.img.zst` | Raspberry Pi 3B+, 4, 400, 5, Zero 2 W (64-bit) |
| `pc-amd64` | `phonix-<version>-pc-amd64.img.zst` | 64-bit PCs, servers and VMs; UEFI or legacy BIOS |
| `pc-x86` | `phonix-<version>-pc-x86.img.zst` | 32-bit PCs, legacy BIOS only. Best effort. |

Each release also includes a signed update bundle per board, `phonix-<version>-<board>.update`, and a `SHA256SUMS` file.

PhonixPBX also runs in containers, with the same system inside:

| Target | Download | Runs on |
|---|---|---|
| `lxc-amd64`, `lxc-arm64` | `phonix-<version>-lxc-<arch>.tar.xz` (+ `.meta.tar.xz` for `lxc-create`) | Proxmox VE, LXC: [system container](#lxc-incus-and-proxmox-ve-system-containers) |
| | `phonix-<version>-incus-<arch>.tar.xz` | Incus / LXD (unified image) |
| OCI image | `ghcr.io/phonixpbx/phonix` (linux/amd64, linux/arm64) | Docker, Podman, Kubernetes: [container image](#container-image-docker-podman) |

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
2. The certificate is self-signed, so the browser shows a warning the first time. Check that the address is right and accept the warning. Later you can get a free certificate from Let's Encrypt (or another ACME CA), or upload your own, under *Advanced → Certificate*.
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
- Log in as `root`, with a key or with the SSH root password set on the same page.
- Put your keys in `/data/ssh/authorized_keys`. Without a password, only key logins work.
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

## LXC, Incus and Proxmox VE system containers

The `lxc-<arch>` images contain the same system as the appliance: OpenRC as init, Asterisk, the web interface behind nginx (HTTPS), the security monitor, the console menu and the nftables firewall. What a container does not need is left out: kernel, initramfs, boot loader, A/B slots, device management, hardware clock and time synchronisation (the clock comes from the host).

Differences to the appliance:

- **`/data`** is a directory in the container. Put it on a separate volume (examples below), so the container can be replaced on updates while the data stays. The first start initialises it exactly like the data partition: database, TLS certificate, random admin password.
- **Network, host name and DNS** belong to the container host. PhonixPBX does not write `/etc/network/interfaces`, `/etc/hostname`, `/etc/hosts` or `/etc/resolv.conf` in a container. *System → Network* shows a notice. The LAN interface setting there only picks the address that is used for SIP, and the NAT settings work as usual. The image default is DHCP on `eth0`.
- **Updates** replace the container. *System → Firmware* says so, and update bundles are refused. To update, create a new container from the new image and attach the old `/data` volume, or restore a backup (*System → Backup/Restore*) into the new container.
- **Factory reset** erases `/data` at the next start of the container.
- **Console menu** runs on the container console (`/dev/console`) and on `tty1`.

The containers run unprivileged. Give them at least 512 MB RAM (1 GB recommended) and 2 GB disk plus the data volume. For telephones on your LAN, attach the container to a bridge of your LAN so it gets its own address (`eth0`). Phones and providers then reach SIP (5060) and RTP (10000-20000/udp) directly.

### Proxmox VE

1. Upload the template: *local → CT Templates → Upload* with `phonix-<version>-lxc-amd64.tar.xz`, or on the host:

   ```sh
   wget -P /var/lib/vz/template/cache/ \
     https://github.com/PhonixPBX/PhonixPBX/releases/download/<tag>/phonix-<version>-lxc-amd64.tar.xz
   ```

2. Create and start the container. The OS type is detected as Alpine; `/data` gets its own volume (`mp0`):

   ```sh
   pct create 120 local:vztmpl/phonix-<version>-lxc-amd64.tar.xz \
     --hostname pbx --ostype alpine --unprivileged 1 \
     --cores 2 --memory 1024 --swap 512 \
     --rootfs local-lvm:2 --mp0 local-lvm:8,mp=/data \
     --net0 name=eth0,bridge=vmbr0,ip=dhcp \
     --cmode console --onboot 1
   pct start 120
   pct console 120        # console menu with address and initial password (Ctrl+a q to leave)
   ```

   For a static address use `ip=192.168.1.10/24,gw=192.168.1.1` and set DNS with `--nameserver`.

Proxmox writes `/etc/network/interfaces`, `/etc/hostname`, `/etc/hosts` and `/etc/resolv.conf` at every start from the container settings. PhonixPBX leaves these files to Proxmox, so change the network in Proxmox (`pct set 120 --net0 ...` or the GUI), not in PhonixPBX.

Update to a new version, keeping the data volume:

```sh
pct stop 120
pct create 121 local:vztmpl/phonix-<new-version>-lxc-amd64.tar.xz <same options, without --mp0>
pct move-volume 120 mp0 --target-vmid 121 --target-volume mp0
pct start 121
```

### Incus (and LXD)

```sh
incus image import phonix-<version>-incus-amd64.tar.xz --alias phonix
incus storage volume create default phonix-data
incus init phonix pbx
incus storage volume attach default phonix-data pbx /data
incus start pbx
incus console pbx          # console menu (Enter to redraw, Ctrl+a q to leave)
incus list pbx             # address of the container
```

On the default `incusbr0` network the PBX is only reachable from the host. For phones on your LAN, give it a NIC on your LAN, for example `incus config device override pbx eth0 nictype=macvlan parent=enp1s0` (or a bridged NIC). To update, `incus image import` the new version, create a new instance, and attach the same `phonix-data` volume to it. LXD works the same way with `lxc` instead of `incus`.

### LXC (lxc-create)

```sh
lxc-create -n pbx -t local -- \
  --metadata phonix-<version>-lxc-amd64.meta.tar.xz \
  --fstree phonix-<version>-lxc-amd64.tar.xz
# network: lxc.net.0.* in the container config (e.g. /var/lib/lxc/pbx/config)
# data volume: lxc.mount.entry = /srv/phonix-data data none bind,create=dir 0 0
lxc-start -n pbx
lxc-console -n pbx -t 0    # console menu (Ctrl+a q to leave)
```

The metadata includes `alpine.common.conf`, the LXC configuration that Proxmox VE uses for Alpine as well. It also works for unprivileged containers created by a regular user.

## Container image (Docker, Podman)

`ghcr.io/phonixpbx/phonix` is a multi-arch (linux/amd64, linux/arm64) application container. It has the same Alpine release, packages and file layout as the appliance, but no init system. The entry point does the following:

- prepares `/data`
- runs first boot (the initial admin password appears in the container log)
- generates the configuration
- starts and supervises Asterisk, the security monitor, the web interface (as user `phonix` on a unix socket) and nginx (HTTPS on 443, port 80 redirects to it)

If one of them dies, the container exits with an error so that the restart policy takes over. `docker stop` shuts down cleanly. A health check tests the web interface and Asterisk.

Tags:

| Tag | Content |
|---|---|
| `latest`, `<version>` | releases (`v*` tags) |
| `edge`, `sha-<commit>` | latest build of the default branch (testing only) |

### Run it

Host networking is recommended. SIP and RTP then work without NAT between the container and the host, and the PBX uses the host's address:

```sh
docker run -d --name phonix --restart unless-stopped --network host \
  -v phonix-data:/data ghcr.io/phonixpbx/phonix:latest
docker logs phonix               # shows the web address and the initial admin password
```

Open `https://<host-address>/` and log in as `admin` with the password from the log. You must change the password at the first login. For the REST API, create a bearer token under *Advanced → API tokens*, or without the web interface with `docker exec phonix phonix token create <name>`.

With published ports (bridge network):

```sh
docker run -d --name phonix --restart unless-stopped \
  -p 80:80 -p 443:443 \
  -p 5060:5060/udp -p 5060:5060/tcp -p 5061:5061/tcp -p 4569:4569/udp \
  -p 10000-10100:10000-10100/udp \
  -v phonix-data:/data ghcr.io/phonixpbx/phonix:latest
```

When you publish ports, two settings matter:

- **RTP port range.** Set it to the published range under *Advanced → RTP*. Publishing all 10000-20000 ports makes docker very slow to start.
- **NAT.** Phones see the host's address, not the container's. Set *System → Network → NAT* to "NAT, static public IP" with the host's address.

Docker compose:

```yaml
services:
  phonix:
    image: ghcr.io/phonixpbx/phonix:latest
    restart: unless-stopped
    network_mode: host
    volumes:
      - phonix-data:/data
    # environment:
    #   PHONIX_HTTPS_PORT: "8443"
volumes:
  phonix-data:
```

Rootless Podman cannot bind ports below 1024 on the host network. Move the web interface instead:

```sh
podman run -d --name phonix --network host -e PHONIX_HTTP_PORT=8080 -e PHONIX_HTTPS_PORT=8443 \
  -v phonix-data:/data ghcr.io/phonixpbx/phonix:latest
```

### Options

| Environment | Default | Meaning |
|---|---|---|
| `PHONIX_HTTP_PORT` | `80` | HTTP port inside the container (redirects to HTTPS) |
| `PHONIX_HTTPS_PORT` | `443` | HTTPS port inside the container |
| `PHONIX_FIREWALL` | `0` | `1` loads PhonixPBX's nftables firewall and enables address bans by the security monitor. Needs `--cap-add NET_ADMIN`. **With `--network host` the rules go into the host's network namespace.** |

Notes:

- **Network, host name, DNS and clock** come from the container engine. PhonixPBX does not change them, as in the LXC images.
- **Updates.** Pull the new image and recreate the container with the same volume: `docker pull ghcr.io/phonixpbx/phonix:latest && docker rm -f phonix && docker run ...`, or `docker compose pull && docker compose up -d`. *System → Firmware* refuses update bundles.
- **Reboot and shut down** in the web interface stop the container. With `--restart unless-stopped`, *Reboot* starts it again.
- **Factory reset** stops the container and erases `/data` when the same container starts again.
- **Console menu:** `docker exec -it phonix phonix tui`. Asterisk console: `docker exec -it phonix asterisk -r`.
- **One-off commands** against the volume while the PBX is stopped, e.g. to reset a password: `docker run --rm -it -v phonix-data:/data ghcr.io/phonixpbx/phonix:latest phonix user passwd admin`.
- **AskoziaPBX `config.xml`.** Place it at `import/config.xml` in the data volume before the first start, or import it later in the web interface.
- **Privileges.** The web process runs as user `phonix` and reaches its few root actions (reload Asterisk/nginx, time zone, firewall) through `doas`. Do not run the container with `--security-opt no-new-privileges`, which disables doas.

Build the image yourself from the repository root:

```sh
podman build --format docker -t phonix .     # or: docker build -f Containerfile -t phonix .
image/test-oci.sh localhost/phonix           # smoke test: web, Asterisk, REST API, clean stop
```

## Monitoring with Prometheus

`GET /api/v1/metrics` returns metrics in the Prometheus text format. Create a read-only token under *Advanced → API tokens* and add a scrape job:

```yaml
scrape_configs:
  - job_name: phonix
    scheme: https
    metrics_path: /api/v1/metrics
    authorization:
      credentials: phx_...            # read-only API token
    tls_config:
      insecure_skip_verify: true      # only while the PBX uses its self-signed certificate
    static_configs:
      - targets: ["pbx.example.com"]
```

The endpoint exports these metrics:

- **System:** uptime, load, memory, data partition usage and network traffic.
- **Asterisk:** whether it is up, its start time, and active calls and channels.
- **Phones:** count per technology, and whether each enabled phone is registered (`phonix_phone_registered`).
- **Providers:** whether each enabled provider is registered or reachable (`phonix_provider_up`).
- **Voicemail:** messages per mailbox (`INBOX`/`Old`).
- **Certificate:** TLS certificate expiry and the result of the last ACME request.
- **Configuration:** pending (not applied) changes, and the number and age of backups.

Example alerts:

- `phonix_provider_up == 0`
- `phonix_asterisk_up == 0`
- `phonix_tls_certificate_expiry_seconds - time() < 14 * 86400`

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
image/build.sh pc-amd64             # or rpi-arm64, pc-x86, lxc-amd64, lxc-arm64, all
image/test-qemu.sh --update         # QEMU boot test (UEFI + BIOS), update and rollback
image/test-lxc.sh                   # boot test of the lxc-amd64 rootfs as a podman system container
```

`image/build.sh` does the following, all inside an `alpine:3.24` container:

1. Builds the `phonix` apk from this repository with abuild.
2. Installs the package lists in `image/profiles/` with `apk --root --arch`.
3. Builds the initramfs.
4. Assembles `out/phonix-<version>-<board>.img.zst`, the `.update` bundle, a `.packages` list with the exact package versions, and `SHA256SUMS`.

With `PHONIX_DEBUG_ROOT_PASSWORD=<password>`, the build makes a troubleshooting image instead, `phonix-<version>-<board>-debug.img.zst`, for boards whose local console doesn't work. It has no update bundle. At boot it enables SSH root login with that password and opens port 22, and `ssh root@<address> debug-report` collects the hardware, console and boot diagnostics. CI builds one for `rpi-arm64` on every pull request and for the nightly. Never use a debug image in production.

For the container boards (`lxc-*`), step 3 is skipped. Step 4 writes the rootfs tarball, the `lxc-create` metadata and the Incus image. All tarballs keep numeric file ownership; they are created inside the build container, where the files have their real owners.

### Signing keys

- **Update signing key** (ed25519). Create it once with `image/keys.sh`; it writes to `image/keys/`, which git ignores.
  - Keep `update-signing.pem` offline or in a CI secret, `PHONIX_UPDATE_SIGNING_KEY`.
  - Every image contains the public half as `/etc/phonix/update-key.pub` and accepts only bundles signed with that private key.
  - If no key is present, the build makes a throwaway key and prints a warning. Images built that way can only be updated with bundles from the same build tree.
- **Package signing key** (RSA, abuild). Pass it with `PHONIX_ABUILD_KEY=/path/key.rsa`, with the `.pub` file next to it. Otherwise a throwaway key is made in `image/keys/abuild/`. Its public half is installed into the image's `/etc/apk/keys`.
