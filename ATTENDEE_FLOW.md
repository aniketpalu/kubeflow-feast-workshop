# Attendee Flow Reference

Visual reference for the workshop participant journey.

## Prerequisites (set up by instructor)

Participants need:
- `oc` CLI configured and logged in to the OpenShift cluster
- The `for_attendees/` folder (via git clone or shared URL)
- Feast Tester URL and Inference Tester URL (provided by instructor)

Instructor has already deployed:
- Postgres with 600K fraud transactions (mlops-workshop namespace)
- MinIO for model storage (kubeflow namespace)
- KServe controller + serving runtimes
- Kubeflow Trainer with torch-distributed runtime
- Feast Tester and Inference Tester Streamlit apps

## Flow Diagram

```
STEP 0 ─── Choose namespace
            export MY_NS=workshop-yourname

STEP 1 ─── Deploy environment
            sed 's/REPLACE_NS/$MY_NS/g' k8s/participant-setup.yaml | oc apply -f -
            ↓
            Creates: Namespace, PVC, Jupyter pod, 5 Services, 2 Routes, MinIO SA
            Wait: oc get pods -n $MY_NS -w (ready in ~90s)

STEP 2 ─── Open Jupyter + clone repo
            Open: https://$(oc get route jupyter-route -n $MY_NS -o jsonpath='{.spec.host}')
            Token: workshop
            Terminal: git clone <REPO> /mnt/workshop
                      cp /mnt/workshop/feast_repo/* /mnt/feast_repo/
                      cp /mnt/workshop/notebooks/* /mnt/notebooks/

STEP 3 ─── Feast setup (in notebook)
            ├── Section 1: Verify data in shared Postgres (600K rows)
            ├── Section 2: feast apply (register features in local file registry)
            ├── Section 3: feast materialize (offline → online store)
            └── Section 4: Fetch historical features (200 rows, date range)

STEP 4 ─── Start Feast servers (in notebook)
            Section 5 starts 4 servers:
            ├── feast serve          :6566  REST     (online features)
            ├── feast serve_registry :6567  gRPC     (feature discovery)
            ├── feast serve_offline  :8815  Flight   (historical features)
            └── feast ui             :8889  HTTP     (feature browser)

            Section 6: Health check (all 4 ports)
            Feast UI: https://$(oc get route feast-ui-route -n $MY_NS -o jsonpath='{.spec.host}')

STEP 5 ─── Test Feast remotely
            Open shared Feast Tester Streamlit app (URL from instructor)
            Enter YOUR service URLs:
              Registry: feast-registry-service.$MY_NS.svc.cluster.local:6567
              Offline:  feast-offline-service.$MY_NS.svc.cluster.local
              Online:   http://feast-service.$MY_NS.svc.cluster.local:6566
            Click "Run Feast Tests" → all 3 should pass

STEP 6 ─── Train model via TrainerV2
            Terminal: cd /mnt/notebooks && python run_training_feast_minio.py

            What happens:
            ├── Kubeflow TrainerV2 creates a K8s TrainJob pod (4Gi, 2 CPU)
            ├── Pod installs torch, feast, boto3, etc.
            ├── Fetches ~146K rows from YOUR Feast servers (no PVC needed)
            ├── Trains FraudMLP (5 epochs, ~0.99 AUC)
            └── Uploads model to MinIO: s3://models/fraud-detector-$MY_NS/

STEP 7 ─── Deploy KServe InferenceService
            Terminal:
              sed "s/REPLACE_NS/$MY_NS/g" /mnt/workshop/k8s/kserve-inferenceservice.yaml | oc apply -f -
              oc get inferenceservice -n $MY_NS -w
            Wait for READY=True

STEP 8 ─── Test inference
            Open shared Inference Tester Streamlit app (URL from instructor)
            Set URL: http://fraud-detector-predictor.$MY_NS.svc.cluster.local/v1/models/fraud-detector:predict
            Try presets: Safe → 0.0, Fraud → 1.0
```

## What Each Step Produces

| Step | Artifact |
|------|----------|
| 1 | Namespace with Jupyter pod + services + routes |
| 2 | Workshop files on PVC at /mnt/ |
| 3 | Feast registry (file) + online store (SQLite) on PVC |
| 4 | 4 running Feast servers + Feast UI route |
| 5 | Validated remote Feast connectivity |
| 6 | Trained model in MinIO (s3://models/fraud-detector-NS/) |
| 7 | KServe InferenceService (READY) |
| 8 | Working fraud prediction endpoint |

## What's Shared vs What's Yours

| Resource | Shared (instructor) | Per-participant |
|----------|-------------------|-----------------|
| Postgres (data) | Shared, read-only | — |
| MinIO (models) | Shared bucket | Unique prefix per NS |
| KServe controller | Shared | InferenceService per NS |
| Feast servers | — | Own servers in own pod |
| Feast registry | — | Own file on own PVC |
| Training job | — | Own K8s Job |
| Streamlit apps | Shared UIs | Enter own URLs |

## Timing Guide

| Step | Duration |
|------|----------|
| 0-1: Setup | 3 min |
| 2: Jupyter + clone | 3 min |
| 3: Feast setup | 5 min |
| 4: Start servers | 3 min |
| 5: Test Feast | 3 min |
| 6: Training | 10 min (includes pod startup + pip install) |
| 7: Deploy KServe | 3 min |
| 8: Test inference | 3 min |
| **Total** | **~33 min** (buffer to 45-60 min with Q&A) |
