# Workshop Guide: Sovereignty & Open Source ML

A hands-on workshop where you build a fraud detection ML pipeline using Feast, Kubeflow TrainerV2, and KServe on OpenShift.

---

## What's Already Set Up For You

The instructor has pre-deployed shared infrastructure:

- **Postgres** -- 600,000 fraud detection transactions (shared, read-only for you)
- **MinIO** -- S3-compatible storage for trained models
- **KServe** -- Model serving controller with sklearn runtime
- **Kubeflow Trainer** -- `torch-distributed` ClusterTrainingRuntime
- **Feast Tester App** -- Streamlit UI to validate your Feast servers
- **Inference Tester App** -- Streamlit UI to test model predictions

You will get the URLs for the Streamlit apps from the instructor.

---

## Step 0: Choose Your Namespace (1 min)

Pick a unique namespace name (e.g., `workshop-alice`, `workshop-bob`). This will be YOUR workspace for the entire session.

```bash
export MY_NS=workshop-yourname
```

---

## Step 1: Deploy Your Environment (3 min)

Apply the participant setup YAML with your namespace:

```bash
sed "s/REPLACE_NS/${MY_NS}/g" k8s/participant-setup.yaml | oc apply -f -
```

This creates in your namespace:
- A Jupyter pod with all dependencies
- A PVC for your files
- Services for Feast (online, registry, offline) and Jupyter
- An OpenShift Route for browser access
- MinIO credentials for KServe

Wait for the pod to be ready (~60-90 seconds for pip install):

```bash
oc get pods -n ${MY_NS} -w
```

---

## Step 2: Open Jupyter and Clone the Repo (3 min)

Get your Jupyter URL:

```bash
echo "https://$(oc get route jupyter-route -n ${MY_NS} -o jsonpath='{.spec.host}')"
```

Open it in your browser. Token: `workshop`

Open a terminal in Jupyter and clone the workshop materials:

```bash
cd /mnt
git clone <REPO_URL_FROM_INSTRUCTOR> workshop
cp workshop/feast_repo/* /mnt/feast_repo/
cp workshop/notebooks/* /mnt/notebooks/
```

---

## Step 3: Set Up Feast (5 min)

Open `/mnt/notebooks/workshop.ipynb` in Jupyter and run through the Feast sections:

### 3a. Verify Data

Run Section 1. You'll see the 600,000 rows in the shared Postgres -- table schema, fraud rate, feature statistics. All queries run in Postgres (nothing loaded into memory).

### 3b. Apply Feature Definitions

Run Section 2: `feast apply`. This registers your Entity and FeatureView in a local file registry on your PVC.

### 3c. Materialize Features

Run Section 3: `feast materialize`. Copies feature values to the local online store for fast lookups.

### 3d. Fetch Historical Features

Run Section 4. This builds an entity DataFrame from a date range and fetches features via Feast's point-in-time join. You'll see 200 rows with all 7 features populated.

---

## Step 4: Start Feast Servers (3 min)

Run Section 5 in the notebook. This starts three servers inside your pod:

| Server | Port | Protocol | Purpose |
|--------|------|----------|---------|
| Online | 6566 | REST | Real-time feature lookup |
| Registry | 6567 | gRPC | Feature discovery for remote pods |
| Offline | 8815 | Arrow Flight | Historical features for training |

Run Section 6 to verify all three are healthy.

### Feast UI

You also get a Feast UI for visually browsing your features, entities, and data sources:

```bash
echo "https://$(oc get route feast-ui-route -n ${MY_NS} -o jsonpath='{.spec.host}')"
```

Open it in your browser — no login needed. Start `feast ui` from the notebook (Section 5 starts it automatically).

---

## Step 5: Test With Feast Tester App (3 min)

Open the **Feast Tester** URL from the instructor.

Change the service URLs to point to YOUR namespace:

- Registry: `feast-registry-service.YOUR-NS.svc.cluster.local:6567`
- Offline Host: `feast-offline-service.YOUR-NS.svc.cluster.local`
- Online: `http://feast-service.YOUR-NS.svc.cluster.local:6566`

Click **Run Feast Tests**. All 3 should pass:
1. Registry connection -- finds `fraud_features`
2. Historical feature fetch -- returns rows with real values
3. Online feature fetch -- returns JSON response

---

## Step 6: Run Training via TrainerV2 (10 min)

The training job runs in a **separate Kubernetes pod** (not your Jupyter pod). It:
1. Connects to YOUR Feast servers to fetch training data
2. Trains a PyTorch fraud detection model
3. Uploads the model to MinIO

From a Jupyter terminal:

```bash
cd /mnt/notebooks
python run_training_feast_minio.py
```

Or from the notebook, run Section 7 (TrainerV2 submission).

Watch for:
- `Submitted TrainJob: <name>`
- `Fetched N rows from Feast`
- `Epoch 1/5 | loss=... | val_auc=...`
- `Uploaded to MinIO: s3://models/fraud-detector-YOUR-NS/`

The training pod needs NO PVC -- it fetches data from Feast and uploads the model to MinIO, all over the network.

---

## Step 7: Deploy KServe InferenceService (3 min)

First, apply the remote Feast config (for future training jobs):

```bash
sed "s/REPLACE_NS/${MY_NS}/g" k8s/feast-remote-config-cm.yaml | oc apply -f -
```

Then deploy the InferenceService:

```bash
sed "s/REPLACE_NS/${MY_NS}/g" k8s/kserve-inferenceservice.yaml | oc apply -f -
```

Wait for it to be ready:

```bash
oc get inferenceservice -n ${MY_NS} -w
```

Once `READY=True`, the model is serving.

---

## Step 8: Test Inference (3 min)

Open the **Inference Tester** URL from the instructor.

Set the KServe URL to:
```
http://fraud-detector-predictor.YOUR-NS.svc.cluster.local/v1/models/fraud-detector:predict
```

Try the presets:
- **Likely Safe** -- low distance, chip+PIN, in-person -- prediction: `0.0`
- **Likely Fraud** -- far from home, high amount, no chip, online -- prediction: `1.0`
- **Edge Case** -- see what the model decides

Or test from the command line:

```bash
curl -s -X POST http://fraud-detector-predictor.${MY_NS}.svc.cluster.local/v1/models/fraud-detector:predict \
  -H "Content-Type: application/json" \
  -d '{"instances": [[113.6, 0.53, 5.34, 1.0, 0.0, 0.0, 1.0]]}'
```

---

## Architecture Summary

```
Your Namespace
  Jupyter Pod (/mnt PVC)
    feast serve          :6566  REST
    feast serve_registry :6567  gRPC
    feast serve_offline  :8815  Arrow Flight
    feast ui             :8889  Web UI (Route)
           |
     TrainerV2 Pod (no PVC)
       Feast SDK -> registry :6567 + offline :8815
       Train PyTorch model
       Upload to MinIO s3://models/fraud-detector-YOUR-NS/
           |
     KServe Predictor Pod
       Reads model from MinIO
       POST /predict -> {fraud: 0 or 1}

Shared Infrastructure (mlops-workshop)
  Postgres :5432    -- 600K fraud transactions
  MinIO :9000       -- model storage
  Feast Tester      -- Streamlit validation app
  Inference Tester  -- Streamlit prediction app
```

---

## Key Takeaways

1. **Feast separates feature engineering from training** -- define features once, use everywhere
2. **Remote access pattern** -- training pods connect to Feast servers via k8s Services, no database credentials needed
3. **MinIO replaces PVC for models** -- no volume mount conflicts, any pod can read/write
4. **TrainerV2 creates real K8s Jobs** -- distributed training with proper resource isolation
5. **Everything is sovereign and open-source** -- runs entirely on your OpenShift cluster
