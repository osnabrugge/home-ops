set default-list
set default-script
set quiet
set script-interpreter := ['bash', '-euo', 'pipefail']
set shell := ['bash', '-euo', 'pipefail', '-c']

scripts_dir := justfile_dir() + '/scripts'

[doc('Apply local Flux Kustomization')]
apply-ks ns ks:
    just kube render-local-ks "{{ ns }}" "{{ ks }}" | kubectl apply --server-side --force-conflicts --field-manager=kustomize-controller -f -

[doc('Browse a PVC')]
browse-pvc ns claim:
    kubectl run -n {{ ns }} browse-pvc-{{ claim }} -it --rm --restart=Never \
        --image=mirror.gcr.io/alpine:latest \
        --overrides='{"spec":{"containers":[{"name":"browse-pvc-{{ claim }}","image":"mirror.gcr.io/alpine:latest","stdin":true,"tty":true,"command":["/bin/sh"],"workingDir":"/mnt","volumeMounts":[{"mountPath":"/mnt","name":"data"}]}],"volumes":[{"name":"data","persistentVolumeClaim":{"claimName":"{{ claim }}"}}]}}'

[doc('Debug a node')]
debug-node node:
    trap 'kubectl delete pod -n default -l app.kubernetes.io/managed-by=kubectl-debug --field-selector spec.nodeName={{ node }} --ignore-not-found --wait=false' EXIT
    kubectl debug node/{{ node }} -n default -it --image=mirror.gcr.io/alpine:latest --profile=sysadmin

[doc('Delete local Flux Kustomization')]
delete-ks ns ks:
    just kube render-local-ks "{{ ns }}" "{{ ks }}" | kubectl delete -f -

[doc('Prune pods in Failed, Pending, or Succeeded state')]
prune-pods:
    for phase in Failed Pending Succeeded; do
        kubectl delete pods -A --field-selector status.phase="$phase" --ignore-not-found=true
    done

[doc('Find RBD volumes ext4 flipped to emergency_ro and restart the owning pods (pass fix=1 to remediate)')]
[script]
rbd-ro fix='0':
    # /proc/mounts still reports "rw" for these; the only tell is the emergency_ro option.
    export TALOSCONFIG="{{ justfile_dir() }}/talosconfig"
    if [[ "{{ fix }}" == "1" ]] && ! kubectl -n rook-ceph exec "$(kubectl -n rook-ceph get pod -l app=rook-ceph-tools -o name | head -1)" -- ceph health 2>/dev/null | grep -q HEALTH_OK; then
        echo "REFUSING to remediate: ceph is not HEALTH_OK. Re-run without fix=1 to just list."; exit 1
    fi
    found=0
    for n in 51 52 53 54 55 56; do
        for pv in $(talosctl -n "192.168.42.$n" read /proc/mounts 2>/dev/null | grep -E '^/dev/rbd.*emergency_ro' | grep -oE 'pvc-[0-9a-f-]+' | sort -u); do
            found=1
            ref=$(kubectl get pv "$pv" -o jsonpath='{.spec.claimRef.namespace}/{.spec.claimRef.name}' 2>/dev/null)
            ns=${ref%%/*}; pvc=${ref##*/}
            pod=$(kubectl get pods -n "$ns" -o json 2>/dev/null | jq -r --arg p "$pvc" '.items[] | select(.spec.volumes[]?.persistentVolumeClaim?.claimName==$p) | .metadata.name' | head -1)
            echo "k8s0$((n-50))  $ref  pod=${pod:-<none>}"
            # A container restart does NOT release the CSI global mount — the pod must be deleted.
            if [[ "{{ fix }}" == "1" && -n "$pod" ]]; then
                kubectl delete pod -n "$ns" "$pod" --wait=false
            fi
        done
    done
    [[ "$found" == "0" ]] && echo "No emergency_ro volumes found." || true

[doc('Quick cluster health sweep focused on workloads and recent warnings')]
[script]
health-sweep:
    echo "Checking for pods not in Running or Completed state..."
    {{ scripts_dir }}/health-sweep.sh

[doc('Mute infra alerts for a planned maintenance window (auto-expires)')]
[script]
maintenance-start hours='2':
    {{ scripts_dir }}/maintenance-silence.sh start {{ hours }}

[doc('Expire active maintenance-window silences')]
[script]
maintenance-stop:
    {{ scripts_dir }}/maintenance-silence.sh stop

[doc('Show active maintenance-window silences')]
[script]
maintenance-status:
    {{ scripts_dir }}/maintenance-silence.sh status

[arg('resource', pattern='hr|ks|gitrepo|ocirepo|es')]
[doc('Sync a resource')]
sync resource:
    kubectl get {{ resource }} --no-headers -A | while read -r ns name _; do
        kubectl -n "$ns" annotate --field-manager flux-client-side-apply --overwrite {{ resource }} "$name" \
            "force-sync=$(date +%s)" \
            "reconcile.fluxcd.io/requestedAt=$(date +%s)" \
            "reconcile.fluxcd.io/forceAt=$(date +%s)"
    done

[doc('View a secret')]
view-secret ns secret:
    kubectl view-secret -n {{ ns }} {{ secret }}

[doc('Copy the Flux sops-age key into a namespace so its Kustomizations can decrypt')]
seed-sops-key ns:
    kubectl get secret sops-age -n flux-system -o json \
        | jq 'del(.metadata.namespace, .metadata.uid, .metadata.resourceVersion, .metadata.creationTimestamp, .metadata.managedFields, .metadata.ownerReferences)' \
        | kubectl apply --server-side --field-manager=just-seed-sops-key -n {{ ns }} -f -

[doc('Copy kopiur-repository-secret into a namespace (kopiur mover Jobs load it via envFrom, which is namespace-local)')]
seed-kopiur-secret ns:
    kubectl get secret kopiur-repository-secret -n kopiur-system -o json \
        | jq 'del(.metadata.namespace, .metadata.uid, .metadata.resourceVersion, .metadata.creationTimestamp, .metadata.managedFields, .metadata.ownerReferences, .metadata.labels, .metadata.annotations)' \
        | kubectl apply --server-side --field-manager=just-seed-kopiur -n {{ ns }} -f -

[private]
render-local-ks ns ks:
    flate build ks --namespace "{{ ns }}" --output yaml "{{ ks }}"
