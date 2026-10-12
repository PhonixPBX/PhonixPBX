#!/bin/sh
# Build the initramfs of a board (needs build-rootfs.sh first).
#   build-initramfs.sh <board>   -> image/work/<board>/initramfs
#
# A tiny Alpine root (busybox, e2fsprogs, sfdisk, dosfstools) plus the
# kernel modules from the profile's list (with dependencies, decompressed,
# loaded in dependency order by busybox insmod - no kmod needed).
BOARD=$1
. /src/image/lib/common.sh
load_profile

R=$BW/rootfs
IR=$BW/initramfs-root
KVER=$(kernel_version "$R")

msg "[$BOARD] initramfs root"
init_root "$IR"
apk_root "$IR" add --initdb busybox e2fsprogs e2fsprogs-extra sfdisk dosfstools util-linux-misc \
	>"$BW/apk-initramfs.log" 2>&1 || { tail -n 20 "$BW/apk-initramfs.log"; die "apk add failed"; }
rm -rf "${IR:?}/lib/apk" "${IR:?}/etc/apk" "${IR:?}/var/cache" "${IR:?}/usr/share" "${IR:?}/usr/include"
# keep only what the init script uses from util-linux-misc
find "$IR/usr/bin" "$IR/usr/sbin" "$IR/bin" "$IR/sbin" -type f 2>/dev/null |
	while read -r f; do
		case "${f##*/}" in
		busybox | e2fsck | resize2fs | mke2fs | sfdisk | fsck.fat | partx) ;;
		*) rm -f "$f" ;;
		esac
	done
# drop now-dangling links created by the packages (busybox links stay)
find "$IR" -xtype l ! -lname /bin/busybox -delete 2>/dev/null || true
busybox_links "$IR"
[ -e "$IR/sbin/fsck.vfat" ] || ln -sf fsck.fat "$IR/sbin/fsck.vfat"
for t in findfs blkid sfdisk e2fsck resize2fs mke2fs fsck.vfat insmod switch_root setsid; do
	[ -n "$(find "$IR/bin" "$IR/sbin" "$IR/usr/bin" "$IR/usr/sbin" -name "$t" 2>/dev/null)" ] ||
		die "initramfs lacks $t"
done

msg "[$BOARD] kernel modules ($KVER)"
mkdir -p "$IR/lib/modules"
python3 - "$R/lib/modules/$KVER" "$IMG/initramfs/$INITRAMFS_MODULES" "$IR/lib/modules" <<'PY'
import gzip, lzma, os, sys
moddir, listfile, dest = sys.argv[1:]
norm = lambda n: n.replace("-", "_")
deps, byname = {}, {}
with open(os.path.join(moddir, "modules.dep")) as fh:
    for line in fh:
        path, _, rest = line.partition(":")
        deps[path] = rest.split()
        base = os.path.basename(path).split(".ko")[0]
        byname[norm(base)] = path
wanted = []
for line in open(listfile):
    name = line.split("#")[0].strip()
    if name:
        wanted.append(norm(name))
order, seen = [], set()
def visit(path):
    if path in seen:
        return
    seen.add(path)
    for d in deps.get(path, []):
        visit(d)
    order.append(path)
missing = []
for name in wanted:
    if name in byname:
        visit(byname[name])
    else:
        missing.append(name)
with open(os.path.join(dest, "load.order"), "w") as out:
    for path in order:
        rel = path.split(".ko")[0] + ".ko"
        target = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        src = os.path.join(moddir, path)
        opener = gzip.open if path.endswith(".gz") else lzma.open if path.endswith(".xz") else open
        with opener(src, "rb") as i, open(target, "wb") as o:
            o.write(i.read())
        out.write(rel + "\n")
print(f"{len(order)} modules; built-in or absent: {' '.join(missing) or '-'}")
PY

mkdir -p "$IR/lib/askozia" "$IR/proc" "$IR/sys" "$IR/dev" "$IR/run" "$IR/tmp" "$IR/sysroot" "$IR/mnt/boot"
install -m 0755 "$IMG/initramfs/init" "$IR/init"
install -m 0644 "$SRC/system/libexec/bootctl.sh" "$IR/lib/askozia/bootctl.sh"

msg "[$BOARD] packing initramfs"
find "$IR" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
(cd "$IR" && find . -mindepth 1 | LC_ALL=C sort |
	cpio --quiet -o -H newc -R 0:0 --reproducible) | gzip -9 -n >"$BW/initramfs"
msg "[$BOARD] initramfs: $(du -h "$BW/initramfs" | cut -f1)"
