# MLOps Workshop: Kubeflow + Feast + KServe on OpenShift

A hands-on workshop demonstrating a sovereign ML pipeline for fraud detection using open-source tools on OpenShift.

## What Participants Learn

1. **Feast** for feature engineering (offline store, feature views, remote serving)
2. **Kubeflow TrainerV2** for distributed model training (K8s-native TrainJobs)
3. **KServe** for model serving (MinIO-backed InferenceService)
4. **MinIO** as S3-compatible model storage (no PVC lock-in)

## Repository Structure

```
├── WORKSHOP_GUIDE.md               # Step-by-step attendee instructions
├── ATTENDEE_FLOW.md                # Visual flow reference + timing guide
├── TROUBLESHOOTING.md              # Common issues and fixes
├── feast_repo/
│   ├── feature_store.yaml          # Feast config (file registry, shared Postgres)
│   └── features.py                 # Entity + FeatureView (fraud detection)
├── k8s/
│   ├── participant-setup.yaml      # Single YAML: NS + Jupyter + Services + Routes
│   ├── feast-remote-config-cm.yaml # ConfigMap for training pods
│   ├── kserve-inferenceservice.yaml# InferenceService template
│   └── inference-request.json      # Sample curl payload
├── notebooks/
│   ├── workshop.ipynb              # Main workshop notebook
│   └── run_training_feast_minio.py # TrainerV2 training script
└── cluster-setup/                  # Instructor-only: infrastructure setup
    ├── README.md                   # Setup instructions
    ├── INFRA_SETUP_GUIDE.md        # Detailed step-by-step
    ├── k8s/                        # All infrastructure YAMLs
    ├── streamlit_app/              # Feast Tester + Inference Tester source
    └── training/                   # Initial model training script
```

## For Participants

### Quick Start

```bash
# 1. Set your namespace
export MY_NS=workshop-yourname

# 2. Deploy your environment
git clone https://github.com/aniketpalu/kubeflow-feast-workshop.git
cd kubeflow-feast-workshop
sed "s/REPLACE_NS/${MY_NS}/g" k8s/participant-setup.yaml | oc apply -f -

# 3. Wait for pod, get Jupyter URL
oc get pods -n ${MY_NS} -w
echo "https://$(oc get route jupyter-route -n ${MY_NS} -o jsonpath='{.spec.host}')"

# 4. Open Jupyter (token: workshop), follow WORKSHOP_GUIDE.md
```

See [WORKSHOP_GUIDE.md](WORKSHOP_GUIDE.md) for the full walkthrough.

## For Instructors

See [cluster-setup/README.md](cluster-setup/README.md) for infrastructure setup.

### What You Need to Deploy Before the Workshop

- Postgres (with fraud data loaded)
- KServe (controller + runtimes, patched for OpenShift)
- Kubeflow Trainer (torch-distributed runtime)
- Feast Tester + Inference Tester Streamlit apps
- RBAC grants for participant namespaces

### Shared Resources

| Resource | Namespace | Purpose |
|----------|-----------|---------|
| Postgres | mlops-workshop | 600K fraud transactions (read-only) |
| MinIO | kubeflow | Model storage (S3-compatible) |
| KServe controller | kserve | Model serving |
| Feast Tester | mlops-workshop | Streamlit validation app |
| Inference Tester | mlops-workshop | Streamlit prediction app |

## Architecture

```
Participant Namespace
  Jupyter Pod
    ├── feast serve          :6566  (online features)
    ├── feast serve_registry :6567  (feature discovery)
    ├── feast serve_offline  :8815  (historical features)
    └── feast ui             :8889  (feature browser)
           │
     TrainerV2 Pod (no PVC needed)
       Feast SDK → registry + offline store
       Train → Upload to MinIO
           │
     KServe Predictor
       Reads model from MinIO
       POST /predict → fraud/legitimate

Shared Infrastructure
  Postgres   → training data
  MinIO      → model storage
  Streamlit  → testing UIs
```

## License

Apache-2.0
