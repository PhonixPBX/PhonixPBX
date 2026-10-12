#!/bin/sh
# Assemble the disk image and the update bundle of a board.
#   assemble.sh <board>
# -> out/phonix-<version>-<board>.img.zst, .update, .packages
#
# Layout (MBR, identical on all boards):
#   p1 PHXBOOT FAT32 256 MiB | p2 rootA squashfs 512 MiB |
#   p3 rootB squashfs 512 MiB | p4 PHXDATA ext4 (64 MiB, grown on first boot)
# No root, no loop devices: partitions are built as files and copied into
# the disk image at their offsets.
BOARD=$1
. /src/image/lib/common.sh
load_profile

export MTOOLS_SKIP_CHECK=1
R=$BW/rootfs
KB=$BW/boot
P=$BW/parts
rm -rf "$P"
mkdir -p "$P/bootfs" "$P/payload"
NAME=phonix-$VERSION-$BOARD

SECT=512
BOOT_START=2048
BOOT_SIZE=$((256 * 2048))
ROOTA_START=$((BOOT_START + BOOT_SIZE))
ROOT_SIZE=$((512 * 2048))
ROOTB_START=$((ROOTA_START + ROOT_SIZE))
DATA_START=$((ROOTB_START + ROOT_SIZE))
DATA_SIZE=$((64 * 2048))
TOTAL=$((DATA_START + DATA_SIZE))

# --- root file system ---------------------------------------------------------
msg "[$BOARD] squashfs"
case "$ARCH" in
x86 | x86_64) BCJ="-Xbcj x86" ;;
aarch64) BCJ="-Xbcj arm64" ;;
*) BCJ="" ;;
esac
# shellcheck disable=SC2086
mksquashfs "$R" "$P/payload/rootfs.squashfs" -noappend -quiet -no-progress \
	-comp xz $BCJ -b 1M \
	-no-xattrs >/dev/null 2>&1 ||
	mksquashfs "$R" "$P/payload/rootfs.squashfs" -noappend -quiet -no-progress \
		-comp xz -b 1M -no-xattrs
SQ=$(stat -c %s "$P/payload/rootfs.squashfs")
[ "$SQ" -le $((ROOT_SIZE * SECT)) ] || die "root file system ($SQ bytes) exceeds the 512 MiB slot"
msg "[$BOARD] rootfs.squashfs: $((SQ / 1048576)) MiB"

# --- kernel, initramfs and boot loader files -----------------------------------
cp "$BW/initramfs" "$P/payload/initramfs"
mkdir -p "$P/bootfs/slotA" "$P/bootfs/slotB"
case "$LOADER" in
grub)
	cp "$KB/vmlinuz-$KERNEL_FLAVOR" "$P/payload/vmlinuz"
	mkdir -p "$P/bootfs/grub"
	sed "s|@CMDLINE@|$CMDLINE|" "$IMG/boot/grub/grub.cfg" >"$P/bootfs/grub/grub.cfg"
	grub-editenv "$P/bootfs/grub/grubenv" create
	grub-editenv "$P/bootfs/grub/grubenv" set boot_slot=A try_slot=
	MODS="part_msdos part_gpt fat search search_label search_fs_uuid configfile normal linux
		echo test loadenv serial terminal sleep reboot halt gzio minicmd ls cat"
	for plat in $GRUB_PLATFORMS; do
		mkdir -p "$P/bootfs/grub/$plat"
		cp /usr/lib/grub/"$plat"/*.mod /usr/lib/grub/"$plat"/*.lst "$P/bootfs/grub/$plat/"
		case "$plat" in
		i386-pc)
			# shellcheck disable=SC2086
			grub-mkimage -O i386-pc -o "$P/core.img" -c "$IMG/boot/grub/early.cfg" -p /grub \
				biosdisk $MODS
			[ "$(stat -c %s "$P/core.img")" -lt $(((BOOT_START - 1) * SECT)) ] || die "core.img too large"
			;;
		x86_64-efi)
			mkdir -p "$P/bootfs/EFI/BOOT"
			# shellcheck disable=SC2086
			grub-mkimage -O x86_64-efi -o "$P/bootfs/EFI/BOOT/BOOTX64.EFI" \
				-c "$IMG/boot/grub/early.cfg" -p /grub efi_gop efi_uga all_video $MODS
			;;
		i386-efi)
			mkdir -p "$P/bootfs/EFI/BOOT"
			# shellcheck disable=SC2086
			grub-mkimage -O i386-efi -o "$P/bootfs/EFI/BOOT/BOOTIA32.EFI" \
				-c "$IMG/boot/grub/early.cfg" -p /grub efi_gop all_video $MODS
			;;
		esac
	done
	;;
rpi)
	cp "$KB/vmlinuz-rpi" "$P/payload/vmlinuz"
	# firmware (shared by both slots)
	for f in bootcode.bin start.elf fixup.dat start4.elf fixup4.dat; do
		[ -f "$KB/$f" ] && cp "$KB/$f" "$P/bootfs/"
	done
	cp "$IMG/boot/rpi/config.txt" "$IMG/boot/rpi/usercfg.txt" "$P/bootfs/"
	printf '# managed by PhonixPBX (A/B update) - do not edit\nos_prefix=slotA/\n' >"$P/bootfs/slot.txt"
	# device trees + overlays are per slot (they belong to the kernel)
	mkdir -p "$P/dtb"
	cp "$KB"/*.dtb "$P/dtb/"
	cp -r "$KB/overlays" "$P/dtb/"
	(cd "$P/dtb" && tar --format=ustar --owner=0 --group=0 --numeric-owner --sort=name \
		--mtime="@$SOURCE_DATE_EPOCH" -cf "$P/payload/boot.tar" .)
	tar -xf "$P/payload/boot.tar" -C "$P/bootfs/slotA"
	echo "$CMDLINE phonix.slot=A" >"$P/bootfs/slotA/cmdline.txt"
	;;
esac
cp "$P/payload/vmlinuz" "$P/payload/initramfs" "$P/bootfs/slotA/"
echo "$VERSION" >"$P/bootfs/slotA/version"

# --- PHXBOOT (FAT32) -------------------------------------------------------------
msg "[$BOARD] boot partition"
find "$P/bootfs" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
mkfs.vfat -F 32 -n PHXBOOT --invariant -C "$P/boot.img" $((BOOT_SIZE / 2)) >/dev/null
(cd "$P/bootfs" && mcopy -i "$P/boot.img" -s -m -Q ./* ::/)

# --- PHXDATA (ext4, empty) ---------------------------------------------------------
mke2fs -q -F -t ext4 -L PHXDATA -m 1 -U 41534b5a-4441-5441-0000-000000000001 \
	-E root_owner=0:0,hash_seed=41534b5a-4441-5441-0000-000000000002 \
	"$P/data.img" $((DATA_SIZE / 2))k

# --- disk image -----------------------------------------------------------------------
msg "[$BOARD] disk image"
IMGF=$P/disk.img
rm -f "$IMGF"
truncate -s $((TOTAL * SECT)) "$IMGF"
sfdisk -q "$IMGF" <<LAYOUT
label: dos
label-id: 0x41534b5a
unit: sectors

start=$BOOT_START, size=$BOOT_SIZE, type=c, bootable
start=$ROOTA_START, size=$ROOT_SIZE, type=83
start=$ROOTB_START, size=$ROOT_SIZE, type=83
start=$DATA_START, size=$DATA_SIZE, type=83
LAYOUT
dd if="$P/boot.img" of="$IMGF" bs=$SECT seek=$BOOT_START conv=notrunc status=none
dd if="$P/payload/rootfs.squashfs" of="$IMGF" bs=$SECT seek=$ROOTA_START conv=notrunc status=none
dd if="$P/data.img" of="$IMGF" bs=$SECT seek=$DATA_START conv=notrunc status=none
if [ -f "$P/core.img" ]; then
	# GRUB for BIOS: boot.img code (keep disk signature + partition table)
	# and core.img in the gap before the first partition
	dd if=/usr/lib/grub/i386-pc/boot.img of="$IMGF" bs=440 count=1 conv=notrunc status=none
	# like grub-bios-setup on hard disks: nop out the boot drive check
	printf '\220\220' | dd of="$IMGF" bs=1 seek=$((0x66)) conv=notrunc status=none
	dd if="$P/core.img" of="$IMGF" bs=$SECT seek=1 conv=notrunc status=none
fi
sfdisk -l "$IMGF"

# --- outputs ------------------------------------------------------------------------------
msg "[$BOARD] compressing"
rm -f "$OUT/$NAME.img.zst"
zstd -q -T0 -19 "$IMGF" -o "$OUT/$NAME.img.zst"
cp "$BW/packages.txt" "$OUT/$NAME.packages"

msg "[$BOARD] update bundle"
SIGNKEY=${PHONIX_UPDATE_SIGNING_KEY:-$KEYS_DIR/update-signing.pem}
"$IMG/mkbundle.sh" "$BOARD" "$VERSION" "$P/payload" "$SIGNKEY" "$OUT/$NAME.update"

write_sha256sums
msg "[$BOARD] done: $OUT/$NAME.img.zst ($(du -h "$OUT/$NAME.img.zst" | cut -f1)), $NAME.update ($(du -h "$OUT/$NAME.update" | cut -f1))"
