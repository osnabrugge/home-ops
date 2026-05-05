set lazy
set positional-arguments
set quiet
set shell := ['bash', '-euo', 'pipefail', '-c']

bootstrap_dir := justfile_dir() + '/bootstrap'
kubernetes_dir := justfile_dir() + '/kubernetes'
controller := `talosctl config info -o yaml 2>/dev/null | yq -e '.endpoints[0] // ""' 2>/dev/null || true`
nodes := `talosctl config info -o yaml 2>/dev/null | yq -e '.nodes // [] | join(" ")' 2>/dev/null || true`
bootstrap_marker := justfile_dir() + '/.private/bootstrap.done'

[private]
default: talos kube (kubeconfig "node") wait namespaces resources crds apps kubeconfig

[doc('Install Talos')]
talos:
    just log info "Running stage..." "stage" "$0"
    for n in {{ nodes }}; do \
        if ! op=$(just talos apply-node "$n" --insecure 2>&1); then \
            if [[ "$op" == *"certificate required"* ]]; then \
                just log info "Talos already configured, skipping apply of config" "stage" "$0" "node" "$n"; \
                continue; \
            fi; \
            just log fatal "Failed to apply Talos configuration" "stage" "$0" "node" "$n" "output" "$op"; \
        fi; \
    done

[doc('Install Kubernetes')]
kube:
    just log info "Running stage..." "stage" "$0"
    if [[ -f "{{ bootstrap_marker }}" ]]; then \
        just log info "Bootstrap marker exists, skipping bootstrap" "stage" "$0" "marker" "{{ bootstrap_marker }}"; \
        exit 0; \
    fi
    retries=0; \
    max_retries=24; \
    while true; do \
        op=""; \
        if op=$(talosctl -n "{{ controller }}" --endpoints "{{ controller }}" bootstrap --insecure 2>&1); then \
            just log info "Bootstrap command accepted" "stage" "$0"; \
            break; \
        fi; \
        if [[ "$op" == *"AlreadyExists"* ]]; then \
            just log info "Cluster already bootstrapped" "stage" "$0"; \
            break; \
        fi; \
        retries=$((retries + 1)); \
        if [[ "$retries" -ge "$max_retries" ]]; then \
            just log fatal "Kubernetes bootstrap failed after retries" "stage" "$0" "output" "$op"; \
        fi; \
        just log info "Kubernetes bootstrap not ready, retrying in 5 seconds..." "stage" "$0" "attempt" "$retries/$max_retries"; \
        sleep 5; \
    done
    mkdir -p "$(dirname "{{ bootstrap_marker }}")"
    date -Iseconds > "{{ bootstrap_marker }}"
    just log info "Bootstrap marker written" "stage" "$0" "marker" "{{ bootstrap_marker }}"

[doc('Fetch kubeconfig')]
kubeconfig lb="cilium":
    just log info "Running stage..." "stage" "$0"
    if ! talosctl kubeconfig -n "{{ controller }}" --endpoints "{{ controller }}" --insecure -f --force-context-name main {{ justfile_dir() }}; then \
        just log fatal "Failed to fetch kubeconfig" "stage" "$0"; \
    fi
    if [[ "{{ lb }}" != "cilium" ]]; then \
        if ! kubectl config set-cluster main --server "https://{{ controller }}:6443"; then \
            just log fatal "Failed to set kubectl cluster server address" "stage" "$0"; \
        fi; \
    fi

[doc('Wait for nodes to be not-ready')]
wait:
    just log info "Running stage..." "stage" "$0"
    if ! kubectl wait nodes --for=condition=Ready=True --all --timeout=10s &>/dev/null; then \
        until kubectl wait nodes --for=condition=Ready=False --all --timeout=10s &>/dev/null; do \
            just log info "Nodes not available, waiting for nodes to be available. Retrying in 5 seconds..." "stage" "$0"; \
            sleep 5; \
        done \
    fi

[doc('Apply Kubernetes namespaces')]
namespaces:
    just log info "Running stage..." "stage" "$0"
    find "{{ kubernetes_dir }}/apps" -mindepth 1 -maxdepth 1 -type d | while IFS= read -r dir; do \
        if ! kustomize build "$dir" | yq ea -e 'select(.kind == "Namespace")' | kubectl apply --server-side --field-manager bootstrap --force-conflicts -f -; then \
            just log fatal "Failed to apply namespace" "stage" "$0" "namespace" "$(basename "$dir")"; \
        fi; \
    done

[doc('Apply Kubernetes resources')]
resources:
    just log info "Running stage..." "stage" "$0"
    rendered=$(just template "{{ bootstrap_dir }}/resources.yaml.j2")
    # Post-render guardrails
    if printf '%s' "$rendered" | grep -qF 'azkv://'; then \
        just log fatal "Rendered resources contain unresolved azkv:// placeholders" "stage" "$0"; \
    fi
    for field in clientId clientSecret tenantId; do \
        val=$(printf '%s' "$rendered" | yq ea "select(.metadata.name == \"azurekv-secret\") | .stringData.$field" 2>/dev/null | head -1); \
        if [[ -z "$val" || "$val" == "null" ]]; then \
            just log fatal "azurekv-secret.$field is empty/null after rendering" "stage" "$0"; \
        fi; \
    done
    if ! printf '%s' "$rendered" | kubectl apply --server-side --field-manager bootstrap --force-conflicts -f -; then \
        just log fatal "Failed to apply resources" "stage" "$0"; \
    fi;

[doc('Apply Helmfile CRDs')]
crds:
    just log info "Running stage..." "stage" "$0"

    if ! helmfile -f "{{ bootstrap_dir }}/helmfile.d/00-crds.yaml" template -q | yq ea -e 'select(.kind == "CustomResourceDefinition")' | kubectl apply --server-side --field-manager bootstrap --force-conflicts -f -; then \
        just log fatal "Failed to apply crds" "stage" "$0"; \
    fi;

[doc('Apply Helmfile Apps')]
apps:
    just log info "Running stage..." "stage" "$0"
    if ! helmfile -f "{{ bootstrap_dir }}/helmfile.d/01-apps.yaml" sync --hide-notes; then \
        just log fatal "Failed to sync helmfile" "stage" "$0"; \
    fi
