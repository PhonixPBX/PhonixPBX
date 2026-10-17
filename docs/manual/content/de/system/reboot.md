---
title: "Neustart"
weight: 70
description: "Das System neu starten oder herunterfahren."
---
Unter *System → Neustart* starten Sie das System neu oder fahren es herunter. Ein Neustart ist selten nötig: Einstellungen werden wirksam, wenn Sie sie übernehmen, ohne Neustart. Sie benötigen ihn nach einem [Firmware-Update]({{< relref "/system/firmware.md" >}}) oder um eine Störung zu beheben.

> In beiden Fällen werden aktive Gespräche unterbrochen.

## Neustart {#reboot}

Klicken Sie auf **Neustart**. Die Seite wartet, bis das System wieder erreichbar ist, und lädt sich dann selbst neu. Das dauert meist ein bis zwei Minuten, auf einem Raspberry Pi mit SD-Karte auch länger.

## Herunterfahren {#shutdown}

Klicken Sie auf **Herunterfahren**, bevor Sie die Stromversorgung trennen, damit die Datenpartition sauber geschlossen wird. Wieder einschalten lässt sich das System nur vor Ort, indem Sie den Strom aus- und wieder einschalten (oder über den Virtualisierungs-Host).

## In einem Container {#containers}

In einem Container wirken die Schaltflächen auf den Container:

- **LXC/Incus:** *Neustart* startet den Container neu. *Herunterfahren* stoppt ihn; starten Sie ihn auf dem Container-Host wieder.
- **OCI-Container:** Beide Schaltflächen bewirken dasselbe: Sie stoppen den Container. Ob er wieder startet, hängt von seiner Neustart-Richtlinie ab. Mit `--restart unless-stopped` (oder `restart: unless-stopped` in Compose) startet er von selbst wieder, sodass *Neustart* wie erwartet funktioniert; damit er gestoppt bleibt, verwenden Sie `docker stop` oder `podman stop` auf dem Host. Ohne Neustart-Richtlinie starten Sie ihn mit `docker start` oder `podman start` wieder.
