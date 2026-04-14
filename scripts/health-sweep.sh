#!/usr/bin/env bash
set -euo pipefail

# Quick cluster health sweep focused on workloads and recent warnings.
# Usage:
#   KUBECONFIG=./kubeconfig ./scripts/health-sweep.sh

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required" >&2
  exit 1
fi

echo "== Cluster Context =="
kubectl config current-context || true
echo

echo "== Nodes =="
kubectl get nodes -o wide

echo
echo "== Pods In Bad States (excluding Completed) =="
kubectl get pods -A --no-headers | awk '$4 != "Running" && $4 != "Completed" {print}' || true

echo
echo "== Running Pods With Frequent Restarts (>= 10) =="
kubectl get pods -A --no-headers | awk '$4 == "Running" && $5 ~ /^[0-9]+$/ && $5 >= 10 {print}' || true

echo
echo "== Deployments With Unavailable Replicas =="
kubectl get deploy -A --no-headers | awk 'split($3,a,"/") && a[1] != a[2] {print}' || true

echo
echo "== StatefulSets Not Fully Ready =="
kubectl get sts -A --no-headers | awk 'split($3,a,"/") && a[1] != a[2] {print}' || true

echo
echo "== Jobs Failed =="
kubectl get jobs -A -o custom-columns='NAMESPACE:.metadata.namespace,NAME:.metadata.name,FAILED:.status.failed,SUCCEEDED:.status.succeeded,AGE:.metadata.creationTimestamp' --no-headers \
  | awk '$3 ~ /^[0-9]+$/ && $3 > 0 {print}' || true

echo
echo "== Recent Warning Events (last 2h) =="
kubectl get events -A --field-selector type=Warning --sort-by=.lastTimestamp 2>/dev/null | tail -n 200 || true

echo
echo "== Summary Complete =="
