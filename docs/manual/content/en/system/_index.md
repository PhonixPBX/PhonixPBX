---
title: "System"
weight: 40
icon: settings
---
The *System* menu holds the settings of the appliance itself rather than of the telephone system: host name, time and network, the data partition, firmware updates, backups, the factory reset and reboot.

- [General Setup]({{< relref "/system/general.md" >}}): host name, domain, time zone, time servers, tone zone, prompt language, mDNS and SSH access.
- [Network]({{< relref "/system/network.md" >}}): LAN address (DHCP or static), DNS servers, IPv6 and the NAT settings for SIP.
- [Storage]({{< relref "/system/storage.md" >}}): how full the data partition is and what uses the space.
- [Firmware]({{< relref "/system/firmware.md" >}}): the installed version, update checks and installing signed update bundles.
- [Backup/Restore]({{< relref "/system/backup.md" >}}): backups of the configuration, restore, and the import and export of AskoziaPBX `config.xml` files.
- [Factory Defaults]({{< relref "/system/defaults.md" >}}): erase all data and start over.
- [Reboot]({{< relref "/system/reboot.md" >}}): restart or shut down the system.

Changes on *General Setup* and *Network* take effect only after you apply them, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}).

In a container (LXC/Incus system container or OCI image), some of these pages behave differently: the network, the host name of the container and the clock belong to the container host, and updates work differently. Each page says what applies.
