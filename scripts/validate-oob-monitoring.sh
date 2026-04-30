#!/usr/bin/env bash
set -euo pipefail

# OOB Management Monitoring Validation Script
#
# Usage: scripts/validate-oob-monitoring.sh
#
# This script validates that all OOB management monitoring is working correctly
# after the consolidation changes are applied.
#
# Prerequisites:
#   - kubectl configured with cluster access
#   - curl available
#   - jq available (optional, for pretty output)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass_count=0
fail_count=0
warn_count=0

log_pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((pass_count++))
}

log_fail() {
    echo -e "${RED}✗${NC} $1"
    ((fail_count++))
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((warn_count++))
}

log_info() {
    echo -e "ℹ $1"
}

section() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "$1"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Check prerequisites
check_prereqs() {
    section "Checking Prerequisites"

    if ! command -v kubectl >/dev/null 2>&1; then
        log_fail "kubectl not found"
        exit 1
    fi
    log_pass "kubectl found"

    if ! command -v curl >/dev/null 2>&1; then
        log_fail "curl not found"
        exit 1
    fi
    log_pass "curl found"

    if ! kubectl cluster-info >/dev/null 2>&1; then
        log_fail "kubectl cluster access failed"
        exit 1
    fi
    log_pass "kubectl cluster access OK"
}

# Validate Gatus deployment
check_gatus() {
    section "Gatus Deployment"

    local pod_status
    pod_status=$(kubectl get pods -n observability -l app.kubernetes.io/name=gatus -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "NotFound")

    if [[ "$pod_status" == "Running" ]]; then
        log_pass "Gatus pod is Running"
    else
        log_fail "Gatus pod status: $pod_status"
        return 1
    fi

    # Check if config has OOB endpoints
    local config_check
    config_check=$(kubectl get configmap -n observability gatus-config -o jsonpath='{.data.config\.yaml}' 2>/dev/null | grep -c "group: oob-management" || echo "0")

    if [[ "$config_check" -ge 7 ]]; then
        log_pass "Gatus config contains $config_check OOB management endpoints (expected 7)"
    else
        log_fail "Gatus config contains only $config_check OOB management endpoints (expected 7)"
    fi
}

# Validate SNMP Exporter
check_snmp_exporter() {
    section "SNMP Exporter"

    local pod_status
    pod_status=$(kubectl get pods -n observability -l app.kubernetes.io/name=snmp-exporter -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "NotFound")

    if [[ "$pod_status" == "Running" ]]; then
        log_pass "SNMP Exporter pod is Running"
    else
        log_fail "SNMP Exporter pod status: $pod_status"
        return 1
    fi

    # Check ServiceMonitor targets
    local targets
    targets=$(kubectl get servicemonitor -n observability snmp-exporter -o jsonpath='{.spec.endpoints[0].params}' 2>/dev/null | grep -c "ups01\|ups02\|pdu01\|pdu02" || echo "0")

    if [[ "$targets" -ge 4 ]]; then
        log_pass "SNMP Exporter ServiceMonitor has 4 targets configured"
    else
        log_warn "SNMP Exporter ServiceMonitor target count unclear (found $targets references)"
    fi
}

# Validate Prometheus Rules
check_prometheus_rules() {
    section "Prometheus Alert Rules"

    local rules
    rules=$(kubectl get prometheusrule -n observability snmp-exporter-rules -o yaml 2>/dev/null)

    if [[ -z "$rules" ]]; then
        log_fail "PrometheusRule 'snmp-exporter-rules' not found"
        return 1
    fi
    log_pass "PrometheusRule 'snmp-exporter-rules' exists"

    # Check for expected alerts
    local expected_alerts=("UPSOnBattery" "UPSReplaceBattery" "PDUUnreachable" "UPSUnreachable" "UPSLowBattery" "UPSHighLoad")
    for alert in "${expected_alerts[@]}"; do
        if echo "$rules" | grep -q "alert: $alert"; then
            log_pass "Alert rule '$alert' found"
        else
            log_fail "Alert rule '$alert' NOT found"
        fi
    done
}

# Check Prometheus Targets (if accessible)
check_prometheus_targets() {
    section "Prometheus Targets (Optional)"

    local prom_pod
    prom_pod=$(kubectl get pods -n observability -l app.kubernetes.io/name=prometheus -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -z "$prom_pod" ]]; then
        log_warn "Prometheus pod not found, skipping target checks"
        return 0
    fi

    # Port-forward to Prometheus (ephemeral)
    log_info "Attempting to query Prometheus targets..."

    # Try to access via service if available
    local prom_url="http://prometheus.observability.svc.cluster.local:9090"

    if kubectl run -i --rm --restart=Never curl-test --image=curlimages/curl:latest --timeout=10s -- \
        curl -s "$prom_url/api/v1/targets" >/dev/null 2>&1; then

        local targets_json
        targets_json=$(kubectl run -i --rm --restart=Never curl-test --image=curlimages/curl:latest --timeout=10s -- \
            curl -s "$prom_url/api/v1/targets" 2>/dev/null)

        # Check SNMP exporter targets
        local snmp_targets
        snmp_targets=$(echo "$targets_json" | grep -o "pdu01\|pdu02\|ups01\|ups02" | sort -u | wc -l || echo "0")

        if [[ "$snmp_targets" -eq 4 ]]; then
            log_pass "All 4 SNMP targets found in Prometheus"
        else
            log_warn "Only $snmp_targets SNMP targets found (expected 4)"
        fi
    else
        log_warn "Could not access Prometheus API, skipping detailed target checks"
    fi
}

# Check Gatus Endpoints Health (if accessible)
check_gatus_health() {
    section "Gatus Endpoint Health (Optional)"

    log_info "Attempting to query Gatus API..."

    # Try to access Gatus via service
    local gatus_url="http://gatus.observability.svc.cluster.local:8080"

    if kubectl run -i --rm --restart=Never curl-test --image=curlimages/curl:latest --timeout=10s -- \
        curl -s "$gatus_url/api/v1/endpoints/statuses" >/dev/null 2>&1; then

        local gatus_json
        gatus_json=$(kubectl run -i --rm --restart=Never curl-test --image=curlimages/curl:latest --timeout=10s -- \
            curl -s "$gatus_url/api/v1/endpoints/statuses" 2>/dev/null)

        # Check OOB management endpoints
        local oob_count
        oob_count=$(echo "$gatus_json" | grep -c '"group":"oob-management"' || echo "0")

        if [[ "$oob_count" -eq 7 ]]; then
            log_pass "All 7 OOB management endpoints found in Gatus"
        else
            log_warn "Only $oob_count OOB management endpoints found (expected 7)"
        fi

        # Check if any are unhealthy
        local unhealthy
        unhealthy=$(echo "$gatus_json" | grep '"group":"oob-management"' | grep -c '"success":false' || echo "0")

        if [[ "$unhealthy" -eq 0 ]]; then
            log_pass "All OOB management endpoints are healthy"
        else
            log_warn "$unhealthy OOB management endpoints are unhealthy"
        fi
    else
        log_warn "Could not access Gatus API, skipping health checks"
    fi
}

# Network connectivity tests
check_network_connectivity() {
    section "Network Connectivity (Optional)"

    log_info "Testing connectivity to OOB devices..."

    # These tests run from within the cluster to verify SNMP/network access
    local test_targets=(
        "pdu01.in.homeops.ca:161"
        "pdu02.in.homeops.ca:161"
        "ups01.in.homeops.ca:161"
        "ups02.in.homeops.ca:161"
        "192.168.42.22:22"  # pi02
        "192.168.42.23:22"  # pi03
    )

    for target in "${test_targets[@]}"; do
        if timeout 3 bash -c "echo >/dev/tcp/${target/:/ } 2>/dev/null"; then
            log_pass "Connection to $target succeeded"
        else
            log_warn "Connection to $target failed (may be firewall/VLAN isolation)"
        fi
    done
}

# Summary
print_summary() {
    section "Validation Summary"

    echo ""
    echo "Results:"
    echo "  ✓ Passed: $pass_count"
    echo "  ✗ Failed: $fail_count"
    echo "  ⚠ Warnings: $warn_count"
    echo ""

    if [[ $fail_count -eq 0 ]]; then
        echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${GREEN}All critical checks passed!${NC}"
        echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

        if [[ $warn_count -gt 0 ]]; then
            echo ""
            echo "Some optional checks produced warnings. This is normal if:"
            echo "  - Running from outside the cluster network"
            echo "  - Prometheus/Gatus APIs are not directly accessible"
            echo "  - OOB devices are on isolated VLANs (expected until #3054)"
        fi

        echo ""
        echo "Next steps:"
        echo "  1. Check Gatus status page: https://status.homeops.ca"
        echo "  2. Verify no false-positive alerts: https://alertmanager.homeops.ca"
        echo "  3. Check UPS dashboard: https://grafana.homeops.ca/d/apc-ups"
        echo ""
        return 0
    else
        echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${RED}Validation failed with $fail_count critical errors${NC}"
        echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
        echo "Please review the failed checks above and:"
        echo "  1. Verify Flux has reconciled the changes"
        echo "  2. Check pod logs: kubectl logs -n observability -l app.kubernetes.io/name=gatus"
        echo "  3. Check for reconciliation errors: flux get ks -A"
        echo ""
        return 1
    fi
}

# Main execution
main() {
    echo "OOB Management Monitoring Validation"
    echo "===================================="
    echo ""

    check_prereqs
    check_gatus
    check_snmp_exporter
    check_prometheus_rules
    check_prometheus_targets
    check_gatus_health
    check_network_connectivity
    print_summary
}

main "$@"
