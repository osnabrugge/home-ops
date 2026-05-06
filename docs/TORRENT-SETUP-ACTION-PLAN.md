# Torrent Ecosystem Configuration Action Plan

**Status Date:** May 5, 2026
**Status:** Infrastructure mostly in place, credential population and app-level verification still pending
**Priority:** Restore stable torrent automation without publishing tracker-identifying details in the repository

---

## Current State

The following applications are part of the torrent workflow in this cluster:
- qBittorrent
- autobrr
- thelounge
- prowlarr
- sonarr
- radarr
- qui

At a high level, the remaining work is:
- populate Azure Key Vault with the required app secrets
- verify ExternalSecrets synchronization
- complete the remaining web UI configuration for indexers, download clients, and IRC
- validate seeding behavior conservatively before enabling more automation

This document intentionally avoids naming private trackers, account state, ratio values, or private endpoints.

---

## Phase 1: Populate App Secrets

Use the consolidated secret model documented in [docs/TRACKER-CREDENTIALS-SETUP.md](/home/sean/projects/talos/home-ops/docs/TRACKER-CREDENTIALS-SETUP.md).

Create or update one Azure Key Vault secret per app:
- `qbittorrent`
- `autobrr`
- `thelounge`
- `prowlarr`
- `sonarr`
- `radarr`

Verification:

```bash
KUBECONFIG=./kubeconfig kubectl get externalsecrets -n default
KUBECONFIG=./kubeconfig kubectl get secrets -n default | grep -E "qbittorrent|autobrr|thelounge|prowlarr|sonarr|radarr"
```

Expected result:
- each app secret appears in Kubernetes
- each ExternalSecret reports a healthy sync status

---

## Phase 2: Finish Application Wiring

### thelounge

- add the required IRC networks manually in the web UI
- use credentials stored in the `thelounge` secret
- confirm the client connects and joins the expected channels

### prowlarr

- add the required private indexers manually
- test each indexer before saving
- keep tracker-specific URLs and tokens out of committed documentation

### sonarr and radarr

- connect qBittorrent as the download client
- connect to prowlarr for indexer synchronization
- verify categories and remote path mappings are correct

### autobrr

- confirm qBittorrent integration works
- start with conservative filters and manual approval where uncertainty remains
- avoid enabling broad automatic grabs until seeding performance is understood

---

## Phase 3: Controlled Activation

Bring the workflow online in a conservative order:

1. Confirm existing torrents can seed reliably.
2. Confirm no new hold-or-remove style violations are being created.
3. Keep new automated downloads limited until upload behavior is stable.
4. Increase automation only after reviewing actual tracker-side results.

Recommended guardrails:
- prefer long seed times over aggressive cleanup
- cap concurrent activity until storage and tracker behavior are stable
- use manual approval or narrow filters for risky feeds

---

## Phase 4: Validation Checklist

- [ ] Azure Key Vault secrets created for each app
- [ ] ExternalSecrets synced successfully
- [ ] qBittorrent web UI accessible
- [ ] autobrr can reach qBittorrent
- [ ] thelounge can connect to required IRC networks
- [ ] prowlarr indexers test successfully
- [ ] sonarr and radarr can send jobs to qBittorrent
- [ ] new automation is still limited and observed closely
- [ ] seeding behavior improves before scaling up automation

---

## Web Interfaces

Internal interfaces currently expected in this setup:

- https://qbittorrent.homeops.ca
- https://autobrr.homeops.ca
- https://thelounge.homeops.ca
- https://prowlarr.homeops.ca
- https://sonarr.homeops.ca
- https://radarr.homeops.ca
- https://qui.homeops.ca

Cluster-local APIs:

- http://qbittorrent.default.svc.cluster.local:80/api/v2/
- http://autobrr.default.svc.cluster.local:80/api/
- http://prowlarr.default.svc.cluster.local:80/api/
- http://sonarr.default.svc.cluster.local:80/api/
- http://radarr.default.svc.cluster.local:80/api/

---

## Troubleshooting

### Secrets missing from Kubernetes

```bash
KUBECONFIG=./kubeconfig kubectl describe externalsecret qbittorrent -n default
KUBECONFIG=./kubeconfig kubectl logs -n external-secrets deploy/external-secrets | grep qbittorrent
```

### qBittorrent integration problems

```bash
KUBECONFIG=./kubeconfig kubectl get pods -n default -l app.kubernetes.io/name=qbittorrent
KUBECONFIG=./kubeconfig kubectl logs -n default -l app.kubernetes.io/name=qbittorrent --tail=100
```

### autobrr cannot reach qBittorrent

```bash
KUBECONFIG=./kubeconfig kubectl exec -n default deploy/autobrr -- curl -fsS http://qbittorrent:80/api/v2/app/version
```

### General rule for private tracker details

Tracker-specific URLs, rules, ratio state, forum links, and IRC endpoints should live outside the repository in a private note or password manager.

---

## Next Step

Populate the consolidated app secrets first. That is the clean boundary between infrastructure already committed here and the private operational details that should stay out of Git.
