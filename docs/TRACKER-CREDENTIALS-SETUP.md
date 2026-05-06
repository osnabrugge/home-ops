# Tracker Credentials Setup Guide

## Purpose

This guide documents how to store torrent-related credentials in Azure Key Vault and expose them to applications through ExternalSecrets.

Sensitive operational details should stay out of the repository:
- Do not commit tracker names, tracker URLs, IRC hosts, usernames, ratio state, or account history.
- Do not encode one secret per tracker unless the workload already requires it.
- Prefer one Azure Key Vault secret per app or service, matching the existing ExternalSecret pattern already used in this repository.

## Secret Layout

The current convention in this repository is:
- One Azure Key Vault secret object per app or service.
- One Kubernetes Secret per app or service.
- ExternalSecrets use `dataFrom.extract` to pull the full object.

For example, [kubernetes/apps/default/qbittorrent/app/externalsecret.yaml](/home/sean/projects/talos/home-ops/kubernetes/apps/default/qbittorrent/app/externalsecret.yaml) extracts a single Azure Key Vault secret named `qbittorrent` into the Kubernetes Secret `qbittorrent-secret`.

## Recommended Azure Key Vault Secrets

Create one secret object for each app that needs credentials:
- `qbittorrent`
- `autobrr`
- `thelounge`
- `prowlarr`
- `sonarr`
- `radarr`

Each secret should contain only the fields that app actually consumes.

## Example Secret Shapes

### qBittorrent

Suggested fields:
- `QBITTORRENT_USERNAME`
- `QBITTORRENT_PASSWORD`
- `TRACKER_1_PASSKEY`
- `TRACKER_2_AUTHKEY`
- `TRACKER_3_TOKEN`

### autobrr

Suggested fields:
- `AUTOBRR_SESSION_SECRET`
- `TRACKER_1_ANNOUNCE_KEY`
- `TRACKER_2_ANNOUNCE_KEY`
- `TRACKER_3_ANNOUNCE_KEY`

### thelounge

Suggested fields:
- `IRC_NETWORK_1_NICK`
- `IRC_NETWORK_1_PASSWORD`
- `IRC_NETWORK_2_NICK`
- `IRC_NETWORK_2_PASSWORD`
- `IRC_NETWORK_3_NICK`
- `IRC_NETWORK_3_PASSWORD`

### prowlarr

Suggested fields:
- `PROWLARR_USERNAME`
- `PROWLARR_PASSWORD`
- `INDEXER_1_API_KEY`
- `INDEXER_2_API_KEY`
- `INDEXER_3_API_KEY`

### sonarr and radarr

Suggested fields:
- `SONARR_USERNAME`
- `SONARR_PASSWORD`
- `RADARR_USERNAME`
- `RADARR_PASSWORD`

## Creating Secrets In Azure Key Vault

Store each app secret as a single JSON object.

Example for `qbittorrent`:

```bash
az keyvault secret set \
  --vault-name "homeops-ca" \
  --name "qbittorrent" \
  --value '{
    "QBITTORRENT_USERNAME": "admin",
    "QBITTORRENT_PASSWORD": "REPLACE_ME",
    "TRACKER_1_PASSKEY": "REPLACE_ME",
    "TRACKER_2_AUTHKEY": "REPLACE_ME",
    "TRACKER_3_TOKEN": "REPLACE_ME"
  }'
```

Example for `autobrr`:

```bash
az keyvault secret set \
  --vault-name "homeops-ca" \
  --name "autobrr" \
  --value '{
    "AUTOBRR_SESSION_SECRET": "REPLACE_ME",
    "TRACKER_1_ANNOUNCE_KEY": "REPLACE_ME",
    "TRACKER_2_ANNOUNCE_KEY": "REPLACE_ME",
    "TRACKER_3_ANNOUNCE_KEY": "REPLACE_ME"
  }'
```

Generate long random values for session secrets and passwords.

```bash
openssl rand -base64 32
```

## ExternalSecret Pattern

The preferred Kubernetes pattern is a single extract per app.

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: qbittorrent
spec:
  refreshInterval: 5m
  secretStoreRef:
    kind: ClusterSecretStore
    name: azurekv
  target:
    name: qbittorrent-secret
  dataFrom:
    - extract:
        key: qbittorrent
```

If an application needs renamed fields, use `target.template.data` to map the extracted values to the exact environment variable names the chart expects.

## Verification

After adding or updating a Key Vault secret, verify it syncs into Kubernetes.

```bash
KUBECONFIG=./kubeconfig kubectl get externalsecrets -n default
KUBECONFIG=./kubeconfig kubectl describe externalsecret qbittorrent -n default
KUBECONFIG=./kubeconfig kubectl get secret qbittorrent-secret -n default -o yaml
```

## Operational Guidance

- Keep tracker-specific notes in a private password manager or a local untracked file.
- Keep this repository limited to app-level secret shapes and deployment wiring.
- If you later decide to split a single app secret into multiple secrets, do it only when there is a concrete operational reason such as separate ownership, separate rotation cadence, or distinct access controls.

## Troubleshooting

### Secret not syncing

```bash
KUBECONFIG=./kubeconfig kubectl describe externalsecret qbittorrent -n default
KUBECONFIG=./kubeconfig kubectl logs -n external-secrets deploy/external-secrets | grep qbittorrent
```

### Secret shape mismatch

If the Kubernetes Secret exists but the app still fails to authenticate:
- confirm the Azure Key Vault object contains the expected field names
- confirm the ExternalSecret template maps fields correctly
- confirm the application chart reads those environment variables or mounted keys

## References

- [docs/TORRENT-SETUP-ACTION-PLAN.md](/home/sean/projects/talos/home-ops/docs/TORRENT-SETUP-ACTION-PLAN.md)
- [docs/TORRENT-OPTIMIZATION.md](/home/sean/projects/talos/home-ops/docs/TORRENT-OPTIMIZATION.md)
- [kubernetes/apps/default/qbittorrent/app/externalsecret.yaml](/home/sean/projects/talos/home-ops/kubernetes/apps/default/qbittorrent/app/externalsecret.yaml)
