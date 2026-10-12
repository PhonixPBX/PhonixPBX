"""What PhonixPBX runs on: an appliance board or a container.

The image build writes the board name to ``/etc/phonix/board``:
``pc-amd64``, ``rpi-arm64``, ... for the appliance images, ``lxc-<arch>`` for
the LXC/Incus system container images and ``oci-<arch>`` for the OCI
(Docker/Podman) image. Without the file (development, tests) it is ``dev``.

In a container the host (Proxmox, Incus, LXC, Docker, ...) owns the network
configuration and the host name, there are no A/B system slots, and the
system is updated by replacing the container image.
"""

from __future__ import annotations

from phonix import config

CONTAINER_PREFIXES = ("lxc-", "oci-")

# generated system components that the container host manages instead
HOST_MANAGED_COMPONENTS = frozenset({"system:network", "system:hostname"})


def board() -> str:
    path = config.get().path("/etc/phonix/board")
    try:
        return path.read_text().strip() or "dev"
    except FileNotFoundError:
        return "dev"


def is_container(name: str | None = None) -> bool:
    return (name if name is not None else board()).startswith(CONTAINER_PREFIXES)


def kind(name: str | None = None) -> str:
    """``appliance``, ``lxc``, ``oci`` or ``dev``."""
    name = name if name is not None else board()
    if name.startswith("lxc-"):
        return "lxc"
    if name.startswith("oci-"):
        return "oci"
    if name == "dev":
        return "dev"
    return "appliance"


CONTAINER_UPDATE_HINT = (
    "PhonixPBX runs in a container: firmware update bundles do not apply. "
    "Update by replacing the container with a newer image and keeping /data."
)
