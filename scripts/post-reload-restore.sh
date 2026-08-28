#!/usr/bin/env bash
# Restore the cluster after the core01 switch reload.
#
# Reverses scripts-free shutdown performed 2026-08-28:
#   - Flux suspended (130 Kustomizations, 97 HelmReleases)
#   - 81 workloads scaled to 0 (replica counts saved)
#   - CNPG postgres16 hibernated
#   - kopiur controller/webhook scaled to 0
#   - 5 CronJobs suspended
#   - Ceph flags: noout, norebalance, nobackfill, norecover
#
# Run steps IN ORDER and check between them. Do not run blind.
set -uo pipefail
cd "$(dirname "$0")/.."
export KUBECONFIG="$PWD/kubeconfig"
export TALOSCONFIG="$PWD/talosconfig"

STATE=/tmp/preload/replicas.txt
[[ -f "$STATE" ]] || STATE="$HOME/preload-replicas.txt"

step() { echo; echo "=== $* ==="; }

step "1. Node and Ceph reachability (STOP if nodes are not Ready)"
kubectl get nodes
ceph() { kubectl -n rook-ceph exec "$(kubectl -n rook-ceph get pod -l app=rook-ceph-tools \
  --no-headers | awk '$3=="Running"{print $1}' | head -1)" -- ceph "$@"; }
ceph status | head -12

read -r -p "Nodes Ready and mons in quorum? [y/N] " a; [[ "$a" == "y" ]] || exit 1

step "2. Clear Ceph maintenance flags"
# Order matters: let peering settle before allowing data movement.
for f in norecover nobackfill norebalance noout; do ceph osd unset "$f"; done
ceph status | head -12

step "3. Wait for HEALTH_OK (or at least all PGs active) before restarting workloads"
for i in $(seq 1 60); do
  h=$(ceph health 2>/dev/null | head -1)
  echo "  $i: $h"
  [[ "$h" == HEALTH_OK* ]] && break
  sleep 15
done

read -r -p "Ceph healthy enough to proceed? [y/N] " a; [[ "$a" == "y" ]] || exit 1

step "4. Restore backup operator"
kubectl scale deploy kopiur-controller -n kopiur-system --replicas=1
kubectl scale deploy kopiur-webhook   -n kopiur-system --replicas=1

step "5. Wake Postgres"
kubectl scale deploy cloudnative-pg -n database --replicas=1
kubectl annotate cluster.postgresql.cnpg.io postgres16 -n database \
  --overwrite cnpg.io/hibernation=off
echo "waiting for postgres pods..."
for i in $(seq 1 30); do
  n=$(kubectl get pods -n database --no-headers 2>/dev/null | grep -c '^postgres16-')
  echo "  postgres pods: $n"; [[ "$n" -ge 1 ]] && break; sleep 10
done

step "6. Restore workload replica counts"
while IFS='|' read -r ns kind name reps; do
  [[ -z "${name:-}" ]] && continue
  kubectl scale "$(echo "$kind" | tr 'A-Z' 'a-z')/$name" -n "$ns" --replicas="$reps" 2>/dev/null \
    && echo "  $ns/$name -> $reps"
done < "$STATE"

step "7. Un-suspend CronJobs"
for r in $(kubectl get cronjob -A -o jsonpath='{range .items[*]}{.metadata.namespace}|{.metadata.name}{"\n"}{end}'); do
  kubectl patch cronjob "${r#*|}" -n "${r%|*}" --type=merge -p '{"spec":{"suspend":false}}' >/dev/null 2>&1
done

step "8. Resume Flux LAST (it will reconcile everything back to git)"
for r in $(kubectl get hr -A -o jsonpath='{range .items[*]}{.metadata.namespace}|{.metadata.name}{"\n"}{end}'); do
  kubectl patch hr "${r#*|}" -n "${r%|*}" --type=merge -p '{"spec":{"suspend":false}}' >/dev/null 2>&1
done
for r in $(kubectl get kustomization -A -o jsonpath='{range .items[*]}{.metadata.namespace}|{.metadata.name}{"\n"}{end}'); do
  kubectl patch kustomization "${r#*|}" -n "${r%|*}" --type=merge -p '{"spec":{"suspend":false}}' >/dev/null 2>&1
done

step "9. Post-reload check — the network WILL have wedged some RBD volumes"
just kube rbd-ro
echo
echo "If any volumes are listed above, pod deletion will NOT fix them."
echo "Reboot the affected node:  ceph osd set noout; talosctl -n <ip> reboot; ceph osd unset noout"
