---
title: "System"
weight: 40
icon: settings
---
Das Menü *System* enthält die Einstellungen des Geräts selbst und nicht der Telefonanlage: Hostname, Zeit und Netzwerk, die Datenpartition, Firmware-Updates, Backups, das Zurücksetzen auf Werkseinstellungen und den Neustart.

- [Grundeinstellungen]({{< relref "/system/general.md" >}}): Hostname, Domain, Zeitzone, Zeitserver, Tonzone, Sprache der Ansagen, mDNS und SSH-Zugang.
- [Netzwerk]({{< relref "/system/network.md" >}}): LAN-Adresse (DHCP oder statisch), DNS-Server, IPv6 und die NAT-Einstellungen für SIP.
- [Speicher]({{< relref "/system/storage.md" >}}): wie voll die Datenpartition ist und was den Platz belegt.
- [Firmware]({{< relref "/system/firmware.md" >}}): die installierte Version, die Suche nach Updates und die Installation signierter Update-Pakete.
- [Backup/Wiederherstellung]({{< relref "/system/backup.md" >}}): Backups der Konfiguration, Wiederherstellung sowie Import und Export von AskoziaPBX-Dateien `config.xml`.
- [Werkseinstellungen]({{< relref "/system/defaults.md" >}}): alle Daten löschen und neu beginnen.
- [Neustart]({{< relref "/system/reboot.md" >}}): das System neu starten oder herunterfahren.

Änderungen unter *Grundeinstellungen* und *Netzwerk* werden erst wirksam, wenn Sie sie übernehmen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}).

In einem Container (LXC-/Incus-Systemcontainer oder OCI-Image) verhalten sich einige dieser Seiten anders: Netzwerk, Hostname des Containers und Uhrzeit gehören zum Container-Host, und Updates funktionieren anders. Jede Seite beschreibt, was jeweils gilt.
