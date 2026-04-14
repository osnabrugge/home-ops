#!/bin/bash
# Torrent Ecosystem Auto-Configuration Script
# Purpose: Initialize and connect qBittorrent, autobrr, thelounge, prowlarr, sonarr, radarr
# Usage: ./setup-torrent-ecosystem.sh

set -euo pipefail

KUBECONFIG="${KUBECONFIG:-./kubeconfig}"
NAMESPACE="default"

echo "🎬 Torrent Ecosystem Auto-Configuration"
echo "======================================="
echo ""

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check prerequisites
check_prerequisites() {
  log_info "Checking prerequisites..."

  if ! command -v kubectl &> /dev/null; then
    log_error "kubectl not found. Please install kubectl."
    exit 1
  fi

  if ! command -v curl &> /dev/null; then
    log_error "curl not found. Please install curl."
    exit 1
  fi

  log_info "Prerequisites OK"
}

# Wait for pod to be ready
wait_for_pod() {
  local pod_name=$1
  local timeout=${2:-300}

  log_info "Waiting for $pod_name to be ready (max ${timeout}s)..."

  KUBECONFIG="$KUBECONFIG" kubectl wait --for=condition=ready pod \
    -l app.kubernetes.io/name="$pod_name" \
    -n "$NAMESPACE" \
    --timeout="${timeout}s" 2>/dev/null || return 1
}

# Get service endpoint (internal)
get_service_endpoint() {
  local service_name=$1
  echo "${service_name}.${NAMESPACE}.svc.cluster.local"
}

# qBittorrent initialization
init_qbittorrent() {
  log_info "Configuring qBittorrent..."

  local qbt_pod=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n "$NAMESPACE" \
    -l app.kubernetes.io/name=qbittorrent -o jsonpath='{.items[0].metadata.name}')

  if [ -z "$qbt_pod" ]; then
    log_error "qBittorrent pod not found"
    return 1
  fi

  # Create qBittorrent categories via API
  log_info "Creating qBittorrent categories..."

  local categories=("monitored" "manual" "tv" "movies" "unsorted")

  for category in "${categories[@]}"; do
    KUBECONFIG="$KUBECONFIG" kubectl exec "$qbt_pod" -n "$NAMESPACE" -- \
      curl -s -X POST "http://localhost:80/api/v2/torrents/createCategory" \
      -d "category=$category" \
      -d "savePath=/data/downloads/$category" || true
  done

  log_info "qBittorrent categories created"
}

# autobrr initialization
init_autobrr() {
  log_info "Configuring autobrr..."

  # Check if autobrr config exists in PVC
  local autobrr_pod=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n "$NAMESPACE" \
    -l app.kubernetes.io/name=autobrr -o jsonpath='{.items[0].metadata.name}')

  if [ -z "$autobrr_pod" ]; then
    log_error "autobrr pod not found"
    return 1
  fi

  # Verify autobrr can reach qBittorrent
  log_info "Testing autobrr → qBittorrent connectivity..."
  KUBECONFIG="$KUBECONFIG" kubectl exec "$autobrr_pod" -n "$NAMESPACE" -- \
    curl -s -I "http://qbittorrent.${NAMESPACE}.svc.cluster.local:80/api/v2/app/version" \
    | grep -q "200\|405" && log_info "✓ autobrr can reach qBittorrent" || log_error "✗ autobrr cannot reach qBittorrent"

  log_info "autobrr configuration complete"
}

# thelounge initialization
init_thelounge() {
  log_info "Configuring thelounge IRC client..."

  local thelounge_pod=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n "$NAMESPACE" \
    -l app.kubernetes.io/name=thelounge -o jsonpath='{.items[0].metadata.name}')

  if [ -z "$thelounge_pod" ]; then
    log_error "thelounge pod not found"
    return 1
  fi

  log_warn "thelounge requires manual IRC configuration:"
  log_warn "1. Access https://thelounge.homeops.ca"
  log_warn "2. Click 'Settings' → 'Networks'"
  log_warn "3. Add networks for: Blutopia, fearnopeer, upload.cx"
  log_warn "4. Use your tracker IRC credentials"
  log_warn "5. Join #announce and #general channels"
}

# prowlarr initialization
init_prowlarr() {
  log_info "Configuring prowlarr indexer..."

  local prowlarr_pod=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n "$NAMESPACE" \
    -l app.kubernetes.io/name=prowlarr -o jsonpath='{.items[0].metadata.name}')

  if [ -z "$prowlarr_pod" ]; then
    log_error "prowlarr pod not found"
    return 1
  fi

  # Test prowlarr connectivity
  log_info "Testing prowlarr connectivity..."
  KUBECONFIG="$KUBECONFIG" kubectl exec "$prowlarr_pod" -n "$NAMESPACE" -- \
    curl -s -I "http://localhost:80/ping" | grep -q "200\|405" && log_info "✓ prowlarr is responding" || log_error "✗ prowlarr not responding"

  log_warn "prowlarr requires manual configuration:"
  log_warn "1. Access https://prowlarr.homeops.ca"
  log_warn "2. Click 'Settings' → 'Indexers'"
  log_warn "3. Add indexers for: Blutopia, fearnopeer, upload.cx (use Cardigann)"
  log_warn "4. Click 'Settings' → 'Apps' and add:"
  log_warn "   - sonarr instance: http://sonarr.${NAMESPACE}.svc.cluster.local:80"
  log_warn "   - radarr instance: http://radarr.${NAMESPACE}.svc.cluster.local:80"
  log_warn "   - autobrr instance: http://autobrr.${NAMESPACE}.svc.cluster.local:80"
}

# sonarr/radarr initialization
init_sonarr_radarr() {
  log_info "Configuring sonarr and radarr..."

  for app in sonarr radarr; do
    local pod=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n "$NAMESPACE" \
      -l app.kubernetes.io/name="$app" -o jsonpath='{.items[0].metadata.name}')

    if [ -z "$pod" ]; then
      log_warn "$app pod not found"
      continue
    fi

    # Test connectivity
    log_info "Testing $app connectivity..."
    KUBECONFIG="$KUBECONFIG" kubectl exec "$pod" -n "$NAMESPACE" -- \
      curl -s -I "http://localhost:80/ping" | grep -q "200\|405" && log_info "✓ $app is responding" || log_error "✗ $app not responding"
  done

  log_warn "sonarr/radarr require manual configuration:"
  log_warn "1. Access https://sonarr.homeops.ca and https://radarr.homeops.ca"
  log_warn "2. Settings → Download Clients:"
  log_warn "   - Add qBittorrent: qbittorrent.${NAMESPACE}.svc.cluster.local:80"
  log_warn "   - Category: tv (sonarr) / movies (radarr)"
  log_warn "   - Remote path mapping: /data → /data"
  log_warn "3. Settings → Indexers:"
  log_warn "   - Add prowlarr sync"
  log_warn "4. Settings → Quality Profiles:"
  log_warn "   - Create profiles for: 1080p/BluRay (TV), 2160p/BluRay (Movies)"
}

# Verify all connectivity
verify_ecosystem() {
  log_info "Verifying ecosystem connectivity..."

  local checks_passed=0
  local checks_total=0

  # List of apps to check
  local apps=(
    "qbittorrent:80"
    "autobrr:80"
    "thelounge:9000"
    "prowlarr:80"
    "sonarr:80"
    "radarr:80"
    "qui:80"
  )

  for app_port in "${apps[@]}"; do
    local app=${app_port%:*}
    local port=${app_port#*:}
    checks_total=$((checks_total + 1))

    if curl -s -I "http://${app}.${NAMESPACE}.svc.cluster.local:${port}/ping" &>/dev/null || \
       curl -s -I "http://${app}.${NAMESPACE}.svc.cluster.local:${port}/api/healthz/readiness" &>/dev/null || \
       curl -s -I "http://${app}.${NAMESPACE}.svc.cluster.local:${port}/" &>/dev/null; then
      log_info "✓ $app is reachable"
      checks_passed=$((checks_passed + 1))
    else
      log_warn "✗ $app is not reachable (may still be initializing)"
    fi
  done

  log_info "Connectivity check: $checks_passed/$checks_total passed"
}

# Main execution
main() {
  check_prerequisites
  echo ""

  if ! wait_for_pod "qbittorrent" 300; then
    log_error "qBittorrent failed to start"
    exit 1
  fi
  echo ""

  init_qbittorrent
  echo ""

  init_autobrr
  echo ""

  init_thelounge
  echo ""

  init_prowlarr
  echo ""

  init_sonarr_radarr
  echo ""

  verify_ecosystem
  echo ""

  log_info "=================================="
  log_info "Torrent ecosystem initialization complete!"
  log_info ""
  log_info "📍 Next Steps:"
  log_info "1. Fix tracker credentials in Azure KV:"
  log_info "   - autobrr: BLUTOPIA_passkey, FEARNOPEER_authkey, UPLOADCX_infohash"
  log_info "   - thelounge: IRC passwords for each tracker"
  log_info ""
  log_info "2. Web UI Access (internal only):"
  log_info "   - qBittorrent:  https://qbittorrent.homeops.ca"
  log_info "   - autobrr:      https://autobrr.homeops.ca"
  log_info "   - thelounge:    https://thelounge.homeops.ca"
  log_info "   - prowlarr:     https://prowlarr.homeops.ca"
  log_info "   - sonarr:       https://sonarr.homeops.ca"
  log_info "   - radarr:       https://radarr.homeops.ca"
  log_info "   - qui:          https://qui.homeops.ca"
  log_info ""
  log_info "3. Read optimization guide: docs/TORRENT-OPTIMIZATION.md"
  log_info "=================================="
}

main "$@"
