#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NS="${1:-}"
TIMEOUT=300
POLL_INTERVAL=5

trap 'echo ""; echo "⚠ Setup interrupted. Re-run this script to resume — it is safe to re-run."; exit 130' INT TERM

usage() {
  echo "Usage: $0 <namespace>"
  echo ""
  echo "Example: $0 workshop-alice"
  exit 1
}

log()  { echo "▸ $*"; }
ok()   { echo "✓ $*"; }
fail() { echo "✗ $*" >&2; exit 1; }
warn() { echo "⚠ $*" >&2; }

# --- Validation ---

[[ -z "$NS" ]] && usage

if ! command -v oc &>/dev/null; then
  fail "oc CLI not found. Install it and log in first."
fi

if ! oc whoami &>/dev/null; then
  fail "Not logged in to OpenShift. Run 'oc login' first."
fi

CURRENT_USER=$(oc whoami)
log "Logged in as: $CURRENT_USER"
log "Target namespace: $NS"
echo ""

# --- Apply participant-setup.yaml ---

SETUP_YAML="$SCRIPT_DIR/k8s/participant-setup.yaml"
if [[ ! -f "$SETUP_YAML" ]]; then
  fail "Cannot find $SETUP_YAML — run this script from the repo root."
fi

log "Applying participant-setup.yaml (namespace, PVC, Jupyter, services, routes)..."
sed "s/REPLACE_NS/${NS}/g" "$SETUP_YAML" | oc apply -f -
ok "Kubernetes resources applied"
echo ""

# --- RBAC ---

log "Granting RBAC (anyuid SCC + cluster-admin for jupyter SA)..."

if oc adm policy add-scc-to-user anyuid -z jupyter -n "$NS" 2>/dev/null; then
  ok "anyuid SCC granted to jupyter SA"
else
  warn "Could not grant anyuid SCC — ask your instructor to run:"
  warn "  oc adm policy add-scc-to-user anyuid -z jupyter -n $NS"
fi

if oc adm policy add-scc-to-user anyuid -z default -n "$NS" 2>/dev/null; then
  ok "anyuid SCC granted to default SA"
else
  warn "Could not grant anyuid SCC for default SA — ask your instructor to run:"
  warn "  oc adm policy add-scc-to-user anyuid -z default -n $NS"
fi

if oc adm policy add-cluster-role-to-user cluster-admin -z jupyter -n "$NS" 2>/dev/null; then
  ok "cluster-admin granted to jupyter SA"
else
  warn "Could not grant cluster-admin — ask your instructor to run:"
  warn "  oc adm policy add-cluster-role-to-user cluster-admin -z jupyter -n $NS"
fi
echo ""

# --- Wait for Jupyter pod ---

log "Waiting for Jupyter pod to be ready (timeout: ${TIMEOUT}s)..."

elapsed=0
while (( elapsed < TIMEOUT )); do
  phase=$(oc get pods -n "$NS" -l app=jupyter -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "")
  ready=$(oc get pods -n "$NS" -l app=jupyter -o jsonpath='{.items[0].status.containerStatuses[0].ready}' 2>/dev/null || echo "")

  if [[ "$phase" == "Running" && "$ready" == "true" ]]; then
    ok "Jupyter pod is running and ready"
    break
  fi

  if [[ -n "$phase" ]]; then
    printf "\r  pod status: %-20s (%ds)" "$phase" "$elapsed"
  else
    printf "\r  waiting for pod to appear... (%ds)" "$elapsed"
  fi

  sleep "$POLL_INTERVAL"
  (( elapsed += POLL_INTERVAL ))
done

echo ""

if (( elapsed >= TIMEOUT )); then
  warn "Jupyter pod did not become ready within ${TIMEOUT}s."
  warn "Check status: oc get pods -n $NS -l app=jupyter"
  warn "View logs:    oc logs -n $NS -l app=jupyter"
  warn ""
  warn "The first boot installs Python packages (~2-3 min). You can continue"
  warn "waiting manually. Re-run this script to resume — it is safe to re-run."
  exit 1
fi

# --- Clone repo inside the pod ---

REPO_URL="https://github.com/aniketpalu/kubeflow-feast-workshop"
JUPYTER_POD=$(oc get pods -n "$NS" -l app=jupyter -o jsonpath='{.items[0].metadata.name}')

log "Cloning workshop repo into Jupyter pod..."
oc exec -n "$NS" "$JUPYTER_POD" -- bash -c "
  if [ -d /mnt/workshop/.git ]; then
    cd /mnt/workshop && git pull --ff-only 2>/dev/null || true
  else
    rm -rf /mnt/workshop
    git clone ${REPO_URL} /mnt/workshop
  fi
"
ok "Repo cloned to /mnt/workshop"

log "Copying workshop files into place..."
oc exec -n "$NS" "$JUPYTER_POD" -- bash -c "
  cp /mnt/workshop/feast_repo/* /mnt/feast_repo/
  cp /mnt/workshop/notebooks/* /mnt/notebooks/
"
ok "Files copied (feast_repo + notebooks)"
echo ""

# --- Print URLs ---

JUPYTER_URL=$(oc get route jupyter-route -n "$NS" -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
FEAST_UI_URL=$(oc get route feast-ui-route -n "$NS" -o jsonpath='{.spec.host}' 2>/dev/null || echo "")

echo "============================================"
echo "  Workshop Setup Complete"
echo "============================================"
echo ""
echo "  Namespace:  $NS"

if [[ -n "$JUPYTER_URL" ]]; then
  echo "  Jupyter:    https://${JUPYTER_URL}  (token: workshop)"
fi
if [[ -n "$FEAST_UI_URL" ]]; then
  echo "  Feast UI:   https://${FEAST_UI_URL}  (available after feast ui is started)"
fi

echo ""
echo "  Next steps:"
echo "    1. Open Jupyter in your browser (use the URL above)"
echo "    2. Open /mnt/notebooks/workshop.ipynb and follow the guide"
echo ""
echo "  Troubleshooting: see TROUBLESHOOTING.md in the repo"
echo "============================================"
