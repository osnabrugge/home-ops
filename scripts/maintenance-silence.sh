#!/usr/bin/env bash
set -euo pipefail

# Maintenance-window silencing for planned disruptive work (node reboots, Ceph/OSD
# migrations, Talos upgrades) so transient infra alerts don't page all day.
#
# Usage:
#   scripts/maintenance-silence.sh start [HOURS]   # default 2h, auto-expires
#   scripts/maintenance-silence.sh stop            # expire active maintenance silences
#   scripts/maintenance-silence.sh status          # list active maintenance silences
#
# Posts an auto-expiring silence to Alertmanager (it expires on its own even if you
# forget to stop it). Only infra/storage/node alerts are matched — app alerts still page.

AM="http://alertmanager-operated.observability.svc:9093"
# Infra alerts that fire as noise during planned maintenance. App alerts are NOT matched.
ALERT_REGEX="(Ceph.*|.*OSD.*|.*Mon.*|etcd.*|Node.*|Kube.*Node.*|KubeletDown|TargetDown|PrometheusMissingRuleEvaluations|Watchdog)"
CREATED_BY="just-maintenance"

run_curl() { # pipe stdin (if any) into a transient curl pod
  kubectl -n observability run "ms$RANDOM" --rm -i --restart=Never \
    --image=curlimages/curl:8.10.1 --command -- "$@"
}

action="${1:-status}"
hours="${2:-2}"

case "$action" in
  start)
    starts="$(date -u +%Y-%m-%dT%H:%M:%S.000Z)"
    ends="$(date -u -d "+${hours} hours" +%Y-%m-%dT%H:%M:%S.000Z)"
    payload="$(cat <<JSON
{"matchers":[{"name":"alertname","value":"${ALERT_REGEX}","isRegex":true,"isEqual":true}],
"startsAt":"${starts}","endsAt":"${ends}","createdBy":"${CREATED_BY}",
"comment":"Planned maintenance window (${hours}h) — infra alerts muted, auto-expires ${ends}"}
JSON
)"
    echo "Creating ${hours}h maintenance silence (expires ${ends})..."
    echo "$payload" | run_curl sh -c "curl -s -XPOST --data-binary @- -H 'Content-Type: application/json' ${AM}/api/v2/silences"
    echo
    echo "Done. App alerts still page; infra alerts muted until ${ends}."
    ;;
  stop)
    echo "Expiring active maintenance silences..."
    run_curl sh -c "curl -s ${AM}/api/v2/silences" > /tmp/ms_list.json 2>/dev/null || true
    ids="$(python3 -c "
import json
raw=open('/tmp/ms_list.json').read().lstrip()
d=json.JSONDecoder().raw_decode(raw)[0]
for s in d:
    if s.get('status',{}).get('state')=='active' and s.get('createdBy')=='${CREATED_BY}':
        print(s['id'])
" 2>/dev/null || true)"
    if [ -z "$ids" ]; then echo "No active maintenance silences."; exit 0; fi
    for id in $ids; do
      echo "  expiring $id"
      run_curl sh -c "curl -s -XDELETE ${AM}/api/v2/silence/${id}" >/dev/null || true
    done
    echo "Done."
    ;;
  status)
    run_curl sh -c "curl -s ${AM}/api/v2/silences" > /tmp/ms_list.json 2>/dev/null || true
    python3 -c "
import json
raw=open('/tmp/ms_list.json').read().lstrip()
d=json.JSONDecoder().raw_decode(raw)[0]
act=[s for s in d if s.get('status',{}).get('state')=='active' and s.get('createdBy')=='${CREATED_BY}']
print(f'Active maintenance silences: {len(act)}')
for s in act:
    print('  id=%s expires=%s' % (s['id'], s.get('endsAt')))
"
    ;;
  *)
    echo "Usage: $0 {start [HOURS]|stop|status}" >&2; exit 1;;
esac
