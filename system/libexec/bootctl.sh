# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=sh
# PhonixPBX A/B boot slot state (sourced library, POSIX sh).
#
# Used by the privileged helper (priv), the healthcheck loop (read-only
# queries) and the initramfs (trial accounting on the Raspberry Pi).
#
# Slots are "A" and "B". Partition 2 holds the root filesystem of slot A,
# partition 3 the one of slot B. Kernel + initramfs (and on the Pi the device
# trees/overlays) live in /slotA and /slotB on the PHXBOOT partition.
#
# Boot state on PHXBOOT:
#   grub (PC):  grub/grubenv  boot_slot=<permanent slot>  try_slot=<one-time trial>
#               GRUB consumes try_slot (save_env) before booting it, so a
#               failed trial falls back to boot_slot on the next boot.
#   rpi:        slot.txt      os_prefix=slotX/  (included from config.txt)
#               trial.txt     slot=X fallback=Y tries=N
#               The Pi firmware cannot write, so the initramfs counts trial
#               boots and restores the fallback slot when they are used up.
#
# The booted slot is passed on the kernel command line (phonix.slot=X).

: "${BOOT_DIR:=/media/boot}"
: "${BOOTCTL_CMDLINE:=/proc/cmdline}"

bootctl_die() {
	echo "bootctl: $*" >&2
	exit 1
}

bootctl_valid_slot() {
	case "$1" in
	A | B) return 0 ;;
	*) return 1 ;;
	esac
}

bootctl_other() {
	if [ "$1" = A ]; then echo B; else echo A; fi
}

# partition number holding the root filesystem of a slot
bootctl_partnum() {
	if [ "$1" = A ]; then echo 2; else echo 3; fi
}

bootctl_loader() {
	if [ -f "$BOOT_DIR/grub/grub.cfg" ]; then
		echo grub
	elif [ -f "$BOOT_DIR/config.txt" ]; then
		echo rpi
	else
		echo unknown
	fi
}

bootctl_cmdline_get() {
	# print the value of a key=value kernel parameter
	for _w in $(cat "$BOOTCTL_CMDLINE" 2>/dev/null); do
		case "$_w" in
		"$1"=*)
			echo "${_w#*=}"
			return 0
			;;
		esac
	done
	return 1
}

bootctl_current() {
	_s=$(bootctl_cmdline_get phonix.slot || true)
	bootctl_valid_slot "$_s" || _s=A
	echo "$_s"
}

# ---------------------------------------------------------------- grubenv

bootctl_grubenv_get() {
	sed -n "s/^$1=//p" "$BOOT_DIR/grub/grubenv" 2>/dev/null | head -n 1
}

# bootctl_grubenv_write <boot_slot> <try_slot|"">
bootctl_grubenv_write() {
	_env="$BOOT_DIR/grub/grubenv"
	_tmp="${TMPDIR:-/tmp}/grubenv.$$"
	{
		printf '# GRUB Environment Block\n'
		printf 'boot_slot=%s\n' "$1"
		printf 'try_slot=%s\n' "$2"
	} >"$_tmp"
	_size=$(wc -c <"$_tmp")
	head -c $((1024 - _size)) /dev/zero | tr '\000' '#' >>"$_tmp"
	[ "$(wc -c <"$_tmp")" -eq 1024 ] || bootctl_die "grubenv size mismatch"
	if [ -f "$_env" ] && [ "$(wc -c <"$_env")" -eq 1024 ]; then
		# rewrite in place: GRUB writes the block directly to its sectors
		dd if="$_tmp" of="$_env" bs=1024 count=1 conv=notrunc 2>/dev/null
	else
		cat "$_tmp" >"$_env"
	fi
	rm -f "$_tmp"
	sync
}

# ---------------------------------------------------------------- rpi

bootctl_rpi_slot_txt() {
	sed -n 's|^os_prefix=slot\([AB]\)/.*|\1|p' "$BOOT_DIR/slot.txt" 2>/dev/null | head -n 1
}

bootctl_rpi_write_slot() {
	printf '# managed by PhonixPBX (A/B update) - do not edit\nos_prefix=slot%s/\n' "$1" \
		>"$BOOT_DIR/slot.txt.new"
	sync
	mv -f "$BOOT_DIR/slot.txt.new" "$BOOT_DIR/slot.txt"
	sync
}

bootctl_rpi_trial_get() {
	sed -n "s/^$1=//p" "$BOOT_DIR/trial.txt" 2>/dev/null | head -n 1
}

bootctl_rpi_write_trial() {
	# slot fallback tries
	printf 'slot=%s\nfallback=%s\ntries=%s\n' "$1" "$2" "$3" >"$BOOT_DIR/trial.txt.new"
	sync
	mv -f "$BOOT_DIR/trial.txt.new" "$BOOT_DIR/trial.txt"
	sync
}

# ---------------------------------------------------------------- queries

# slot that boots when no trial is pending / after a failed trial
bootctl_permanent() {
	case "$(bootctl_loader)" in
	grub)
		_s=$(bootctl_grubenv_get boot_slot)
		;;
	rpi)
		if [ -f "$BOOT_DIR/trial.txt" ]; then
			_s=$(bootctl_rpi_trial_get fallback)
		else
			_s=$(bootctl_rpi_slot_txt)
		fi
		;;
	*) _s=A ;;
	esac
	bootctl_valid_slot "$_s" || _s=A
	echo "$_s"
}

# pending (not yet started) trial slot, if any
bootctl_pending_trial() {
	case "$(bootctl_loader)" in
	grub)
		_s=$(bootctl_grubenv_get try_slot)
		;;
	rpi)
		_s=""
		if [ -f "$BOOT_DIR/trial.txt" ] && [ "$(bootctl_rpi_trial_get slot)" != "$(bootctl_current)" ]; then
			_s=$(bootctl_rpi_trial_get slot)
		fi
		;;
	*) _s="" ;;
	esac
	bootctl_valid_slot "$_s" && echo "$_s"
	return 0
}

# true when the running system was booted as an unconfirmed trial
bootctl_is_trial() {
	[ "$(bootctl_current)" != "$(bootctl_permanent)" ]
}

bootctl_status() {
	echo "loader=$(bootctl_loader)"
	echo "current=$(bootctl_current)"
	echo "permanent=$(bootctl_permanent)"
	echo "pending_trial=$(bootctl_pending_trial)"
	if bootctl_is_trial; then echo "trial=1"; else echo "trial=0"; fi
}

# ---------------------------------------------------------------- changes
# (callers must make $BOOT_DIR writable)

# Forget a pending trial of <slot> (before its contents are overwritten).
bootctl_cancel_trial() {
	case "$(bootctl_loader)" in
	grub)
		if [ "$(bootctl_grubenv_get try_slot)" = "$1" ]; then
			bootctl_grubenv_write "$(bootctl_permanent)" ""
		fi
		;;
	rpi)
		if [ -f "$BOOT_DIR/trial.txt" ] && [ "$(bootctl_rpi_trial_get slot)" = "$1" ]; then
			bootctl_rpi_write_slot "$(bootctl_rpi_trial_get fallback)"
			rm -f "$BOOT_DIR/trial.txt"
			sync
		fi
		;;
	esac
}

# Boot <slot> once on the next boot; fall back to the current slot unless
# the trial gets confirmed with bootctl_mark_good.
bootctl_arm_trial() {
	bootctl_valid_slot "$1" || bootctl_die "invalid slot $1"
	_cur=$(bootctl_current)
	[ "$1" != "$_cur" ] || bootctl_die "slot $1 is running"
	case "$(bootctl_loader)" in
	grub)
		bootctl_grubenv_write "$_cur" "$1"
		;;
	rpi)
		# tries=1: the first boot of the slot consumes the try; if that
		# boot is not confirmed, the next boot restores the fallback
		bootctl_rpi_write_trial "$1" "$_cur" 1
		bootctl_rpi_write_slot "$1"
		;;
	*) bootctl_die "unknown boot loader" ;;
	esac
}

# Make the running slot permanent.
bootctl_mark_good() {
	_cur=$(bootctl_current)
	case "$(bootctl_loader)" in
	grub)
		if [ "$(bootctl_grubenv_get boot_slot)" != "$_cur" ] || [ -n "$(bootctl_grubenv_get try_slot)" ]; then
			bootctl_grubenv_write "$_cur" ""
		fi
		;;
	rpi)
		rm -f "$BOOT_DIR/trial.txt"
		[ "$(bootctl_rpi_slot_txt)" = "$_cur" ] || bootctl_rpi_write_slot "$_cur"
		sync
		;;
	*) bootctl_die "unknown boot loader" ;;
	esac
}

# Initramfs hook (rpi): account a trial boot. Returns 0 to continue booting
# (sets TRIAL=1 when this boot is a trial) or 2 when the trial is used up
# and the fallback slot has been restored - the caller must reboot.
bootctl_initramfs_account() {
	[ "$(bootctl_loader)" = rpi ] || return 0
	[ -f "$BOOT_DIR/trial.txt" ] || return 0
	_cur=$(bootctl_current)
	_slot=$(bootctl_rpi_trial_get slot)
	_fb=$(bootctl_rpi_trial_get fallback)
	_tries=$(bootctl_rpi_trial_get tries)
	case "$_tries" in '' | *[!0-9]*) _tries=0 ;; esac
	bootctl_valid_slot "$_fb" || _fb=$(bootctl_other "$_slot")
	if [ "$_slot" != "$_cur" ]; then
		# booted something else (e.g. the fallback): forget the trial
		rm -f "$BOOT_DIR/trial.txt"
		[ "$(bootctl_rpi_slot_txt)" = "$_cur" ] || bootctl_rpi_write_slot "$_cur"
		return 0
	fi
	if [ "$_tries" -gt 0 ]; then
		bootctl_rpi_write_trial "$_slot" "$_fb" $((_tries - 1))
		TRIAL=1
		return 0
	fi
	bootctl_rpi_write_slot "$_fb"
	rm -f "$BOOT_DIR/trial.txt"
	sync
	return 2
}
