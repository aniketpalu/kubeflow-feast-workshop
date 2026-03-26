# Cluster Setup (Instructor / Admin)

Everything needed to recreate the shared workshop infrastructure on an OpenShift cluster.

## Prerequisites

- OpenShift cluster with `oc` CLI logged in (cluster-admin)
- Kubeflow installed (Training Operator with `torch-distributed` ClusterTrainingRuntime)
- MinIO deployed (typically via Kubeflow, at `minio-service.kubeflow.svc:9000`)
- Docker CLI on your local machine (for mirroring images from Docker Hub)
- A Quay.io account (or other registry) for image mirroring

## What This Sets Up

| Component | Purpose |
|-----------|---------|
| Postgres | 600K fraud transaction rows (shared offline store) |
| Feast Tester | Streamlit app for participants to validate Feast connectivity |
| Inference Tester | Streamlit app for participants to test KServe predictions |
| KServe | Model serving controller + sklearn runtime |
| RBAC | anyuid SCC, cluster-admin for jupyter SA |
| Image mirrors | All Docker Hub images mirrored to quay.io |

## Quick Setup

See [INFRA_SETUP_GUIDE.md](INFRA_SETUP_GUIDE.md) for detailed step-by-step instructions.

### Summary

```bash
# 1. Create namespace + Postgres + load data
oc apply -f k8s/namespace.yaml
oc apply -f k8s/postgres.yaml
oc apply -f k8s/load-data-job.yaml
oc wait --for=condition=complete job/load-fraud-data -n mlops-workshop --timeout=600s

# 2. Install KServe (mirrors images to quay.io)
chmod +x k8s/kserve-install.sh
./k8s/kserve-install.sh

# 3. Configure KServe for RawDeployment + MinIO
oc patch configmap inferenceservice-config -n kserve --type merge \
  -p '{"data":{"deploy":"{\"defaultDeploymentMode\": \"RawDeployment\"}"}}'

# 4. Deploy Streamlit apps
oc apply -f k8s/feast-tester.yaml
oc apply -f k8s/inference-tester.yaml

# 5. Grant RBAC for participants
oc adm policy add-scc-to-user anyuid -z default -n mlops-workshop

# 6. Mirror Docker Hub images (from your local machine)
# See INFRA_SETUP_GUIDE.md for full mirroring steps
```

## File Inventory

### k8s/
| File | Purpose |
|------|---------|
| `namespace.yaml` | mlops-workshop namespace |
| `postgres.yaml` | Secret + ConfigMap (init SQL) + Deployment + Service |
| `pvc.yaml` | Instructor's workshop PVC (5Gi) |
| `load-data-job.yaml` | Job: downloads CSV, loads 600K rows into Postgres |
| `jupyter.yaml` | Instructor's Jupyter pod (for testing) |
| `jupyter-service.yaml` | Jupyter service |
| `jupyter-route.yaml` | Jupyter route |
| `feast-service.yaml` | Feast online service (:6566) |
| `feast-registry-service.yaml` | Feast registry service (:6567) |
| `feast-offline-service.yaml` | Feast offline service (:8815) |
| `feast-config-cm.yaml` | Server-side Feast config ConfigMap |
| `feast-tester.yaml` | Feast Tester Streamlit (ConfigMap + Deployment + Service + Route) |
| `inference-tester.yaml` | Inference Tester Streamlit (ConfigMap + Deployment + Service + Route) |
| `minio-secret.yaml` | MinIO S3 credentials + ServiceAccount for KServe |
| `kserve-install.sh` | KServe installation script with quay.io image patches |
| `remote-feast-test-job.yaml` | Validation job for remote Feast access |
| `inference-input-schema.md` | Feature schema reference |

### streamlit_app/
| File | Purpose |
|------|---------|
| `app.py` | Feast Tester source (dark theme, 3 tests) |
| `inference_app.py` | Inference Tester source (dark theme, presets) |
| `requirements.txt` | Python dependencies |

### training/
| File | Purpose |
|------|---------|
| `train.py` | sklearn training script (generates initial model.joblib) |

## Docker Hub Image Mirroring

This cluster may hit Docker Hub rate limits. Mirror these images to your registry:

```bash
for img in \
  "kserve/kserve-controller:v0.14.1" \
  "kserve/kserve-localmodel-controller:v0.14.1" \
  "kserve/sklearnserver:v0.14.1" \
  "kserve/storage-initializer:v0.14.1"; do
  docker pull --platform linux/amd64 docker.io/$img
  docker tag docker.io/$img quay.io/YOUR-REGISTRY/$img
  docker push quay.io/YOUR-REGISTRY/$img
done
```

Then patch KServe to use your registry. See `kserve-install.sh` for the patch commands.

## Cluster Patches Required

| Resource | Patch |
|----------|-------|
| `inferenceservice-config` (kserve ns) | `defaultDeploymentMode: RawDeployment` + storage-initializer image |
| `ClusterServingRuntime/kserve-sklearnserver` | image → your mirror |
| `ClusterStorageContainer/default` | image → your mirror |
| `ClusterTrainingRuntime/torch-distributed` | image → `ubi9/python-311` (for OpenShift compatibility) |
| `anyuid` SCC | grant to default SA in participant namespaces |
| `cluster-admin` | grant to jupyter SA for TrainerV2 RBAC |
