# Infrastructure Setup Guide

How we built the MLOps workshop from scratch on a ROSA (OpenShift on AWS) cluster.

---

## Prerequisites

- OpenShift cluster with `oc` CLI logged in
- Cluster admin access (for KServe CRDs)
- Docker CLI on your local machine (for mirroring images)
- A Quay.io account for image mirroring (Docker Hub is rate-limited on shared clusters)

---

## Phase 1: Namespace + Storage

```bash
oc apply -f k8s/namespace.yaml        # mlops-workshop namespace
oc apply -f k8s/pvc.yaml              # workshop-pvc (5Gi) for Jupyter
oc apply -f k8s/model-pvc.yaml        # model-pvc (1Gi) for KServe
```

---

## Phase 2: Postgres

```bash
oc apply -f k8s/postgres.yaml
```

This creates:
- A **Secret** with credentials (feast/feast/feast)
- A **ConfigMap** with init SQL that creates the `fraud_transactions` table
- A **Deployment** using `quay.io/aniket-redhat/postgres:16-alpine`
- A **Service** on port 5432

Wait for the pod:
```bash
oc get pods -n mlops-workshop -l app=postgres -w
```

Verify the table exists:
```bash
oc exec -n mlops-workshop deploy/postgres -- psql -U feast -d feast -c "\dt"
```

---

## Phase 3: Load Data

```bash
oc apply -f k8s/load-data-job.yaml
oc wait --for=condition=complete job/load-fraud-data -n mlops-workshop --timeout=600s
oc logs job/load-fraud-data -n mlops-workshop --tail=3
```

The Job downloads the CSV from GitHub and loads 600K rows into Postgres (~5 min).

---

## Phase 4: Jupyter Pod + Services

```bash
oc apply -f k8s/jupyter.yaml
oc apply -f k8s/jupyter-service.yaml
oc apply -f k8s/feast-service.yaml
oc apply -f k8s/feast-registry-service.yaml
oc apply -f k8s/feast-offline-service.yaml
oc apply -f k8s/jupyter-route.yaml
```

Wait for Jupyter to be ready (pip install takes ~60s):
```bash
oc get pods -n mlops-workshop -l app=jupyter -w
```

---

## Phase 5: Copy Workshop Files to Pod

```bash
JUPYTER_POD=$(oc get pods -n mlops-workshop -l app=jupyter -o jsonpath='{.items[0].metadata.name}')
oc cp feast_repo/feature_store.yaml ${JUPYTER_POD}:/mnt/feast_repo/feature_store.yaml -n mlops-workshop
oc cp feast_repo/features.py ${JUPYTER_POD}:/mnt/feast_repo/features.py -n mlops-workshop
oc cp notebooks/workshop.ipynb ${JUPYTER_POD}:/mnt/notebooks/workshop.ipynb -n mlops-workshop
```

---

## Phase 6: Feast Apply + Materialize + Start Servers

From inside the Jupyter pod (or via the notebook):

```bash
# Apply feature definitions
oc exec -n mlops-workshop ${JUPYTER_POD} -- bash -c "cd /mnt/feast_repo && feast apply"

# Materialize features
oc exec -n mlops-workshop ${JUPYTER_POD} -- bash -c "cd /mnt/feast_repo && feast materialize 2025-01-01T00:00:00 2025-12-31T23:59:59"

# Start all 3 Feast servers
oc exec -n mlops-workshop ${JUPYTER_POD} -- bash -c 'cd /mnt/feast_repo; feast serve --host 0.0.0.0 --port 6566 > /mnt/feast_online.log 2>&1 &'
oc exec -n mlops-workshop ${JUPYTER_POD} -- bash -c 'cd /mnt/feast_repo; feast serve_registry --port 6567 > /mnt/feast_registry.log 2>&1 &'
oc exec -n mlops-workshop ${JUPYTER_POD} -- bash -c 'cd /mnt/feast_repo; feast serve_offline --host 0.0.0.0 --port 8815 > /mnt/feast_offline.log 2>&1 &'
```

Verify all ports:
```bash
oc exec -n mlops-workshop ${JUPYTER_POD} -- ss -tlnp | grep -E "6566|6567|8815"
```

---

## Phase 7: Validate Remote Feast Access

Deploy the remote test config and job:
```bash
oc apply -f k8s/feast-remote-config-cm.yaml
oc apply -f k8s/remote-feast-test-job.yaml
oc wait --for=condition=complete job/remote-feast-test -n mlops-workshop --timeout=600s
oc logs job/remote-feast-test -n mlops-workshop --tail=15
```

You should see `REMOTE FEAST ACCESS (provider: remote): SUCCESS`.

---

## Phase 8: Install KServe

```bash
chmod +x k8s/kserve-install.sh
./k8s/kserve-install.sh
```

This installs cert-manager, KServe controller, and patches images to use `quay.io/aniket-redhat/` mirrors.

If the sklearn serving runtime still points to Docker Hub:
```bash
oc patch clusterservingruntime kserve-sklearnserver --type='json' \
  -p='[{"op": "replace", "path": "/spec/containers/0/image", "value": "quay.io/aniket-redhat/sklearnserver:v0.14.1"}]'
```

Set RawDeployment mode (no Knative):
```bash
oc patch configmap inferenceservice-config -n kserve --type merge \
  -p '{"data":{"deploy":"{\"defaultDeploymentMode\": \"RawDeployment\"}"}}'
```

---

## Phase 9: Train Model + Deploy to KServe

Train locally:
```bash
cd training
MODEL_DIR=models python train.py
```

Copy model to cluster:
```bash
# Temporary pod to write to model-pvc
oc run model-loader --image=registry.access.redhat.com/ubi9/python-311:latest \
  --restart=Never -n mlops-workshop \
  --overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"model-loader","image":"registry.access.redhat.com/ubi9/python-311:latest","command":["sleep","300"],"securityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]}},"volumeMounts":[{"name":"model-vol","mountPath":"/models"}]}],"volumes":[{"name":"model-vol","persistentVolumeClaim":{"claimName":"model-pvc"}}]}}'

# Wait for pod, copy model, clean up
sleep 15
oc exec -n mlops-workshop model-loader -- mkdir -p /models/fraud-model
oc cp training/models/model.joblib model-loader:/models/fraud-model/model.joblib -n mlops-workshop
oc delete pod model-loader -n mlops-workshop --force
```

Deploy InferenceService:
```bash
oc apply -f k8s/kserve-inferenceservice.yaml
oc get inferenceservice -n mlops-workshop -w   # Wait for READY=True
```

Test inference:
```bash
oc exec -n mlops-workshop ${JUPYTER_POD} -- curl -s -X POST \
  http://fraud-detector-predictor.mlops-workshop.svc.cluster.local/v1/models/fraud-detector:predict \
  -H "Content-Type: application/json" \
  -d '{"instances": [[113.61, 0.53, 1.75, 1.0, 0.0, 0.0, 1.0]]}'
# Expected: {"predictions":[1.0]}
```

---

## Phase 10: Deploy Streamlit Apps

### Feast Tester (validates remote Feast connectivity)
```bash
oc apply -f k8s/feast-tester.yaml
```

### Inference Tester (tests KServe predictions)
```bash
oc apply -f k8s/inference-tester.yaml
```

Get URLs:
```bash
echo "Feast Tester:     https://$(oc get route feast-tester-route -n mlops-workshop -o jsonpath='{.spec.host}')"
echo "Inference Tester: https://$(oc get route inference-tester-route -n mlops-workshop -o jsonpath='{.spec.host}')"
```

Both apps use dark theme and pip-install dependencies at startup (~30-60s first load).

### Feast Tester Usage
1. Open the URL
2. Default service URLs are pre-filled
3. Click "Run Feast Tests"
4. 3 tests run: Registry (gRPC) → Historical Features (Arrow Flight) → Online Features (REST)
5. Each shows PASS/FAIL with full output and error tracebacks

### Inference Tester Usage
1. Open the URL
2. Default KServe URL is pre-filled
3. Use Quick Presets (Safe / Fraud / Edge Case) or adjust features manually
4. Click "Predict"
5. Shows the JSON request, response, and a FRAUD/LEGITIMATE verdict

---

## Phase 11: Verify Everything

```bash
# All pods running
oc get pods -n mlops-workshop

# All services
oc get svc -n mlops-workshop

# All routes
oc get routes -n mlops-workshop

# KServe InferenceService
oc get inferenceservice -n mlops-workshop

# PVCs
oc get pvc -n mlops-workshop
```

Expected: 5 pods running, 8 services, 3 routes, 1 InferenceService (READY=True), 2 PVCs (Bound).

---

## Docker Hub Image Mirroring

This cluster hits Docker Hub rate limits. All images were mirrored to `quay.io/aniket-redhat/`:

```bash
# For each image needed from Docker Hub:
docker pull --platform linux/amd64 <docker-hub-image>
docker tag <docker-hub-image> quay.io/aniket-redhat/<name>:<tag>
docker push quay.io/aniket-redhat/<name>:<tag>
# Make the Quay repo public via quay.io web UI
```

Images mirrored:
- `postgres:16-alpine` → `quay.io/aniket-redhat/postgres:16-alpine`
- `kserve/kserve-controller:v0.14.1` → `quay.io/aniket-redhat/kserve-controller:v0.14.1`
- `kserve/kserve-localmodel-controller:v0.14.1` → `quay.io/aniket-redhat/kserve-localmodel-controller:v0.14.1`
- `kserve/sklearnserver:v0.14.1` → `quay.io/aniket-redhat/sklearnserver:v0.14.1`

**Important:** Always use `--platform linux/amd64` when pulling on Apple Silicon Macs.

---

## Troubleshooting

See `TROUBLESHOOTING.md` for common issues with Postgres, Feast, Jupyter, PVC, and KServe.
