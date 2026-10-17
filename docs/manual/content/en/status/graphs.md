---
title: "Graphs"
weight: 30
description: "Live graphs of CPU usage and network traffic."
---
*Status → Graphs* shows two large live graphs. They are useful to see whether the PBX is overloaded during busy hours, or how much bandwidth the calls use.

## CPU load {#cpu}

The upper graph, *CPU load*, shows the CPU usage of the whole system in percent (0–100 %, all CPUs together). A plain PBX with a few calls stays in the low single digits. Sustained high values point to transcoding between codecs, many conference participants, or a system that is too small.

## Network traffic {#network}

The lower graph, *Network traffic (all interfaces)*, shows the incoming (*in*) and outgoing (*out*) traffic in bytes per second, summed over all network interfaces except the loopback interface. As a rule of thumb, a call with the G.711 codec (alaw/ulaw) needs about 10 KB/s in each direction per call leg, including packet overhead.

## How the graphs are sampled {#sampling}

The PBX does not record these values in the background. They are measured only while a page with graphs is open – this page, or the small graphs on [Status → Summary]({{< relref "/status/summary.md#graphs" >}}) – every two seconds on this page. The PBX keeps the last 120 samples, about four minutes on this page. When you open the page after a while, the graphs start empty and fill up while you watch; the graph shows "collecting data..." until the first values arrive.

For long-term monitoring, collect the metrics with Prometheus from `/api/v1/metrics`, see [REST API and MCP]({{< relref "/reference/api.md#metrics" >}}).
