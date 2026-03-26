# Troubleshooting Guide

## Postgres Issues

### Pod not starting
```bash
oc describe pod -l app=postgres -n mlops-workshop
oc logs -l app=postgres -n mlops-workshop
```

Common causes:
- Image pull error: Check if `postgres:15` is accessible. On restricted clusters, mirror the image first.
- PVC not bound: `oc get pvc -n mlops-workshop` — ensure a default StorageClass exists.

### Cannot connect from Jupyter
```bash
# Test from Jupyter pod
oc exec -it $(oc get pods -l app=jupyter -n mlops-workshop -o name) -n mlops-workshop -- \
  python -c "from sqlalchemy import create_engine; e = create_engine('postgresql://feast:feast@postgres:5432/feast'); print(e.connect())"
```

Common causes:
- Service not created: `oc get svc postgres -n mlops-workshop`
- DNS not resolved: Use full FQDN `postgres.mlops-workshop.svc.cluster.local`

---

## Feast Issues

### `feast apply` fails
```bash
# Check feature_store.yaml is correct
cat /mnt/feast_repo/feature_store.yaml

# Check Postgres connectivity
python -c "import psycopg2; conn = psycopg2.connect('host=postgres dbname=feast user=feast password=feast'); print('OK')"
```

Common causes:
- Wrong working directory: Must `cd /mnt/feast_repo` before running `feast apply`
- Postgres not reachable: Check service exists and pod is running

### `feast materialize` fails
- Ensure data exists in Postgres with valid timestamps
- Check date range covers your data: `SELECT MIN(event_timestamp), MAX(event_timestamp) FROM fraud_transactions;`

### Feast server not starting
```bash
# Check logs
cat /mnt/feast_server.log

# Check if port is already in use
ss -tlnp | grep 6566
```

---

## Jupyter Issues

### `mkdir: cannot create directory '/mnt/...': Permission denied`

The Jupyter pod's PVC mount at `/mnt` is owned by `root:root`. The container needs to run as root to create directories there.

**Cause:** The `anyuid` SCC is not granted to the `jupyter` ServiceAccount, or the pod spec is missing `securityContext.fsGroup: 0`.

`fsGroup: 0` tells Kubernetes to set group ownership of the PVC to GID 0 and make it group-writable. The UBI9 image (UID 1001) is a member of group 0, so it can write without running as root.

**Fix:**
```bash
# Grant anyuid SCC to the jupyter SA in your namespace
oc adm policy add-scc-to-user anyuid -z jupyter -n <your-namespace>

# Delete the crashing pod so the Deployment creates a new one
oc delete pod -l app=jupyter -n <your-namespace>
```

If you don't have permission to grant SCCs, ask your instructor to run the command above.

The `participant-setup.yaml` must include `securityContext.fsGroup: 0` in the pod spec. If you're using an older version of the YAML, re-pull the repo.

### Pod stuck in CrashLoopBackOff
```bash
oc logs -l app=jupyter -n <your-namespace> --previous
```

Common causes:
- pip install failing: Network policy may block PyPI. Pre-build image or add network policy.
- Permission issues: See the `mkdir Permission denied` section above.

### Cannot access Jupyter
```bash
# Check route
oc get route jupyter-route -n mlops-workshop

# Port-forward fallback
oc port-forward svc/jupyter-service 8888:8888 -n mlops-workshop
```

Token: `workshop`

---

## PVC Issues

### PVC stuck in Pending
```bash
oc describe pvc workshop-pvc -n mlops-workshop
```

Common causes:
- No default StorageClass: `oc get sc` — set one as default or specify in PVC yaml
- Insufficient storage quota

### Files not visible after copy
```bash
# Verify files are on the PVC
oc exec -it $(oc get pods -l app=jupyter -n mlops-workshop -o name) -n mlops-workshop -- ls -la /mnt/
```

---

## KServe Issues

### Installation fails
```bash
# Check cert-manager first
oc get pods -n cert-manager

# Check KServe controller
oc get pods -n kserve
oc logs -l control-plane=kserve-controller-manager -n kserve
```

Common causes:
- cert-manager not ready: Wait longer or check cert-manager logs
- CRD conflicts: If KServe CRDs already exist from another install

### InferenceService not ready
```bash
oc describe inferenceservice fraud-detector -n mlops-workshop
```

Common causes:
- Model not found at PVC path: Ensure `/mnt/models/model.joblib` exists
- PVC not accessible: Check PVC is bound and accessible
- Serving runtime not found: `oc get clusterservingruntimes`

### Inference request fails
```bash
# Check the predictor pod
oc get pods -n mlops-workshop | grep fraud-detector
oc logs <predictor-pod-name> -n mlops-workshop

# Test with curl
curl -v http://fraud-detector.mlops-workshop.svc.cluster.local/v1/models/fraud-detector:predict \
  -H "Content-Type: application/json" \
  -d '{"instances": [[75.74, 0.53, 1.18, 1.0, 0.0, 0.0, 1.0]]}'
```

---

## General Debugging

### Check all resources
```bash
oc get all -n mlops-workshop
```

### Check events
```bash
oc get events -n mlops-workshop --sort-by='.lastTimestamp'
```

### Check resource quotas
```bash
oc describe quota -n mlops-workshop
oc describe limitrange -n mlops-workshop
```

### Nuclear option: restart everything
```bash
oc delete pod --all -n mlops-workshop
# Pods will be recreated by their Deployments
```
