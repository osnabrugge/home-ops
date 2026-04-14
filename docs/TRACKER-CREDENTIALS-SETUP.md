# Tracker Credentials Setup Guide

## Azure Key Vault Secrets Required

The following secrets must be created in Azure Key Vault for the torrent ecosystem to function. These are injected via ExternalSecrets into Kubernetes.

### For qBittorrent
**Key names (Azure KV):**
- `qbittorrent-password` - Web UI admin password
- `qbittorrent-blutopia-passkey` - Blutopia passkey
- `qbittorrent-fearnopeer-authkey` - fearnopeer authkey
- `qbittorrent-uploadcx-infohash` - upload.cx infohash/magnet credentials

**How to set (via Azure CLI):**
```bash
# Blutopia tracker credentials
az keyvault secret set \
  --vault-name "homeops-ca" \
  --name "qbittorrent-blutopia-passkey" \
  --value "YOUR_BLUTOPIA_PASSKEY_HERE"

# fearnopeer tracker credentials
az keyvault secret set \
  --vault-name "homeops-ca" \
  --name "qbittorrent-fearnopeer-authkey" \
  --value "YOUR_FEARNOPEER_AUTHKEY_HERE"

# upload.cx tracker credentials
az keyvault secret set \
  --vault-name "homeops-ca" \
  --name "qbittorrent-uploadcx-infohash" \
  --value "YOUR_UPLOADCX_INFOHASH_HERE"

# Web UI password
az keyvault secret set \
  --vault-name "homeops-ca" \
  --name "qbittorrent-password" \
  --value "STRONG_RANDOM_PASSWORD_HERE"
```

### For autobrr
**Key names (Azure KV):**
- `autobrr-session-secret` - Session encryption key
- `autobrr-blutopia-passkey` - Blutopia API/announce key
- `autobrr-fearnopeer-authkey` - fearnopeer API key
- `autobrr-uploadcx-infohash` - upload.cx credentials

**How to set:**
```bash
# Session secret (generate random: openssl rand -base64 32)
az keyvault secret set \
  --vault-name "homeops-ca" \
  --name "autobrr-session-secret" \
  --value "$(openssl rand -base64 32)"

# Tracker credentials
az keyvault secret set \
  --vault-name "homeops-ca" \
  --name "autobrr-blutopia-passkey" \
  --value "YOUR_BLUTOPIA_PASSKEY_HERE"

az keyvault secret set \
  --vault-name "homeops-ca" \
  --name "autobrr-fearnopeer-authkey" \
  --value "YOUR_FEARNOPEER_AUTHKEY_HERE"

az keyvault secret set \
  --vault-name "homeops-ca" \
  --name "autobrr-uploadcx-infohash" \
  --value "YOUR_UPLOADCX_INFOHASH_HERE"
```

### For thelounge (IRC)
**Key names (Azure KV):**
- `thelounge-blutopia-irc-nick` - IRC nickname
- `thelounge-blutopia-irc-password` - IRC password (if required)
- `thelounge-fearnopeer-irc-nick` - IRC nickname
- `thelounge-fearnopeer-irc-password` - IRC password
- `thelounge-uploadcx-irc-nick` - IRC nickname
- `thelounge-uploadcx-irc-password` - IRC password

**How to set:**
```bash
az keyvault secret set \
  --vault-name "homeops-ca" \
  --name "thelounge-blutopia-irc-nick" \
  --value "YOUR_BLUTOPIA_IRC_NICK"

az keyvault secret set \
  --vault-name "homeops-ca" \
  --name "thelounge-blutopia-irc-password" \
  --value "YOUR_BLUTOPIA_IRC_PASSWORD"

# Repeat for fearnopeer and upload.cx
```

### For prowlarr
**Key names (Azure KV):**
- `prowlarr-password` - Web UI password
- `prowlarr-blutopia-passkey` - For indexer defintion
- `prowlarr-fearnopeer-authkey` - For indexer definition
- `prowlarr-uploadcx-infohash` - For indexer definition

**How to set:**
```bash
az keyvault secret set \
  --vault-name "homeops-ca" \
  --name "prowlarr-password" \
  --value "STRONG_RANDOM_PASSWORD"

# Indexer definitions (usually configured in web UI, not as secrets)
```

### For sonarr/radarr
**Key names (Azure KV):**
- `sonarr-password` - Web UI password
- `radarr-password` - Web UI password

**How to set:**
```bash
az keyvault secret set \
  --vault-name "homeops-ca" \
  --name "sonarr-password" \
  --value "STRONG_RANDOM_PASSWORD"

az keyvault secret set \
  --vault-name "homeops-ca" \
  --name "radarr-password" \
  --value "STRONG_RANDOM_PASSWORD"
```

---

## Finding Your Tracker Credentials

### Blutopia
1. Log in to https://blutopia.reseed.pro
2. Go to **Profile** → **Security**
3. Find "Passkey" or "API Key"
4. Copy the full value

### fearnopeer
1. Log in to https://fearnopeer.com
2. Go to **Profile** → **Settings**
3. Look for "Authentication Token" or "API Key"
4. Copy the value

### upload.cx
1. Log in to https://upload.cx
2. Go to **Account** → **Security**
3. Find "Infohash Auth" or similar
4. Request new credentials if needed

### IRC Details

**Blutopia IRC:**
- Server: `irc.blutopia.xyz` (port 6697 TLS)
- Nickname: Your tracker username
- Password: Usually same as tracker password
- Channels: `#announce`, `#general`, `#staff` (if available)

**fearnopeer IRC:**
- Server: `irc.fearnopeer.com` (port 6697 TLS)
- Nickname: Your tracker username
- Password: Request from admin or same as tracker login
- Channels: `#announce`, `#general`

**upload.cx IRC:**
- Server: `irc.upload.cx` (port 6697 TLS)
- Nickname: Your tracker username
- Password: Usually same as tracker password
- Channels: `#announce`, `#staff`

---

## Verifying Secrets in Kubernetes

After adding to Azure KV, verify they're synced to Kubernetes:

```bash
# Check if ExternalSecrets have synced
KUBECONFIG=./kubeconfig kubectl get externalsecrets -n default -o wide

# Check if secrets exist
KUBECONFIG=./kubeconfig kubectl get secrets -n default | grep -E "qbittorrent|autobrr|thelounge|prowlarr"

# View secret content (decoded)
KUBECONFIG=./kubeconfig kubectl get secret qbittorrent-secret -o jsonpath='{.data}'
```

---

## Post-Deployment Configuration Checklist

- [ ] All tracker credentials added to Azure KV
- [ ] ExternalSecrets synced (watch `kubectl get externalsecrets -w`)
- [ ] qBittorrent Web UI accessible (https://qbittorrent.homeops.ca)
- [ ] qBittorrent configured with proper seeding rules (see TORRENT-OPTIMIZATION.md)
- [ ] autobrr configured with tracker filters
- [ ] thelounge connected to IRC servers
- [ ] prowlarr configured with indexers
- [ ] sonarr/radarr linked to qBittorrent + prowlarr
- [ ] qui (alternative UI) accessible as backup
- [ ] Seeding phase 1 activated (pause downloads, focus on existing seeds)

---

## Troubleshooting

### "Secret not found" errors in logs
```bash
# Check ExternalSecret status
KUBECONFIG=./kubeconfig kubectl describe externalsecret qbittorrent -n default

# Check Azure KV access
KUBECONFIG=./kubeconfig kubectl logs -n external-secrets deploy/external-secrets -f | grep "qbittorrent"
```

### Tracker credentials not working
1. Verify in Azure KV: `az keyvault secret show --vault-name "homeops-ca" --name "thekey"`
2. Ensure no extra whitespace/newlines
3. For API keys: verify they're still valid (not revoked/expired)
4. Check app logs for authentication failures

### "Cannot connect to tracker" in qBittorrent
1. Verify netcat reachability from pod: `kubectl exec -it qbittorrent-xxx -- nc -zv tracker.example.com 80`
2. Check firewall rules on NAS02
3. Verify passkey is correctly added to `.torrent` file

---

## References

- [docs/TORRENT-OPTIMIZATION.md](./TORRENT-OPTIMIZATION.md) - Full optimization guide
- [scripts/setup-torrent-ecosystem.sh](../scripts/setup-torrent-ecosystem.sh) - Auto-setup script
- Tracker documentation (consult official wiki/forums)
- [autobrr docs](https://autobrr.com/)
- [qBittorrent docs](https://github.com/qbittorrent/qBittorrent/wiki)

