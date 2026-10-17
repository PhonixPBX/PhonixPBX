---
title: "Reboot"
weight: 70
description: "Restart or shut down the system."
---
*System → Reboot* restarts the system or shuts it down. A reboot is rarely needed: settings take effect when you apply them, without a restart. You need it after a [firmware update]({{< relref "/system/firmware.md" >}}), or to clear a fault.

> Active calls are interrupted in both cases.

## Reboot {#reboot}

Click **Reboot**. The page waits until the system is reachable again and then reloads by itself. This usually takes a minute or two; on a Raspberry Pi with an SD card it can take longer.

## Shut down {#shutdown}

Click **Shut down** before you remove the power, so the data partition is closed cleanly. The system can only be started again on site, by switching the power off and on (or from the virtualisation host).

## In a container {#containers}

In a container, the buttons act on the container:

- **LXC/Incus:** *Reboot* restarts the container. *Shut down* stops it; start it again on the container host.
- **OCI container:** both buttons do the same: they stop the container. Whether it starts again depends on its restart policy. With `--restart unless-stopped` (or `restart: unless-stopped` in Compose) it starts again by itself, so *Reboot* works as expected; to keep it stopped, use `docker stop` or `podman stop` on the host. Without a restart policy, start it again with `docker start` or `podman start`.
