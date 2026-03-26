"""
TrainerV2 training job that:
1. Fetches features directly from Feast (remote offline store)
2. Trains a PyTorch fraud detection model
3. Uploads the model to MinIO

Zero PVC dependencies. Only needs network access to Feast + MinIO.

The participant's namespace is read from the WORKSHOP_NS env var
(set automatically by participant-setup.yaml).
"""
import os

WORKSHOP_NS = os.environ.get("WORKSHOP_NS", "mlops-workshop")


def train_fraud_from_feast(
    num_epochs=5,
    batch_size=256,
    lr=1e-3,
    hidden_dim=64,
    feast_registry_url=None,
    feast_offline_host=None,
    feast_offline_port=8815,
    feast_start_date="2025-01-01",
    feast_end_date="2025-03-31",
    feast_features=None,
    label_column="fraud",
    val_split=0.2,
    output_dir="/tmp/model_output",
    minio_endpoint="http://minio-service.kubeflow.svc.cluster.local:9000",
    minio_access_key="minio",
    minio_secret_key="minio123",
    minio_bucket="models",
    minio_model_prefix=None,
    workshop_ns=None,
):
    import json
    import os
    import random

    if isinstance(num_epochs, dict):
        cfg = num_epochs
        num_epochs = cfg.get("num_epochs", 5)
        batch_size = cfg.get("batch_size", 256)
        lr = cfg.get("lr", 1e-3)
        hidden_dim = cfg.get("hidden_dim", 64)
        feast_registry_url = cfg.get("feast_registry_url", feast_registry_url)
        feast_offline_host = cfg.get("feast_offline_host", feast_offline_host)
        feast_offline_port = cfg.get("feast_offline_port", feast_offline_port)
        feast_start_date = cfg.get("feast_start_date", feast_start_date)
        feast_end_date = cfg.get("feast_end_date", feast_end_date)
        feast_features = cfg.get("feast_features", feast_features)
        label_column = cfg.get("label_column", label_column)
        val_split = cfg.get("val_split", val_split)
        output_dir = cfg.get("output_dir", output_dir)
        minio_endpoint = cfg.get("minio_endpoint", minio_endpoint)
        minio_access_key = cfg.get("minio_access_key", minio_access_key)
        minio_secret_key = cfg.get("minio_secret_key", minio_secret_key)
        minio_bucket = cfg.get("minio_bucket", minio_bucket)
        minio_model_prefix = cfg.get("minio_model_prefix", minio_model_prefix)
        workshop_ns = cfg.get("workshop_ns", workshop_ns)

    ns = workshop_ns or os.environ.get("WORKSHOP_NS", "mlops-workshop")

    if feast_registry_url is None:
        feast_registry_url = f"feast-registry-service.{ns}.svc.cluster.local:6567"
    if feast_offline_host is None:
        feast_offline_host = f"feast-offline-service.{ns}.svc.cluster.local"
    if minio_model_prefix is None:
        minio_model_prefix = f"fraud-detector-{ns}"

    import numpy as np
    import pandas as pd
    import torch
    import torch.distributed as dist
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import train_test_split
    from torch import nn
    from torch.utils.data import DataLoader, Dataset, DistributedSampler

    random.seed(42)
    np.random.seed(42)
    torch.manual_seed(42)

    world_size = int(os.getenv("WORLD_SIZE", "1"))
    rank = int(os.getenv("RANK", "0"))
    local_rank = int(os.getenv("LOCAL_RANK", "0"))

    distributed = world_size > 1
    if distributed:
        backend = "nccl" if torch.cuda.is_available() else "gloo"
        dist.init_process_group(backend=backend)

    if rank == 0:
        print(f"Namespace: {ns}")
        print(f"Registry:  {feast_registry_url}")
        print(f"Offline:   {feast_offline_host}:{feast_offline_port}")
        print(f"MinIO:     {minio_endpoint} -> s3://{minio_bucket}/{minio_model_prefix}/")
        print("Fetching features from Feast remote offline store...")

    from datetime import datetime
    from feast import FeatureStore, RepoConfig

    if feast_features is None:
        feast_features = [
            "fraud_features:distance_from_home",
            "fraud_features:distance_from_last_transaction",
            "fraud_features:ratio_to_median_purchase_price",
            "fraud_features:repeat_retailer",
            "fraud_features:used_chip",
            "fraud_features:used_pin_number",
            "fraud_features:online_order",
            "fraud_features:fraud",
        ]

    config = RepoConfig(
        project="fraud_detection",
        provider="local",
        registry={"registry_type": "remote", "path": feast_registry_url},
        offline_store={"type": "remote", "host": feast_offline_host, "port": int(feast_offline_port)},
        online_store={"type": "sqlite", "path": "/tmp/feast_online.db"},
        entity_key_serialization_version=3,
    )
    store = FeatureStore(config=config)

    start_dt = datetime.strptime(feast_start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(feast_end_date, "%Y-%m-%d")

    retrieval = store.get_historical_features(
        entity_df=None,
        features=feast_features,
        start_date=start_dt,
        end_date=end_dt,
    )
    df = retrieval.to_df()

    all_cols = [f.split(":")[-1] for f in feast_features]
    feature_cols = [c for c in all_cols if c != label_column]

    if rank == 0:
        print(f"Fetched {len(df)} rows from Feast ({feast_start_date} to {feast_end_date})")
        print(f"Features: {feature_cols}")
        print(f"Label: {label_column}")

    df = df.dropna(subset=feature_cols + [label_column])
    train_df, val_df = train_test_split(df, test_size=val_split, random_state=42, stratify=df[label_column])

    if rank == 0:
        print(f"Train: {len(train_df)}, Val: {len(val_df)}")

    class TabularDataset(Dataset):
        def __init__(self, frame, fcols, lcol):
            self.x = torch.tensor(frame[fcols].values, dtype=torch.float32)
            self.y = torch.tensor(frame[lcol].values, dtype=torch.float32).unsqueeze(1)
        def __len__(self): return len(self.x)
        def __getitem__(self, i): return self.x[i], self.y[i]

    class FraudMLP(nn.Module):
        def __init__(self, d, h):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(d, h), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(h, h // 2), nn.ReLU(),
                nn.Linear(h // 2, 1),
            )
        def forward(self, x): return self.net(x)

    device = torch.device(f"cuda:{local_rank}") if torch.cuda.is_available() else torch.device("cpu")
    if torch.cuda.is_available():
        torch.cuda.set_device(device)

    model = FraudMLP(len(feature_cols), hidden_dim).to(device)
    if distributed:
        model = nn.parallel.DistributedDataParallel(model, device_ids=[local_rank] if torch.cuda.is_available() else None)

    train_ds = TabularDataset(train_df, feature_cols, label_column)
    val_ds = TabularDataset(val_df, feature_cols, label_column)
    train_sampler = DistributedSampler(train_ds) if distributed else None
    train_loader = DataLoader(train_ds, batch_size=batch_size, sampler=train_sampler, shuffle=(train_sampler is None))
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    for epoch in range(num_epochs):
        model.train()
        if train_sampler:
            train_sampler.set_epoch(epoch)
        rl = 0.0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            optimizer.step()
            rl += loss.item()

        model.eval()
        tg, sc = [], []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb = xb.to(device)
                sc.extend(torch.sigmoid(model(xb)).cpu().numpy().reshape(-1).tolist())
                tg.extend(yb.numpy().reshape(-1).tolist())

        auc = roc_auc_score(tg, sc) if len(set(int(v) for v in tg)) >= 2 else float("nan")
        if rank == 0:
            print(f"Epoch {epoch+1}/{num_epochs} | loss={rl/max(len(train_loader),1):.4f} | val_auc={auc:.4f}")

    if rank == 0:
        os.makedirs(output_dir, exist_ok=True)
        m = model.module if hasattr(model, "module") else model
        mp = os.path.join(output_dir, "fraud_mlp_state_dict.pt")
        xp = os.path.join(output_dir, "metrics.json")

        torch.save({"model_state_dict": m.state_dict(), "feature_columns": feature_cols, "label_column": label_column, "hidden_dim": hidden_dim}, mp)
        with open(xp, "w") as f:
            json.dump({"val_auc": float(auc), "epochs": num_epochs, "train_rows": len(train_df), "val_rows": len(val_df), "feast_start": feast_start_date, "feast_end": feast_end_date, "namespace": ns}, f, indent=2)
        print(f"Model saved: {mp} ({os.path.getsize(mp)} bytes)")

        import boto3
        from botocore.client import Config as BC
        s3 = boto3.client("s3", endpoint_url=minio_endpoint, aws_access_key_id=minio_access_key, aws_secret_access_key=minio_secret_key, config=BC(signature_version="s3v4"), region_name="us-east-1")
        try:
            s3.create_bucket(Bucket=minio_bucket)
        except Exception:
            pass
        s3.upload_file(mp, minio_bucket, f"{minio_model_prefix}/fraud_mlp_state_dict.pt")
        s3.upload_file(xp, minio_bucket, f"{minio_model_prefix}/metrics.json")
        print(f"Uploaded to MinIO: s3://{minio_bucket}/{minio_model_prefix}/")

    if distributed:
        dist.barrier()
        dist.destroy_process_group()


if __name__ == "__main__":
    from kubeflow.trainer import CustomTrainer, TrainerClient

    ns = os.environ.get("WORKSHOP_NS", "mlops-workshop")
    client = TrainerClient()

    job_name = client.train(
        trainer=CustomTrainer(
            func=train_fraud_from_feast,
            func_args={
                "num_epochs": 5,
                "batch_size": 256,
                "lr": 1e-3,
                "hidden_dim": 64,
                "feast_start_date": "2025-01-01",
                "feast_end_date": "2025-03-31",
                "label_column": "fraud",
                "val_split": 0.2,
                "output_dir": "/tmp/model_output",
                "minio_endpoint": "http://minio-service.kubeflow.svc.cluster.local:9000",
                "minio_access_key": "minio",
                "minio_secret_key": "minio123",
                "minio_bucket": "models",
                "workshop_ns": ns,
            },
            num_nodes=1,
            resources_per_node={
                "cpu": "2",
                "memory": "4Gi",
            },
            packages_to_install=[
                "torch",
                "pandas",
                "scikit-learn",
                "pyarrow",
                "boto3",
                "feast[postgres,grpc]",
                "psycopg2-binary",
                "grpcio",
            ],
        ),
        runtime="torch-distributed",
    )

    print(f"Submitted TrainJob: {job_name}")
    print("Waiting for job to start...")

    client.wait_for_job_status(name=job_name, status={"Running"}, timeout=600)
    print(f"{job_name} is running. Streaming logs:")
    for line in client.get_job_logs(job_name, follow=True):
        print(line, end="")

    client.wait_for_job_status(name=job_name, timeout=60)
    print("TrainJob completed.")
