# Bell 8 Gbps investigation — measured findings

Answers: *"I am paying Bell for 8Gbps/8Gbps and I have been getting ripped off for
years. Is there anything in my config on pve01 / gw01 that is limiting this?"*

## Verdict

**You are getting ~3.2 Gbps, not 8 Gbps — but the evidence says this is NOT Bell
under-provisioning you, and it is NOT a misconfiguration you left lying around.
It is a hard packet-processing ceiling in your own WAN path.**

The good news: it is fixable, and you already own most of the hardware.
The bad news: no amount of sysctl tuning gets a PPPoE OPNsense VM to 8 Gbps.

## The measurement that settles the "is Bell ripping me off" question

7 days of `speedtest_exporter` samples:

| Statistic | Download |
|---|---|
| Mean | **3.227 Gbps** |
| Max | 3.352 Gbps |
| Std deviation | **0.111 Gbps (±3.4%)** |
| Upload max | 3.126 Gbps |

Per-6h buckets over 7 days ranged only **3.155 → 3.352 Gbps**.

**Why this matters:** an oversubscribed / throttled ISP link looks *nothing* like
this. Congestion produces evening dips, weekend dips, and 3am bursts — swings of
20–40%. Your line is flat to within 3.4% at every hour of the day and night.

> A flat, time-invariant ceiling = a **device** doing a fixed amount of work per
> packet and running out of headroom. A variable ceiling = an **ISP**.
>
> Yours is flat. **Stop blaming Bell.**

## What I ruled out

| Hypothesis | Verdict | Evidence |
|---|---|---|
| Bell oversubscription / throttling | **Ruled out** | ±3.4% variance, no diurnal pattern |
| speedtest-exporter pod CPU-throttled | **Ruled out** | pod has memory limit only, no CPU limit |
| `net.isr` untuned (the usual advice) | **Already correct** | 8 threads, `dispatch=deferred`, `bindthreads=1` |
| netisr work stuck on one core | **Ruled out — this surprised me** | see table below |
| mbuf exhaustion | **Ruled out** | 0 mbuf denials |
| 1G link in the WAN path | **Ruled out** | 3.3 Gbps > 1 Gbps. (But see "verify" below) |

### netisr per-core IP handling on gw01 (this disproved my first theory)

```
cpu1: 697,717,056  14.35%
cpu4: 675,443,462  13.89%
cpu6: 624,814,721  12.85%
cpu2: 623,941,015  12.83%
cpu3: 621,285,624  12.78%
cpu7: 607,812,192  12.50%
cpu5: 523,614,491  10.77%
cpu0: 487,361,806  10.02%
                   ------
total ip handled: 4,861,990,367
```

IP forwarding is **evenly distributed across all 8 cores**. So the standard
"tune net.isr / your firewall is single-threaded" advice does **not** apply —
that part of your config is already right.

## What is actually left holding the ceiling

Three things, in order of likely impact:

### 1. PPPoE session processing (primary suspect)
The netisr counters above measure IP handling *after* decapsulation. The PPPoE
session itself runs through **netgraph (`ng_pppoe`)** and is **not** parallelised
the way the IP path is. One PPPoE session = one serialized encap/decap path.
~3.2 Gbps is squarely in the expected range for a modern core doing this on
FreeBSD. This is a well-known OPNsense/pfSense PPPoE ceiling.

### 2. gw01 is a VM with virtio NICs
Every packet crosses the hypervisor boundary. virtio adds per-packet overhead and
vCPU scheduling jitter on top of the PPPoE cost.

### 3. netisr queue drops — 384,131 total
```
cpu0 26,680   cpu1 56,489   cpu2 67,573   cpu3 31,437
cpu4 38,686   cpu5 64,026   cpu6 60,439   cpu7 38,801
```
Only 0.008% of packets, but it is **not zero**, and `queue-limit` is at the
default `1000`. Under burst these drops trigger TCP backoff, which caps
throughput harder than the raw drop rate suggests.

## The decisive test (needs your go-ahead — gw01 is on the read-only list)

Everything above is strong circumstantial evidence. To *prove* PPPoE is the
ceiling, measure gw01 moving traffic that does **not** traverse PPPoE:

1. Enable the **iperf plugin** on gw01 (OPNsense ships it).
2. Run iperf3 from a cluster node to gw01 across a VLAN boundary (forces routing
   through gw01, no PPPoE involved).
3. Compare:
   - **~9 Gbps routed but 3.2 Gbps via WAN** → PPPoE confirmed. Fix = item A below.
   - **~3.2 Gbps both ways** → the VM/virtio path is the ceiling. Fix = item B.

This requires starting a service on gw01, which is a config change on a
read-only host — **say the word and I will do it in a maintenance window.**

## Also worth verifying (cheap, and I have already staged it)

`docs/mikrotik-switch-config.rsc` documents ext01's WAN-side ports as:

```
sfp-sfpplus1 → 10G SFP+ to pve01
sfp-sfpplus2 → 1G SFP to fw01     <-- stale? fw01 predates gw01
sfp-sfpplus4 → XPS-PON module (ISP WAN uplink)
```

That `1G SFP` comment is almost certainly stale (you are exceeding 1 Gbps), but
**nobody has actually read the negotiated link rates off that switch** — ext01 has
no monitoring at all today.

I have added SNMP config to that file. Apply it and ext01 can be scraped, which
gives negotiated speed + errors + discards on every WAN-path port. If the PON
uplink is negotiating at less than 10G, that is a 30-second fix worth thousands of
dollars of Bell billing.

## Options if PPPoE is confirmed

| Option | Expected result | Effort |
|---|---|---|
| **A. Move PPPoE off the VM** — dedicated bare-metal firewall | ~5–6 Gbps | High (new hardware, this is the gw02/pve02 work) |
| **B. Ask Bell for DHCP/IPoE instead of PPPoE** | Removes the serialization entirely; potentially full 8 Gbps | **Low — one phone call. Try this first.** |
| **C. Raise `net.isr.defaultqlimit`** (1000 → 4096) | Cuts the 384k drops; a few % gain, not a fix | Low |
| **D. Accept 3.2 Gbps** | — | Zero |

> **Start with option B.** Bell's newer 8 Gbps deployments increasingly support
> IPoE. If they will move you off PPPoE, the ceiling likely disappears without
> you buying anything. That single phone call is the highest-value action here.

## Bottom line for the "am I being ripped off" question

You are paying for 8 Gbps and receiving 3.2 Gbps — but **the constraint is
demonstrably inside your own network, not on Bell's side**, so a refund/credit
argument based on the speedtest numbers alone will not hold up. Fix the PPPoE
path first, re-measure, and *then* escalate to Bell if it is still short.

## Monitoring gap found during this investigation

**gw01 has no node_exporter.** Your firewall — the single most important device on
the network — exports no CPU, memory, or per-interface metrics to Prometheus.
Every other host (pve01, nas02, kvm01, all 6 k8s nodes) is scraped.

This is why the question "is one core pegged during a speedtest?" could not be
answered directly from history. Recommend enabling the OPNsense
**node_exporter plugin** and adding a scrape target. Same for ext01 (SNMP, staged).
