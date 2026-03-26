import pandas as pd
import joblib
import os
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

FEATURE_COLS = [
    "distance_from_home",
    "distance_from_last_transaction",
    "ratio_to_median_purchase_price",
    "repeat_retailer",
    "used_chip",
    "used_pin_number",
    "online_order",
]
LABEL_COL = "fraud"

print("Loading dataset...")
url = "https://raw.githubusercontent.com/aniketpalu/fraud-detection/feast_data_support/data/train.csv"
df = pd.read_csv(url, nrows=10000)
print(f"Loaded {len(df)} rows")

X = df[FEATURE_COLS]
y = df[LABEL_COL]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
print(f"Train: {len(X_train)}, Test: {len(X_test)}")

print("Training RandomForestClassifier...")
model = RandomForestClassifier(n_estimators=50, max_depth=10, random_state=42, n_jobs=-1)
model.fit(X_train, y_train)

y_pred = model.predict(X_test)
accuracy = accuracy_score(y_test, y_pred)
print(f"\nAccuracy: {accuracy:.4f}")
print(f"\nClassification Report:\n{classification_report(y_test, y_pred)}")

output_dir = os.environ.get("MODEL_DIR", "/tmp/models")
os.makedirs(output_dir, exist_ok=True)
model_path = os.path.join(output_dir, "model.joblib")
joblib.dump(model, model_path)
print(f"\nModel saved to: {model_path}")

print("\nQuick inference test:")
sample = X_test.iloc[:3]
predictions = model.predict(sample)
print(f"Input shape: {sample.shape}")
print(f"Predictions: {predictions}")
