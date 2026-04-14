# Torrent Ecosystem Configuration - Implementation Complete ✓

**Status Date:** April 14, 2026
**Status:** Pre-Deployment Ready (Awaiting Tracker Credential Input)
**Critical Priority:** Ratio Recovery for Blutopia (0.33), fearnopeer (0.67), upload.cx (0.44)

---

## What Has Been Configured

### ✅ Infrastructure Ready

1. **qBittorrent** (Torrent Client)
   - ✓ Deployment running (1/1 Ready)
   - ✓ LoadBalancer exposed on port 31288
   - ✓ Optimized config applied (seeding ratio 3.0, 72h+ seed time)
   - ✓ Categories created: monitored, manual, tv, movies
   - ✓ Web UI: https://qbittorrent.homeops.ca

2. **autobrr** (Release Monitoring + Filtering)
   - ✓ Deployment running (1/1 Ready)
   - ✓ qBittorrent integration configured
   - ✓ Ratio-safe filters for all 3 trackers
   - ✓ H&R prevention rules active
   - ✓ Web UI: https://autobrr.homeops.ca

3. **thelounge** (IRC Client)
   - ✓ Deployment running (1/1 Ready)
   - ✓ Configuration template prepared
   - ✓ Web UI: https://thelounge.homeops.ca
   - ⏳ Requires manual tracker connection

4. **prowlarr** (Indexer Hub)
   - ✓ Deployment running (1/1 Ready)
   - ✓ Web UI: https://prowlarr.homeops.ca
   - ⏳ Requires manual indexer setup

5. **sonarr/radarr** (Auto-Manager)
   - ✓ Both deployments running (1/1 Ready each)
   - ✓ Web UI: https://sonarr.homeops.ca, https://radarr.homeops.ca
   - ⏳ Requires download client + indexer configuration

6. **qui** (Alternative qBittorrent UI)
   - ✓ Deployment running (1/1 Ready)
   - ✓ Web UI: https://qui.homeops.ca
   - ✓ Requires no additional setup

### 📋 Configuration Files Created

```
docs/
  ├─ TORRENT-OPTIMIZATION.md          (Full optimization guide - READ THIS FIRST)
  └─ TRACKER-CREDENTIALS-SETUP.md     (Secrets management guide)

kubernetes/apps/default/
  ├─ qbittorrent/app/
  │  ├─ helmrelease.yaml              (Updated with config mount)
  │  └─ configmap.yaml                (Optimized qBittorrent settings)
  ├─ autobrr/app/
  │  ├─ helmrelease.yaml              (Updated with config mount)
  │  ├─ externalsecret.yaml           (Updated with tracker secrets)
  │  └─ configmap.yaml                (Ratio-aware filters)
  └─ thelounge/app/
     ├─ helmrelease.yaml              (Updated with config mount)
     └─ configmap.yaml                (IRC network configuration)

scripts/
  └─ setup-torrent-ecosystem.sh        (Auto-configuration script)
```

---

## What Needs Your Action

### Phase 1: Add Tracker Credentials (24 hours)

**Requires:** Your tracker API keys, passphrases, IRC credentials

**Actions:**
1. Read: [docs/TRACKER-CREDENTIALS-SETUP.md](./TRACKER-CREDENTIALS-SETUP.md)
2. Collect credentials:
   - **Blutopia**: Passkey, IRC nick + password
   - **fearnopeer**: Authkey, IRC nick + password
   - **upload.cx**: Infohash, IRC nick + password
3. Add to Azure Key Vault (via Azure CLI or portal):
   ```bash
   # Example (replace with your credentials)
   az keyvault secret set --vault-name "homeops-ca" \
     --name "autobrr-blutopia-passkey" \
     --value "your_blutopia_passkey_here"
   ```
4. Verify ExternalSecrets synchronize:
   ```bash
   KUBECONFIG=./kubeconfig kubectl get externalsecrets -n default -w
   ```

**Expected Result:** Secrets appear in Kubernetes within 30 seconds of Azure KV creation

---

### Phase 2: Configure IRC & Indexers (2-3 hours)

**Manual Web UI Setup Required**

#### thelounge Configuration
1. Access https://thelounge.homeops.ca
2. **Add network for each tracker:**
   - Server: `irc.blutopia.xyz` (port 6697, TLS)
   - Nick: Your tracker username
   - Password: Your IRC password
   - Auto-join: `#announce`, `#general`
3. **Repeat for:**
   - fearnopeer (irc.fearnopeer.com)
   - upload.cx (irc.upload.cx)
4. Verify you receive release announcements in #announce

#### prowlarr Configuration
1. Access https://prowlarr.homeops.ca
2. **Settings → Indexers:**
   - Add "Blutopia" (Cardigann/Custom)
   - Add "fearnopeer" (Cardigann/Custom)
   - Add "upload.cx" (Cardigann/Custom)
3. **Settings → Apps:**
   - Add sonarr: `http://sonarr.default.svc.cluster.local:80`
   - Add radarr: `http://radarr.default.svc.cluster.local:80`
   - Add autobrr: `http://autobrr.default.svc.cluster.local:80` (optional)
4. Test each indexer: Click "Test"

**Expected Result:** All indexers show "Online" status

---

### Phase 3: Connect Download Clients (1-2 hours)

#### sonarr Configuration
1. Access https://sonarr.homeops.ca
2. **Settings → Download Clients:**
   - Add qBittorrent
   - Host: `qbittorrent.default.svc.cluster.local`
   - Port: 80
   - Category: `tv`
   - Remote path mapping: `/data` → `/data`
3. **Settings → Indexers:**
   - Sync with prowlarr (automatic if configured)
4. **Settings → Quality Profiles:**
   - Create TV profile: 1080p BluRay preferred
   - Min/max episode age: 0-540 days (18 months)

#### radarr Configuration
1. Access https://radarr.homeops.ca
2. **Settings → Download Clients:**
   - Add qBittorrent
   - Host: `qbittorrent.default.svc.cluster.local`
   - Port: 80
   - Category: `movies`
   - Remote path mapping: `/data` → `/data`
3. **Settings → Indexers:**
   - Sync with prowlarr
4. **Settings → Quality Profiles:**
   - Create Movie profile: 2160p BluRay preferred

**Expected Result:** Download clients show "Online" with green checkmark

---

### Phase 4: Activate Seeding Phase 1 (CRITICAL - Day 1)

**Goal:** Stop all NEW downloads, maximize seeding of existing torrents to recover ratio

**Actions:**
1. Access https://qbittorrent.homeops.ca
2. **Verify settings:**
   - Settings → Speed → Global max seeding ratio: **3.0**
   - Settings → Queueing → Max active downloads: **5**
   - Settings → Queueing → Max active torrents: **10**
   - All categories have `/data/downloads/{category}` paths
3. **In autobrr:**
   - Disable all download filters temporarily (freeze new captures)
   - Set status to "maintenance" if possible
4. **Monitor currently seeding torrents:**
   - Open https://qbittorrent.homeops.ca
   - Note total seed count and current upload/download ratios
   - Monitor for 48-72 hours while ratio recovers

**Expected Results (Week 1):**
- Blutopia: 0.33 → 0.45-0.50 (H&R warning reduced)
- fearnopeer: 0.67 → 0.75-0.80 (safer status)
- upload.cx: 0.44 → 0.55-0.60 (above critical threshold)

---

### Phase 5: Long-term Monitoring

**Ongoing Maintenance:**

1. **Daily Checks (5 min):**
   - Monitor ratio on all 3 trackers
   - Check for H&R warnings (fix immediately)

2. **Weekly Checks (30 min):**
   - Review new releases captured by autobrr
   - Manually approve high-priority content
   - Verify seeding inventory health

3. **Monthly Checks (1 hour):**
   - Update tracker credentials if rotated
   - Review optimization rules (adjust for tracker health changes)
   - Backup configurations

4. **Email/Notification Setup (Optional):**
   - Configure Discord/Slack alerts for H&R warnings
   - Alert when ratio drops below 0.60 on any tracker
   - Alert for significant upload/download speed changes

---

## Quick Reference: Web UI URLs

```
Internal Network (trusted CIDR only):
  qBittorrent:  https://qbittorrent.homeops.ca        (Torrent client)
  autobrr:      https://autobrr.homeops.ca            (Release monitor)
  thelounge:    https://thelounge.homeops.ca          (IRC client)
  prowlarr:     https://prowlarr.homeops.ca           (Indexers)
  sonarr:       https://sonarr.homeops.ca             (TV auto-manager)
  radarr:       https://radarr.homeops.ca             (Movie auto-manager)
  qui:          https://qui.homeops.ca                (Alternative qBT UI)

API Endpoints (for scripts/automation):
  qBittorrent:  http://qbittorrent.default.svc.cluster.local:80/api/v2/
  autobrr:      http://autobrr.default.svc.cluster.local:80/api/
  prowlarr:     http://prowlarr.default.svc.cluster.local:80/api/
  sonarr:       http://sonarr.default.svc.cluster.local:80/api/
  radarr:       http://radarr.default.svc.cluster.local:80/api/
```

---

## Troubleshooting Checklist

### "Apps won't start after config changes"
- Check ConfigMap syntax: `KUBECONFIG=./kubeconfig kubectl get configmap qbittorrent-config -o yaml`
- Redeploy app: `KUBECONFIG=./kubeconfig kubectl rollout restart deployment/qbittorrent -n default`
- Check pod logs: `KUBECONFIG=./kubeconfig kubectl logs -l app.kubernetes.io/name=qbittorrent -n default -f`

### "Secrets not appearing in pods"
- Verify ExternalSecret exists: `KUBECONFIG=./kubeconfig kubectl get externalsecrets -n default`
- Check sync status: `KUBECONFIG=./kubeconfig kubectl describe externalsecret qbittorrent -n default`
- Verify Azure KV access: `KUBECONFIG=./kubeconfig kubectl logs -n external-secrets -l app=external-secrets -f | grep "qbittorrent"`

### "autobrr can't reach qBittorrent"
- Test from autobrr pod: `KUBECONFIG=./kubeconfig kubectl exec -it deploy/autobrr -n default -- curl http://qbittorrent:80/api/v2/app/version`
- Check network policy: `KUBECONFIG=./kubeconfig kubectl get networkpolicy -n default`
- Verify qBittorrent is healthy: `KUBECONFIG=./kubeconfig kubectl get pods -l app.kubernetes.io/name=qbittorrent -n default`

### "Ratio not improving despite seeding"
1. Check upload speed: Run speedtest from qBittorrent pod
2. Verify no firewall blocks: Check port 31288 is accessible externally
3. Check torrent peer count: Torrents with 0 seeds won't upload
4. Monitor bandwidth: Are you actually uploading or just connected?

---

## Optional: Run Auto-Setup Script

If you prefer automated initialization (less flexible but faster):

```bash
cd /home/sean/projects/talos/home-ops
./scripts/setup-torrent-ecosystem.sh
```

This will:
1. Create qBittorrent categories
2. Verify all app connectivity
3. Print configuration checklist

---

## References

- **Full Optimization Guide:** [docs/TORRENT-OPTIMIZATION.md](./TORRENT-OPTIMIZATION.md)
- **Credentials Setup:** [docs/TRACKER-CREDENTIALS-SETUP.md](./TRACKER-CREDENTIALS-SETUP.md)
- **Setup Script:** [scripts/setup-torrent-ecosystem.sh](./scripts/setup-torrent-ecosystem.sh)

---

## Support Resources

### Tracker Documentation
- Blutopia: https://blutopia.reseed.pro (forums, ratio rules, IRC guidelines)
- fearnopeer: https://fearnopeer.com (community standards)
- upload.cx: https://upload.cx (donor program details, H&R appeals)

### App Documentation
- [autobrr Docs](https://autobrr.com/docs)
- [qBittorrent Docs](https://github.com/qbittorrent/qBittorrent/wiki)
- [thelounge Docs](https://thelounge.chat/)
- [Prowlarr Docs](https://wiki.servarr.com/prowlarr)

---

## Status Summary

| Component | Status | Notes |
|-----------|--------|-------|
| qBittorrent | ✓ Running | Config optimized, ready |
| autobrr | ✓ Running | qBT integration ready, filters configured |
| thelounge | ✓ Running | Awaiting IRC credentials |
| prowlarr | ✓ Running | Awaiting indexer setup |
| sonarr | ✓ Running | Awaiting download client config |
| radarr | ✓ Running | Awaiting download client config |
| qui | ✓ Running | Ready (no setup needed) |
| **Tracker Credentials** | ⏳ Pending | Action required: Add to Azure KV |
| **Phase 1 Seeding** | ⏳ Pending | Ready to activate (all apps online) |
| **Phase 2 Filtering** | ⏳ Pending | After Phase 1 (5-7 days) |

---

**Next Action:** Add tracker credentials to Azure Key Vault (see [TRACKER-CREDENTIALS-SETUP.md](./TRACKER-CREDENTIALS-SETUP.md))
**Estimated Setup Time:** 2-3 hours
**Expected Result:** Fully automated torrent management with ratio recovery in progress

