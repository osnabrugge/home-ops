# QUICK REFERENCE: Torrent Setup Checklist

## ✅ COMPLETED (15 files)

- [x] 7 apps deployed and running (qBittorrent, autobrr, thelounge, prowlarr, sonarr, radarr, qui)
- [x] qBittorrent ConfigMap (optimized seeding: 3.0 ratio, 72h seed time)
- [x] autobrr ConfigMap (H&R-safe filters per tracker)
- [x] thelounge ConfigMap (IRC network templates)
- [x] 4 HelmRelease files updated with config mounts
- [x] ExternalSecret extended for tracker credentials
- [x] 4 comprehensive documentation files (2,500+ lines)
- [x] Automation setup script (executable)
- [x] All ConfigMaps deployed to cluster

## ⏳ YOUR TODO (Next 6-8 Hours)

### STEP 1: Add Tracker Credentials (2-4 hours) - START HERE
```bash
# Read this first:
cat docs/TRACKER-CREDENTIALS-SETUP.md

# Then collect from tracker accounts:
# - Blutopia: passkey, IRC nick, IRC password
# - fearnopeer: authkey, IRC nick, IRC password
# - upload.cx: infohash, IRC nick, IRC password

# Run Azure CLI commands from guide to add to KeyVault
az keyvault secret set --vault-name "homeops-ca" \
  --name "autobrr-blutopia-passkey" \
  --value "YOUR_PASSKEY_HERE"
# (see guide for all commands)

# Verify sync:
KUBECONFIG=./kubeconfig kubectl get externalsecrets -n default -w
# Wait for Status: Success
```

### STEP 2: Configure IRC Servers (1 hour)
```
1. Open https://thelounge.homeops.ca
2. Add network: Blutopia
   - Host: irc.blutopia.xyz, Port: 6697, TLS: Yes
   - Use your Blutopia IRC nick + password
3. Repeat for fearnopeer and upload.cx
4. Verify: See releases in #announce
```

### STEP 3: Configure Indexers (1 hour)
```
1. Open https://prowlarr.homeops.ca
2. Settings → Indexers → Add:
   - Blutopia (Cardigann)
   - fearnopeer (Cardigann)
   - upload.cx (Cardigann)
3. Settings → Apps:
   - Add sonarr: http://sonarr.default.svc.cluster.local:80
   - Add radarr: http://radarr.default.svc.cluster.local:80
4. Test each (should show "Online")
```

### STEP 4: Connect Download Clients (1 hour)
```
sonarr (https://sonarr.homeops.ca):
  1. Settings → Download Clients → Add qBittorrent
  2. Host: qbittorrent.default.svc.cluster.local
  3. Port: 80
  4. Category: tv
  5. Remote path mapping: /data → /data

radarr (https://radarr.homeops.ca):
  1. Settings → Download Clients → Add qBittorrent
  2. Host: qbittorrent.default.svc.cluster.local
  3. Port: 80
  4. Category: movies
  5. Remote path mapping: /data → /data
```

### STEP 5: Activate Phase 1 - Seeding Only (5 minutes)
```
1. Open https://autobrr.homeops.ca
   - Disable all filters (freeze new downloads)

2. Open https://qbittorrent.homeops.ca
   - Settings → Queueing → Max Active Downloads: 0
   - Verify seeding (should see current torrents)

3. Monitor ratio daily:
   - Blutopia: Target 0.33 → 0.45
   - fearnopeer: Target 0.67 → 0.75
   - upload.cx: Target 0.44 → 0.55

4. Expected result: Visible improvement in week 1
```

## 📖 Documentation Files

```
Read in this order:

1. docs/TORRENT-SETUP-ACTION-PLAN.md
   → High-level implementation checklist

2. docs/TRACKER-CREDENTIALS-SETUP.md
   → How to find & add credentials

3. docs/TORRENT-OPTIMIZATION.md
   → Complete strategy & troubleshooting

4. docs/TORRENT-IMPLEMENTATION-SUMMARY.md
   → Detailed overview of what's been done
```

## 🌐 Web UI URLs (Internal Network Only)

```
qBittorrent:  https://qbittorrent.homeops.ca
autobrr:      https://autobrr.homeops.ca
thelounge:    https://thelounge.homeops.ca
prowlarr:     https://prowlarr.homeops.ca
sonarr:       https://sonarr.homeops.ca
radarr:       https://radarr.homeops.ca
qui:          https://qui.homeops.ca
```

## ⏱️ Timeline

```
Now:        Everything ready ✓
+4h:        Credentials added → Phase 2 unlocked
+5h:        IRC connected → Real-time alerts active
+6h:        Indexers configured → Smart filtering ready
+7h:        Download clients connected → Full automation ready
+7.5h:      Phase 1 activated → Seeding begins
+7-14 days: Phase 1 complete → Ratio improved +0.15 per tracker
```

## 🎯 Success Metrics

**Phase 1 Target (Week 1):**
- Blutopia: 0.45+ (from 0.33)
- fearnopeer: 0.75+ (from 0.67)
- upload.cx: 0.55+ (from 0.44)
- Status: H&R warnings reduced or eliminated

**Phase 2 Start (Week 2):**
- All ratios stable/improving
- Ready to resume selective downloads
- autobrr filters re-enabled (cautiously)

**Phase 3 (Ongoing):**
- Full automation active
- Healthy ratios sustained
- Community trust restored

## 🚨 Critical Don'ts

❌ Don't skip adding credentials
❌ Don't enable Phase 2 before week 1 complete
❌ Don't download if ratio dropping (emergency seeding mode)
❌ Don't ignore H&R warnings (address immediately)
❌ Don't exceed seeding limits (respect tracker rules)

## 🔍 Verification Commands

```bash
# Check all apps running
KUBECONFIG=./kubeconfig kubectl get deployments -n default | grep -E "qbit|autobrr|thelounge|prowlarr|sonarr|radarr|qui"

# Check ConfigMaps deployed
KUBECONFIG=./kubeconfig kubectl get configmaps -n default | grep -E "qbit|autobrr|thelounge"

# Check ExternalSecrets status
KUBECONFIG=./kubeconfig kubectl get externalsecrets -n default -w

# Check pod logs
KUBECONFIG=./kubeconfig kubectl logs -l app.kubernetes.io/name=autobrr -n default -f
```

## 📝 Git Commit

When ready:
```bash
git add -A
git commit -m "feat: auto-configure torrent ecosystem for ratio recovery"
```

---

**Status:** ✅ All infrastructure ready, awaiting credentials
**Next Action:** Read docs/TRACKER-CREDENTIALS-SETUP.md
**Expected Result:** +0.15 ratio per tracker in week 1

