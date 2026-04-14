# Torrent Ecosystem Optimization Guide

**Last Updated:** April 14, 2026
**Priority:** CRITICAL - Ratio Recovery
**Status:** Active H&R Prevention + Download Throttling

## Executive Summary

Your private tracker ratios are critical:
- **Blutopia**: 0.33 ratio, 4 H&Rs (2 active)
- **fearnopeer**: 0.67 ratio
- **upload.cx**: 0.44 ratio, 4 peers seed/down, admin notice about donor requirement

**Recovery Strategy:**
1. **Immediate:** Pause new downloads until seeding debt paid down
2. **Upload Boost:** Maximize seed time and bandwidth allocation
3. **Smart Filtering:** Download only high-probability seeding torrents
4. **Throttling:** Prevent new H&Rs via qBittorrent seeding rules
5. **Optimization:** Auto-configure all apps for ratio-aware downloading

---

## Architecture Overview

### Component Interactions

```
thelounge (IRC)
    │
    ├─→ prowlarr (Indexer metadata)
    │
    ├─→ autobrr (Release monitoring/filtering)
    │       │
    │       ├─→ Smart filters (scene/P2P, quality, age)
    │       ├─→ Ratio checks (abort if ratio would drop)
    │       └─→ Integrates with qBittorrent API
    │
    ├─→ qbittorrent (Torrent client)
    │       ├─→ Multithreaded downloading
    │       ├─→ Smart seeding (ratio-aware)
    │       └─→ Bandwidth management
    │
    └─→ sonarr/radarr (Automated management)
            ├─→ Query prowlarr for searches
            ├─→ Send releases to autobrr
            └─→ Monitor qBittorrent for completion

NAS02 storage (Rook-Ceph mounted via NFS)
```

---

## Critical Configuration Changes

### 1. qBittorrent Seeding Rules (HIGHEST PRIORITY)

**Goal:** Prevent new H&Rs, maximize upload time

```ini
[Transfers]
# Seeding Limits (CRITICAL for H&R prevention)
GlobalMaxSeedingMinutes=0              # No time limit for seeding
GlobalMaxSeedingRatio=3.0              # Target 3.0 ratio before removal
MaxRatioAction=Stop                    # Stop (don't remove) at 3.0 ratio
MaxSeedingTime=9999999                 # Max seed time (practical infinity)
MaxUploadsPerSecond=0                  # No limit (let server limit)
MaxConnectionsPerSecond=0              # No limit

# Per-Torrent Seeding (if category-specific)
# Category: DefaultSeed
#   MinSeedingTime=172800               # 48 hours minimum seed time
#   MaxSeedingMinutes=10080             # 7 days max before checking ratio

[Speed]
# Upload optimization
UploadSlotsBehavior=FixedSlotPolicy    # Use fixed slots
UploadSlotsPerTorrent=4                # 4 upload slots per torrent
UpSlots=20                             # 20 total upload slots
UploadRateLimit=0                      # Unlimited (let bandwidth cap it)

# Download throttling (CRITICAL - prevent ratio collapse)
DnSlots=20                             # 20 concurrent downloads MAX
DownloadRateLimit=0                    # Set via Web UI per-session
MaxConnections=500                     # Global peer connections
MaxConnectionsPerTorrent=100           # Per-torrent peer limit

[Connection]
ProxyHostname=                         # No proxy
ProxyPassword=
ProxyPort=
ProxyType=None
ProxyUsername=
UPnPEnabled=true                       # Enable UPnP for port mapping
RandomPort=false                       # Keep consistent port (31288)
ListeningPortUPnPEnabled=true         # Let UPnP publish

[BitTorrent]
# DHT & PEX for faster peer discovery
DHT=true
PEX=true
LSD=true                               # Local Service Discovery
GZIP=true                              # Compression

[Queueing]
MaxActiveDownloads=5                   # ONLY 5 concurrent downloads
MaxActiveTorrents=10                   # Max active seeds+downloads
MaxInactiveTorrents=9999               # Allow stopped torrents
AutoTorrentMgmtEnabled=true            # Auto-manage by ratio/time
IgnoreSlowTorrents=false               # Don't auto-pause slow torrents
```

### 2. Autobrr Configuration (Release Filtering)

**Goal:** Smart downloading - only releases that won't damage ratio

```yaml
# /config/autobrr/config.toml

[server]
host = "0.0.0.0"
port = 80
metrics-port = 9094
check-for-updates = false
log-level = "info"

[database]
type = "sqlite"
# Path: /config/autobrr/autobrr.db

[actions]
# Action: Send to qBittorrent
[[actions]]
name = "qBittorrent - Monitored"
enabled = true
type = "qbittorrent"
exec-cmd = ""

[qbittorrent]
host = "qbittorrent.default.svc.cluster.local"
port = 80
username = "admin"
password = "PASSWORD_FROM_SECRET"  # Use ExternalSecret
use-ssl = false
ssl-verify = false
tls-ca = ""
client-key = ""
client-cert = ""
basic-auth = false

# Seeding rules
category = "monitored"                 # Must match qBT category
add-paused = false
skip-hash-check = false
content-layout = "original"
paused = false
root-folder = "/data"

# Critical: Ratio safeguards
ratio-limit = 3.0
seeding-time-limit = 259200            # 72 hours = upload focus
upload-limit = 0                       # No limit
tags = ["autobrr", "ratio=safe"]

[[filters]]
enabled = true
name = "Blutopia - Ratio Safe"

# Sources
[[filters.indexers]]
name = "blutopia"

# Quality filters
[[filters.rules]]
except = false
type = "years"
operator = ">="
value = "2020"                         # Only recent content (better seed time)

[[filters.rules]]
except = false
type = "codec"
operator = "="
value = "h.264"

[[filters.rules]]
except = false
type = "source"
operator = "="
value = "bluray"                       # Prefer professional sources

# Ratio protection: Only download if...
# - We have upload capacity
# - Torrent will reach max peers (better speed)
# - Scene/P2P ratio is good
[[filters.rules]]
except = true                          # NEGATIVE RULE: Skip if...
type = "seeders"
operator = "<"
value = "10"                           # Skip if <10 seeders (won't seed well)

[[filters.rules]]
except = true
type = "leechers"
operator = ">"
value = "50"                           # Skip if >50 leechers (crowded, slow upload)

# Pause downloads during peak hours
[[filters.execution_intervals]]
enabled = true
from_time = "14:00"                    # 2PM UTC (adjust to your TZ)
to_time = "18:00"                      # 6PM UTC - reduce competition

[[filters]]
enabled = true
name = "fearnopeer - Minimum Peers"

[[filters.indexers]]
name = "fearnopeer"

[[filters.rules]]
except = true
type = "seeders"
operator = "<"
value = "3"

[[filters]]
enabled = true
name = "upload.cx - Manual Approval"

[[filters.indexers]]
name = "upload.cx"

[[filters.rules]]
except = true                          # Skip by default
type = "codecs"
operator = "exists"
value = ""                             # Manual review due to critical status


# Action: Log and notify (don't auto-download critical trackers yet)
[[actions]]
name = "Critical Tracker - Notify Only"
enabled = true
type = "exec"
exec-cmd = "curl -X POST http://notifier.default.svc.cluster.local:8080/notify -d 'Critical tracker release: {release_name}'"

[[filters]]
enabled = false                        # Temp disabled until ratio improves
name = "LowRatio - Skip for Now"
invert-match = true                    # Skip matching releases
```

### 3. qBittorrent Web UI Settings

Access via `https://qbittorrent.homeops.ca`

**Under Settings → Downloads:**
- Save path: `/data/downloads`
- Keep incomplete torrents in: `/data/downloads/.incomplete`
- Pre-allocate space: OFF (faster on NFS)
- Append `.!qB` extension: ON
- Monitor external sources: `/data/watch`

**Under Settings → Connection:**
- Port: 31288 (exposed via LoadBalancer)
- Type: TCP/UTP (hybrid mode)
- UPnP/NAT-PMP: enabled
- Max connections: 500
- Max per-torrent: 100

**Under Settings → Speed:**
- Global rate limits: Apply per-session via Web UI
  - Download: 100 MB/s initial, reduce if ratio dropping
  - Upload: 50 MB/s sustained (adjust based on link capacity)
- Alt speed schedule: Enable for non-peak hours

**Under Settings → BitTorrent:**
- Encryption: Force encryption for all outgoing connections
- Maximum ratio: 3.0 (per torrent override if needed)
- Seeding time: 0 (no limit)

**Action after upload to max ratio:**
- Remove torrent + data: OFF
- Pause torrent: ON

---

## Ratio Recovery Phases

### Phase 1: Seeding Only (Days 1-7)

**Actions:**
- ✅ **STOP all new downloads** except manual approval
- ✅ Configure 48-hour minimum seed time per torrent
- ✅ Maximize upload bandwidth (50 MB/s+ if possible)
- ✅ Remove slow/stalled torrents (seeders=0, locked uploads)
- ✅ Monitor all 3 trackers daily

**Expected Results:**
- Blutopia: 0.33 → 0.45-0.50 (reduce H&R warning severity)
- fearnopeer: 0.67 → 0.75-0.80
- upload.cx: 0.44 → 0.55-0.60

**Exit Criteria:** No H&R warnings, visible ratio improvement

### Phase 2: Selective Downloads (Days 8-14)

**Preconditions:**
- Current ratio ≥ 0.50 on all trackers
- No active H&R warnings
- Seeding inventory: ≥50 active torrents

**Actions:**
- Resume autobrr monitoring (filtered downloads only)
- Require minimum 3 seeders per torrent
- Daily download limit: 5 torrents max per tracker
- 72-hour minimum seed time enforced
- Tag all new downloads for tracking

**Expected Results:**
- Maintain current ratio while slowly improving
- Rebuild trust with moderators
- Begin H&R recovery process

### Phase 3: Normal Operations (Day 15+)

**Preconditions:**
- Ratio ≥ 0.65 on Blutopia / 0.80 on fearnopeer / 0.60 on upload.cx
- H&R count stable or declining
- Admin response positive (if they check)

**Actions:**
- Resume normal autobrr filtering
- Adjust per-torrent limits based on tracker health
- Monitor for any H&R spike

---

## Application-Specific Setup

### thelounge (IRC Client)

**Purpose:** Connect to private tracker IRC channels for:
- ANNOUNCED releases (real-time)
- Ratio alerts
- H&R warnings
- Moderator communications

**Post-Install Steps:**
1. Connect to tracker IRC servers:
   - Blutopia: irc.blutopia.xyz:6667 (or SSL port)
   - fearnopeer: irc.fearnopeer.com
   - upload.cx: irc.upload.cx

2. Join channels (typical naming):
   - #announce (new releases)
   - #general (discussion)
   - #staff (alerts, if accessible)

3. Register nickname with NickServ

4. Set up CTCP/DCC (optional): Allow file uploads for invite codes

**Helm Values Updates Needed:**
```yaml
# ~/.config/thelounge/config.irc.json (create in config PVC)
{
  "networks": [
    {
      "name": "Blutopia",
      "host": "irc.blutopia.xyz",
      "port": 6697,
      "tls": true,
      "nick": "YOUR_TRACKER_USERNAME",
      "password": "YOUR_IRC_PASSWORD",
      "realName": "YOUR_REAL_NAME",
      "user": "YOUR_TRACKER_USERNAME"
    }
  ]
}
```

### prowlarr (Indexer Metadata)

**Purpose:** Centralized indexer management + API for sonarr/radarr

**Post-Install Configuration:**

1. **Add Indexers** (Configure via Web UI):
   - Blutopia (Cardigann)
   - fearnopeer (Cardigann)
   - upload.cx (Cardigann)
   - Public: 1337x, TPB, RARBG

2. **Settings → Apps:**
   - Add sonarr instance (automatic torrent search)
   - Add radarr instance
   - Add autobrr instance (for custom searches)

3. **Settings → Download Clients:**
   - Add qBittorrent: `qbittorrent.default.svc.cluster.local:80`
   - Category: `monitored`

### autobrr (Release Monitoring)

**Purpose:** IRC + RSS monitoring, intelligent filtering, qBT integration

**Post-Install Steps:**

1. **Add IRC Channels:**
   - thelounge → IRC logs
   - OR direct IRC connections for faster reaction time

2. **Add Trackers** (Web UI: Settings → Trackers):
   - Configure proxy/VPN if required
   - Credentials in ExternalSecret

3. **Create Filters** (see config above):
   - Scene filters (quality, codec, resolution)
   - P2P filters (popular torrents, good peers)
   - H&R protection rules

4. **Test Filters:**
   - Dry-run IRC parsing
   - Verify qBT connection
   - Monitor release captures

### qBittorrent (Torrent Client)

**Purpose:** Torrent downloading/seeding engine

**Post-Install Steps:**

1. **Web UI Access:** https://qbittorrent.homeops.ca
   - Default credentials (change!): admin/RANDOM_PASSWORD
   - Password stored in Secret: `qbittorrent-secret` (Azure KV)

2. **Configure Categories:**
   - `monitored` → /data/downloads (for autobrr)
   - `manual` → /data/downloads/manual
   - `tv` → /data/downloads/tv
   - `movies` → /data/downloads/movies

3. **Add Trackers:**
   - Blutopia passkey
   - fearnopeer authkey
   - upload.cx infohash

4. **Test Download:**
   - Manual torrent (non-critical) to verify:
     - Download speed
     - Upload speed (measure real upload capacity)
     - Seeding rules

### sonarr/radarr (Automated Management)

**Purpose:** Automated TV series + movie management, integration with prowlarr/autobrr

**Post-Install Steps:**

1. **Add Root Paths:**
   - sonarr: `/data/tv`
   - radarr: `/data/movies`

2. **Settings → Download Clients:**
   - qBittorrent: `qbittorrent.default.svc.cluster.local:80`
   - Category: `tv` (sonarr), `movies` (radarr)
   - Remote path mapping: /data → /data (no translation needed)

3. **Settings → Indexers:**
   - prowlarr (sync-enabled for auto-updates)
   - Configure quality profiles:
     - TV: 1080p/BluRay (high seed probability)
     - Movies: 2160p/BluRay (long-term seeding)

4. **Settings → Import Lists:**
   - Connect to trakt/letterboxd for wanted lists (optional)

### qui (qBittorrent UI)

**Purpose:** Modern web UI + mobile-friendly client management

**Purpose:** Alternative web UI for qBittorrent with better UX

**Setup:**
- Access via: https://qui.homeops.ca
- Auto-connects to qbittorrent pod (same namespace)
- Minimal setup (mostly stateless)

---

## Monitoring & Alerts

### Daily Ratio Checks

```bash
# Script to monitor ratio (add to cron or K8s CronJob)
curl -s https://blutopia.reseed.pro/api/user/profile \
  -H "Authorization: Bearer $BLUTOPIA_API_KEY" | jq '.data.ratio'

curl -s https://fearnopeer.com/api.php?action=user&user=YOUR_ID \
  -H "Authorization: Bearer $FEARNOPEER_API_KEY" | jq '.user.ratio'
```

### qBittorrent Metrics

Monitor via Prometheus (if enabled in cluster):
- `qbittorrent_seeding_count`
- `qbittorrent_active_torrents`
- `qbittorrent_total_uploaded_bytes`
- `qbittorrent_total_downloaded_bytes`
- `qbittorrent_free_disk_space`

### Autobrr Health

- Monitor `/health` endpoint
- Alert on capture failures (parsing errors)
- Alert on qBT integration failures
- Log all filter triggers

---

## Troubleshooting

### "Ratio dropping - can't keep up with downloads"

**Solutions:**
1. **Reduce concurrent downloads:** Lower `MaxActiveDownloads` in qBT (was 20, try 5)
2. **Increase seeding time:** Raise `MinSeedingTime` to 72-96 hours
3. **Pause autobrr:** Manually stop new downloads, focus on seeding
4. **Check upload link:** Verify your upload speed (run speedtest.net)
   - If <10 MB/s upload: reduce downloads to 1-2 concurrent torrents
   - If >50 MB/s upload: can sustain 10-20 concurrent downloads

### "H&Rs keep appearing"

**Causes:**
- Downloaded torrent but didn't reach min ratio before deletion
- Incomplete torrent stalling (no peers, forced removal)
- Network disconnect during upload phase

**Solutions:**
1. **Increase min seed time:** Don't remove until 72h+ elapsed
2. **Reduce downloads:** Only download if you can afford to seed 48h
3. **Check peer count:** Only download torrents with >5 seeders
4. **Monitor stalled torrents:** Remove any torrent with 0 upload speed for >4 hours

### "Getting banned/warnings from trackers"

**Status:**
- Blutopia: 4 H&Rs (2 active) → address with 72h seeding phase
- fearnopeer: 0.67 ratio → needs improvement but below warning threshold
- upload.cx: Admin message about donor requirement → consider $30 BTC donation + ratio improvement

**Actions:**
1. **Contact tracker admin** (if they allow appeals):
   - Explain current recovery plan
   - Commit to seeding targets
   - Request H&R forgiveness if possible

2. **For upload.cx specifically:**
   - $30 BTC donation is ~$1,260 (rough estimate, adjust for current price)
   - Donor status bypasses ratio requirements
   - Alternative: Reach 0.60+ ratio naturally

---

## Long-term Recommendations

### For Ratio Stability

1. **Set seed-to-download ratio:** 3:1 (seed 3x what you download by data size)
2. **Target inventory:** 100-200 active seeding torrents per tracker
3. **Seed duration:** 72+ hours per torrent (minimum)
4. **Peer diversity:** Don't focus on same releases; spread intake

### For Tracker Health

1. **Read announcements:** Most trackers have rules/alerts in IRC
2. **Participate in forums:** Shows engagement, builds trust
3. **Respect ratio alerts:** If ratio drops below 0.60, reduce downloads
4. **Report bugs:** If autobrr fails or qBT crashes, report to track maintainers

### For Infrastructure

1. **Backup configs regularly:** All app configs in NAS02/Git
2. **Monitor disk space:** `/data` fills up quickly with seeding
3. **Test disaster recovery:** Ensure Kopia/VolSync backups include torrent data
4. **Optimize bandwidth:** Use tc (traffic control) in K8s if needed

---

## Files Modified/Created

- [qbittorrent/app/helmrelease.yaml](../../kubernetes/apps/default/qbittorrent/app/helmrelease.yaml) - Updated with optimized qBT settings
- [autobrr/app/helmrelease.yaml](../../kubernetes/apps/default/autobrr/app/helmrelease.yaml) - Added IRC integration
- [thelounge/app/helmrelease.yaml](../../kubernetes/apps/default/thelounge/app/helmrelease.yaml) - IRC client config
- [prowlarr/app/helmrelease.yaml](../../kubernetes/apps/default/prowlarr/app/helmrelease.yaml) - Indexer integration
- [sonarr/radarr/app/helmrelease.yaml](../../kubernetes/apps/default/sonarr/app/helmrelease.yaml) - Auto-manager setup
- [qui/app/helmrelease.yaml](../../kubernetes/apps/default/qui/app/helmrelease.yaml) - Alternative UI

---

## Next Steps

1. **Day 1:**
   - [ ] Pause all new downloads in autobrr (disable filters)
   - [ ] Configure qBT seeding rules (72h minimum)
   - [ ] Set upload bandwidth limit (test current upload speed)

2. **Day 2-3:**
   - [ ] Connect to tracker IRC (thelounge)
   - [ ] Monitor ratio improvements
   - [ ] Configure prowlarr/sonarr/radarr integrations

3. **Day 4-7:**
   - [ ] Daily ratio checks
   - [ ] Prepare for Phase 2 (selective downloads)
   - [ ] Consider contacting admins about H&Rs

4. **Day 8-14:**
   - [ ] Resume limited autobrr filtering
   - [ ] Monitor for H&R spike
   - [ ] Fine-tune seeding time/ratios

---

**Last Updated:** 2026-04-14
**Maintained by:** Sean (osnabrugge)
**References:** Tracker documentation, autobrr wiki, qBittorrent docs
