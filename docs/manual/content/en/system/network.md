---
title: "Network"
weight: 20
description: "LAN address by DHCP or static, DNS servers, IPv6 and the NAT settings for SIP."
---
*System → Network* sets how the system gets its address on the LAN and tells Asterisk whether it sits behind a NAT router. On first boot the first network card (`eth0`) gets its address by DHCP. If PhonixPBX knows the current address of the selected interface, it is shown at the top of the page.

Click **Save** to store the settings and then apply the changes, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}).

> Changing the address interrupts the connection to the web interface. After applying, open the new address in your browser. If you lock yourself out, the console menu on the local screen or serial port can set the LAN address again (see [Console menu]({{< relref "/getting-started/_index.md#console" >}})).

## LAN interface {#lan}

| Field | Meaning | Default |
|---|---|---|
| Interface | The network card to configure. The list shows the interfaces the system has. | `eth0` |
| Configuration | **DHCP**: get the address, gateway and DNS servers from the DHCP server of your network. **Static**: use the address entered below. | DHCP |
| IP address | Static IPv4 address of the system. Only shown with *Static*. | `192.168.1.2` |
| Prefix | Network size in prefix notation, 1–32 (`24` = `255.255.255.0`). Only shown with *Static*. | `24` |
| Gateway | Default gateway (router). Optional. Only shown with *Static*. | empty |
| DNS servers | DNS servers, one per line (IPv4 or IPv6). With DHCP, leave empty to use the servers from the DHCP server. With a static address and no DNS server, the gateway is used as DNS server. | empty |
| IPv6 | **Automatic (SLAAC)**: the interface takes an IPv6 address from router advertisements. **Off**: no automatic IPv6 configuration. | Automatic (SLAAC) |

A phone system should have a fixed address, because phones and providers have to find it. Either configure a static address here, or reserve the address for the system in your DHCP server.

## NAT / public address {#nat}

These settings are needed when providers or remote phones reach the system through a NAT router, for example a typical internet router. Asterisk then puts the public address into its SIP and SDP messages for everything outside the local network, so that calls have audio in both directions.

| Field | Meaning | Default |
|---|---|---|
| Topology | **Public address / no NAT**: the system has a public address, or all phones and providers are in the local network. **NAT, static public IP**: the router has a fixed public IPv4 address. **NAT, dynamic IP (hostname)**: the router's public address changes and a DNS name points to it. | Public address / no NAT |
| Public IP address | The fixed public IPv4 address of the router. Only shown with *NAT, static public IP*. | empty |
| Public hostname | A DNS name that always resolves to the router's public address, for example a DynDNS name. Only shown with *NAT, dynamic IP (hostname)*. | empty |

The local network is taken from the LAN interface (the static address and prefix, or the network of the DHCP address). With NAT, also forward the SIP port and the RTP port range on the router to the system (see [Advanced → SIP]({{< relref "/advanced/sip.md" >}}) and [Advanced → RTP]({{< relref "/advanced/rtp.md" >}})).

## In a container {#containers}

In an LXC/Incus system container or the OCI container image, the address, gateway, DNS servers and host name of the container belong to the container host. The page shows a notice and PhonixPBX does not write the network configuration:

- The settings *Configuration*, *IP address*, *Prefix*, *Gateway*, *DNS servers* and *IPv6* are not applied. Configure the network in the container settings of Proxmox VE, Incus, LXC, Docker or Podman.
- *Interface* still selects which address is used for SIP.
- The NAT settings apply as usual.

For phones on your LAN, attach an LXC/Incus container to a bridge of your LAN, so that it gets its own address.
