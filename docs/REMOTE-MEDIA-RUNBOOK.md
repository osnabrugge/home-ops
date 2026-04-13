# Remote Media Reliability Runbook

## Scope

Use this runbook when `plex.homeops.ca` is reachable but playback fails, libraries show offline, or remote access drops intermittently.

## Fast triage (5 minutes)

1. Check Plex workload health.

```bash
kubectl -n default get pods -l app.kubernetes.io/name=plex -o wide
kubectl -n default logs deploy/plex --since=15m | tail -n 120
```

2. Check route attachment and backend wiring.

```bash
kubectl -n default get httproute plex-app plex-internal -o yaml | rg -n "Accepted|ResolvedRefs|port:"
kubectl -n default get svc plex -o yaml | rg -n "port: 32400|targetPort"
```

3. Check tunnel health and resolver errors.

```bash
kubectl -n network get pods -l app.kubernetes.io/name=cloudflare-tunnel -o wide
kubectl -n network logs deploy/cloudflare-tunnel --since=30m | rg -i "timeout|lookup|error|reconnect|disconnect"
```

4. Check gateway dataplane errors.

```bash
kubectl -n network logs deploy/envoy-external --since=30m | rg -i "route_not_found|no healthy upstream|503|timeout|reset"
```

## Synthetic checks and alert signals

- Gatus endpoint `Cloudflare Tunnel Ready` validates tunnel readiness at `http://cloudflare-tunnel.network.svc.cluster.local:8080/ready`.
- Gatus endpoint `Plex Routed Identity` validates gateway-to-plex routing using Host header `plex.homeops.ca`.
- HTTPRoute annotation on Plex (`group: external`) ensures outages trigger `GatusEndpointDown` alerts.

## If playback is failing but service is up

1. Confirm transcode path health.

```bash
kubectl -n default exec deploy/plex -- sh -lc 'df -h /transcode || true'
```

2. Confirm NFS media mount is present and readable.

```bash
kubectl -n default exec deploy/plex -- sh -lc 'ls /media | head -n 20'
```

3. Confirm direct backend identity responds.

```bash
kubectl -n default run curltest --image=curlimages/curl:8.12.1 --rm -i --restart=Never --command -- sh -lc "curl -sS -o /dev/null -w '%{http_code}\n' --max-time 10 http://plex.default.svc.cluster.local:32400/identity"
```

## Incident data to capture

- Local timestamp and timezone of failure.
- Client network type (cellular, guest Wi-Fi, VPN on/off).
- First symptom (`timeout`, `offline libraries`, `server unavailable`, playback never starts).
- Whether `requests.homeops.ca` failed simultaneously.

## Recovery actions

1. If tunnel logs show resolver timeouts repeatedly, restart tunnel deployment once and re-check.

```bash
kubectl -n network rollout restart deploy/cloudflare-tunnel
kubectl -n network rollout status deploy/cloudflare-tunnel --timeout=180s
```

2. If route resolution degraded, reconcile network ingress stack.

```bash
flux reconcile ks envoy-gateway -n network --with-source
flux reconcile ks cloudflare-tunnel -n network --with-source
```

3. If only Plex pod is degraded, roll only Plex.

```bash
kubectl -n default rollout restart deploy/plex
kubectl -n default rollout status deploy/plex --timeout=300s
```
