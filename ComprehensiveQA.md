# AutoMLOps — Complete Question & Answer Reference

> Covers every area: system architecture, datasets, models, algorithms, design decisions, and operational details.

---

## TABLE OF CONTENTS

1. [System Overview & Architecture](#1-system-overview--architecture)
2. [Datasets — Iris Classifier](#2-datasets--iris-classifier)
3. [Datasets — Aegis NIDS Synthetic Dataset](#3-datasets--aegis-nids-synthetic-dataset)
4. [Iris Classifier — v1 (scikit-learn)](#4-iris-classifier--v1-scikit-learn)
5. [Iris Classifier — v2 (XGBoost + Optuna)](#5-iris-classifier--v2-xgboost--optuna)
6. [Aegis NIDS — Model Architecture](#6-aegis-nids--model-architecture)
7. [Aegis Bridge Pattern — Zero-Import Integration](#7-aegis-bridge-pattern--zero-import-integration)
8. [Webhook & Pipeline Trigger Flow](#8-webhook--pipeline-trigger-flow)
9. [Quality Gate & Deployment](#9-quality-gate--deployment)
10. [Drift Detection & Auto-Retrain](#10-drift-detection--auto-retrain)
11. [Explainability — SHAP](#11-explainability--shap)
12. [Hyperparameter Tuning — Optuna](#12-hyperparameter-tuning--optuna)
13. [MLflow Experiment Tracking](#13-mlflow-experiment-tracking)
14. [Security & Webhook Verification](#14-security--webhook-verification)
15. [Technology Stack](#15-technology-stack)
16. [Design Decisions & Trade-offs](#16-design-decisions--trade-offs)

---

## 1. System Overview & Architecture

**Q: What is AutoMLOps and what problem does it solve?**

AutoMLOps is a self-hosted ML lifecycle management platform that automates the entire process from code push to model deployment and monitoring. The problem it solves is the "last mile" of machine learning: most teams can train a model but struggle to reliably retrain, evaluate, deploy, and monitor it in production. AutoMLOps closes this loop automatically — a developer pushes code, and the system handles training, quality checking, deployment, drift detection, and retraining without any manual steps.

---

**Q: Describe the complete end-to-end pipeline flow.**

1. **Developer pushes code** to a GitHub repository (e.g., iris-classifier main branch)
2. **GitHub sends a webhook** (`POST /webhook/github`) to the AutoMLOps backend
3. **Webhook handler** verifies the HMAC-SHA256 signature, looks up the repo in the database, creates a `Run` record with status `pending`, and spawns a background thread
4. **Local runner** (`runner/local_runner.py`) reads `mlops.yaml` from the repo, identifies the framework (sklearn or xgboost), and dispatches to the appropriate training module
5. **Training module** loads data, splits it, trains the model, evaluates metrics, and writes `metrics.json`
6. **Quality gate** reads `metrics.json` and compares against thresholds in `mlops.yaml` (e.g., accuracy ≥ 0.92, F1 ≥ 0.90)
7. **If passed**: the model is deployed locally (`deploy/local_deploy.py`), post-training monitoring runs (Evidently baseline + anomaly model training), a version comparison report is generated, and a Discord alert is sent
8. **If failed**: the Run record is updated to `failed`, a critical alert is sent, and no deployment happens
9. **Monitoring**: Evidently AI computes statistical drift between baseline training data and live prediction data. If drift is detected, an auto-retrain is triggered (subject to the circuit breaker: max 3 retrains per 24 hours)

---

**Q: What are the main components of the system and what does each do?**

| Component | Location | Role |
|---|---|---|
| FastAPI Backend | `backend/` | REST API, webhook receiver, repo management, run tracking |
| Database | SQLite via SQLAlchemy | Stores repos, runs, deployments, metrics history |
| Local Runner | `runner/local_runner.py` | Dispatches training by framework, enforces pipeline lock |
| Training Modules | `ml/train_sklearn.py`, `ml/train_xgboost.py` | Framework-specific training logic |
| Aegis Bridge | `ml/aegis_bridge.py` | Loads pre-trained Aegis model without importing Aegis |
| Quality Gate | Inside runner | AND-logic comparison: all metrics must pass |
| Deployment | `deploy/local_deploy.py` | Saves model artifacts, registers deployment record |
| Monitoring | `monitoring/monitor.py` | Evidently drift reports, version comparison, anomaly model |
| Alerts | `monitoring/alerts.py` | Discord webhook notifications for pipeline events |
| Frontend | `frontend/` (React/Vite) | Dashboard UI, repo cards, metrics display, run history |
| MLflow | localhost:5000 | Experiment tracking, hyperparameter logs, run history |

---

**Q: What is the pipeline lock and why does it exist?**

The pipeline lock is a Python `set` called `_running_pipelines` (in `runner/local_runner.py`) that stores the repo IDs of currently running pipelines. Before starting a new training run, the runner checks if the repo ID is already in this set. If it is, it returns `False` (launch skipped) to prevent two concurrent training runs for the same repo.

This is necessary because training can take 20–60 seconds. If a developer pushes two commits in quick succession, GitHub sends two webhooks. Without the lock, both would start training simultaneously, writing to the same `metrics.json` and model file, causing a race condition. The lock ensures runs are serialized per repo.

---

**Q: What database does AutoMLOps use and what tables exist?**

AutoMLOps uses **SQLite** accessed via **SQLAlchemy ORM**. The main tables are:

- **Repo**: stores connected repositories (id, repo_name, github_url, mlops_yaml config, created_at)
- **Run**: stores individual pipeline runs (id, repo_id, commit_sha, status, triggered_by, started_at, completed_at, metrics_json, quality_gate_result)
- **Deployment**: stores deployment records (id, repo_id, run_id, deployed_at, model_path, port, tunnel_url)

SQLite was chosen for self-hosted simplicity — no external database server required. For production scale, this would swap to PostgreSQL.

---

## 2. Datasets — Iris Classifier

**Q: What is the Iris dataset and why was it chosen for the demo?**

The Iris dataset is one of the most famous benchmark datasets in machine learning, created by botanist Edgar Anderson in 1935 and popularized by statistician Ronald Fisher. It contains measurements of 150 iris flowers from three species:

- **Setosa** — clearly separable, very distinct measurements
- **Versicolor** — partially overlaps with Virginica
- **Virginica** — partially overlaps with Versicolor

The four features are: `sepal_length`, `sepal_width`, `petal_length`, `petal_width` (all in centimeters).

**Why chosen for the demo:**
1. Small (150 rows × 4 features) — trains in under 1 second for sklearn, ~12 seconds for XGBoost+Optuna — fast enough for a live demo
2. Well-understood — everyone knows what "iris classification" means, so the audience doesn't need domain explanation
3. Shows clear metric improvement: sklearn RandomForest gets ~0.92 accuracy, XGBoost+Optuna gets ~0.97 — a visible 5-point jump that proves the v2 upgrade is worth it
4. Multi-class (3 classes) — demonstrates that AutoMLOps handles more than binary classification

---

**Q: How was the iris.csv file generated for the repo?**

The file at `data/iris.csv` was generated from scikit-learn's built-in dataset using Python:

```python
from sklearn.datasets import load_iris
import pandas as pd
iris = load_iris(as_frame=True)
df = iris.frame
df.columns = ['sepal_length','sepal_width','petal_length','petal_width','target']
df['species'] = df['target'].map({0:'setosa',1:'versicolor',2:'virginica'})
df = df.drop('target', axis=1)
df.to_csv('data/iris.csv', index=False)
```

This produces 150 rows with columns: `sepal_length`, `sepal_width`, `petal_length`, `petal_width`, `species`. The species column is the string label the training code reads and encodes with `LabelEncoder`.

---

**Q: What is the train/test split for the iris classifier?**

A **20% stratified test split** is used — 120 rows for training, 30 rows for testing. Stratified means each class is proportionally represented in both splits (50 samples per class → 40 train, 10 test per class). This is important for a balanced dataset like Iris to ensure the test set isn't accidentally all one class.

---

## 3. Datasets — Aegis NIDS Synthetic Dataset

**Q: What dataset does Aegis NIDS use and why is it synthetic?**

Aegis uses **synthetic network flow data** that it generates programmatically. Real network intrusion datasets exist (KDD Cup 99, CICIDS-2017/2018), but they have significant problems:
1. **Stale**: traffic patterns from 2017 don't reflect modern attack techniques
2. **Distribution mismatch**: captured on specific hardware/topology, doesn't generalise
3. **Legal/privacy**: real network captures may contain sensitive data
4. **Limited attack diversity**: real captures may not have all 7 threat classes in the proportions needed

The synthetic approach allows precise control over feature distributions per threat class, making the pipeline testable before any real Wireshark/Zeek captures exist. The architecture is designed so that real Parquet files (from Docker lab captures) automatically replace the synthetic data — no code change needed.

---

**Q: How exactly is the Aegis synthetic dataset generated? Walk through the code.**

The function `generate_synthetic_data(n_per_class=500)` in `ml/train.py` works as follows:

1. **Creates a NumPy random generator** with a fixed seed (42) for reproducibility
2. **Defines a `specs` dictionary** with 7 entries — one per threat class — where each entry maps feature names to `(low, high)` uniform distribution bounds
3. **For each class**, generates `n_per_class` rows where each feature is sampled from `np.random.uniform(low, high, n)`, clipped to `[0, ∞)`
4. **Special handling for integer columns**: `orig_bytes`, `resp_bytes`, `orig_pkts`, `resp_pkts`, `unique_dst_ips`, `unique_dst_ports`, `dns_query_count` are cast to int
5. **Port columns**: `src_port` is random in `[1024, 65535]`; `dst_port` is chosen from common ports `[80, 443, 53, 22, 8080, 8443, 21, 25]`
6. **Boolean columns**: `is_tls`, `is_quic`, `quic_0rtt` are set based on class-specific probabilities (e.g., `malware_tls` always has `is_tls=1`, `ddos` always has `is_tls=0`)
7. **Categorical columns**: `ja4_hash_enc` and `cipher_suite_enc` are random integers in small ranges to exercise the encoding path
8. **Applies the `PERIODICITY_CAP`** of 100.0 to prevent outlier values
9. Each row gets `label = class_name` and `scenario = "synthetic_<class_name>"`

The result is a DataFrame of `7 × 500 = 3500` rows with all 36 `FEATURE_COLUMNS` present.

---

**Q: What are the 36 features used in Aegis and what do they represent?**

The features are network flow statistics computed from packet captures by `features/pipeline.py`:

**Flow rate features:**
- `packets_per_sec` — connection speed indicator
- `bytes_per_sec` — bandwidth usage
- `duration` — how long the flow lasted

**Volume features:**
- `orig_bytes`, `resp_bytes` — bytes sent by originator/responder
- `orig_pkts`, `resp_pkts` — packet counts each direction
- `outbound_inbound_ratio` — asymmetry between upload and download

**Topology features:**
- `fan_out` — number of destinations contacted
- `fan_in` — number of sources connecting to a host
- `unique_dst_ips` — distinct destination IPs
- `unique_dst_ports` — distinct destination ports
- `src_ip_entropy` — entropy of source IPs (high = spoofed/distributed)
- `connection_frequency` — connections per time window

**Timing features:**
- `iat_mean`, `iat_std`, `iat_min`, `iat_max` — inter-arrival time statistics (regularity of timing)
- `periodicity_score` — how periodic/regular the timing is (capped at 100)

**DNS features:**
- `dns_query_entropy` — randomness of domain names (high = DGA)
- `domain_length_mean`, `domain_length_max` — length of queried domain names
- `subdomain_count` — number of subdomain labels
- `dns_record_type_a_ratio` — fraction of A record queries
- `dns_record_type_txt_ratio` — fraction of TXT queries (high = DNS tunneling)
- `dns_query_count` — total DNS queries in window

**TLS/Protocol features:**
- `tls_version` — TLS protocol version (old versions are suspicious)
- `is_tls` — whether flow is TLS encrypted (boolean)
- `src_port`, `dst_port` — connection endpoints

**QUIC features:**
- `is_quic` — whether QUIC protocol is used
- `quic_0rtt` — 0-RTT QUIC connection (security implication)
- `quic_pkt_size_mean`, `quic_pkt_size_std` — QUIC packet size statistics

**Encoded categorical:**
- `ja4_hash_enc` — frequency-encoded JA4 TLS fingerprint
- `cipher_suite_enc` — frequency-encoded cipher suite

---

**Q: How do the synthetic distributions encode real-world attack knowledge?**

Each class's feature distributions are grounded in known attack behavior:

**DDoS (SYN flood)**:
- `packets_per_sec`: 500–5000 (extremely high packet rate)
- `orig_bytes`: 40–200 (tiny — just SYN packets, no data)
- `resp_bytes`: 0–5 (nearly zero — handshake never completes)
- `fan_in`: 50–500 (many spoofed source IPs hitting one victim)
- `src_ip_entropy`: 3.5–5.0 (high entropy from IP spoofing)
- `duration`: 0.001–0.05 seconds (very short flows)

**C2 Beaconing**:
- `iat_mean`: 55–65 seconds (approximately 60-second beacon interval)
- `iat_std`: 0.1–2.0 (very low jitter — regular timing)
- `periodicity_score`: 50–100 (very high — almost perfectly periodic)
- `fan_out`: 1–2 (always connects to same C2 server)
- `unique_dst_ips`: exactly 1 (one C2 destination)

**DNS Anomaly (DGA + DNS tunneling)**:
- `dns_query_entropy`: 4.2–5.0 (nearly random-looking domain names)
- `domain_length_mean`: 30–60 characters (long DGA-generated names)
- `subdomain_count`: 4–8 (many levels, used for tunneling data)
- `dns_record_type_txt_ratio`: 0.3–0.8 (high TXT ratio — DNS tunneling signal)
- `dns_query_count`: 30–100 (many queries per window)

**Port Scan**:
- `unique_dst_ports`: 200–1024 (scanning a wide port range)
- `fan_out`: 200–1024 (connecting to many ports)
- `orig_bytes`: 40–60 (just SYN packets)
- `connection_frequency`: 50–200 (rapid sequential connections)

**Exfiltration**:
- `outbound_inbound_ratio`: 50–1000 (heavily asymmetric — sending much more than receiving)
- `orig_bytes`: 100,000–5,000,000 (large upload)
- `bytes_per_sec`: 50,000–500,000 (high sustained bandwidth)
- `duration`: 30–600 seconds (long sustained flows)

---

**Q: What is the label taxonomy for Aegis and how are labels attached to data?**

The 7 classes are defined in `CLASS_NAMES` in `ml/train.py`:
```
["benign", "ddos", "c2_beaconing", "dns_anomaly", "malware_tls", "port_scan", "exfiltration"]
```

Labels are stored as JSON files in `data/labels/`. Each file looks like:
```json
{
  "scenario":    "syn_flood",
  "attack_class": "ddos",
  "src_ip":      "10.10.0.4",
  "dst_ip":      "10.10.0.3",
  "description": "SYN flood attack from 10.10.0.4 to 10.10.0.3",
  "pcap":        "data/raw/syn_flood.pcap"
}
```

When real Parquet files exist in `data/features/`, each file is named after its scenario (e.g., `syn_flood.parquet`). The loader matches the filename stem to the label map to attach the class. Multiple scenarios can share the same class (e.g., `syn_flood_1.parquet` and `syn_flood_2.parquet` both map to `ddos`).

---

**Q: Why is scenario-level splitting used instead of row-level splitting?**

**Row-level splitting** is the naive approach: randomly assign 80% of rows to train and 20% to test. The problem is that a single attack run generates thousands of correlated flows with the same source IP, same timing pattern, and similar feature values. If rows from the same attack run appear in both train and test, the model trivially memorizes the run's signature rather than learning generalizable attack patterns. This produces falsely inflated metrics — the model looks 99% accurate on paper but fails on any new attack instance.

**Scenario-level splitting** assigns entire attack runs (scenarios) to either train, val, or test. The model never sees a specific attack run during training that it will be tested on. This produces honest evaluation: the test metrics reflect performance on attack runs the model has never encountered.

Split ratios: 70% train / 15% val / 15% test, stratified by class.

---

## 4. Iris Classifier — v1 (scikit-learn)

**Q: What model does v1 use and why?**

v1 uses **scikit-learn's RandomForestClassifier** with default hyperparameters. It was chosen as the baseline because:
- Easy to understand and explain
- No hyperparameter tuning required
- Trains in ~0.5 seconds on 120 rows
- Achieves ~0.92 accuracy on Iris out of the box
- Demonstrates that even a simple baseline passes the quality gate

The v1 `train.py` applies `StandardScaler` to normalize the features, which is standard practice for sklearn models but unnecessary for tree-based models (trees are scale-invariant).

---

**Q: What does the v1 model bundle contain?**

The v1 model saves a Python dictionary (bundle) as `model.pkl` via `pickle`:
```python
{
    "model": trained_RandomForestClassifier,
    "scaler": fitted_StandardScaler,
    "label_encoder": fitted_LabelEncoder,
    "features": ["sepal_length", "sepal_width", "petal_length", "petal_width"],
    "framework": "sklearn"
}
```

During inference (`predict.py`), the bundle is loaded, the scaler is applied first, then the model predicts, then the label encoder decodes the integer prediction back to the species string.

---

## 5. Iris Classifier — v2 (XGBoost + Optuna)

**Q: What changed in v2 and why does it perform better?**

v2 replaces RandomForest with **XGBoost** (gradient boosted trees) and adds **Optuna** for automated hyperparameter search. The improvements:

1. **XGBoost vs RandomForest**: XGBoost trains trees sequentially where each tree corrects the errors of the previous one (boosting), whereas RandomForest trains trees independently and averages (bagging). For most tabular datasets, boosting achieves higher accuracy because it focuses on hard-to-classify examples.

2. **Optuna hyperparameter tuning**: Instead of using defaults, Optuna runs 30 trials searching over `n_estimators`, `max_depth`, `learning_rate`, `min_child_weight`. The best combination is selected based on cross-validated F1 score. On Iris, this pushes accuracy from ~0.92 to ~0.97.

3. **No StandardScaler needed**: XGBoost is a tree-based model and therefore scale-invariant. Removing the scaler simplifies the pipeline.

---

**Q: What does the v2 training code do step by step?**

1. Reads `mlops.yaml` to get `dataset_path`, `metrics_threshold`, and `xgboost.n_trials`
2. Loads `data/iris.csv` with pandas
3. Extracts feature columns and target (`species`)
4. Fits a `LabelEncoder` on the species column (setosa→0, versicolor→1, virginica→2)
5. Performs a 20% stratified train/test split
6. Runs Optuna with `n_trials=30`, each trial training XGBoost with different hyperparameters and evaluating F1 macro on a 20% validation split
7. Retrains the final model on the full training set with the best hyperparameters
8. Evaluates on the held-out test set
9. Saves `{model, label_encoder, features, framework:"xgboost"}` bundle as `model.pkl`
10. Writes `metrics.json` with `accuracy`, `f1`, and `model_artifact_path`

---

**Q: Why was `use_label_encoder` removed from XGBoost calls?**

In XGBoost versions prior to 1.6, you could pass `use_label_encoder=False` to suppress a deprecation warning about automatic label encoding. In **XGBoost ≥ 1.6**, this parameter was completely removed — passing it raises a `TypeError: unexpected keyword argument`. The fix is to simply not pass this argument at all, since modern XGBoost handles label encoding correctly without it.

---

**Q: What is the Optuna search space for iris v2?**

```python
n_estimators:     50 – 400    (number of boosting rounds / trees)
max_depth:        3 – 10      (depth of each individual tree)
learning_rate:    0.01 – 0.3  (shrinkage factor, sampled log-uniform)
min_child_weight: 1 – 10      (minimum sum of instance weight in a leaf)
subsample:        0.6 – 1.0   (fraction of rows used per tree)
colsample_bytree: 0.6 – 1.0   (fraction of features used per tree)
```

Optuna's **TPE (Tree-structured Parzen Estimator)** sampler guides the search: it builds a probabilistic model of the relationship between hyperparameters and objective value, and samples more frequently in regions that historically produced good results. This is more efficient than random search or grid search.

---

## 6. Aegis NIDS — Model Architecture

**Q: What is Aegis NIDS and what does it detect?**

**Aegis** is a Network Intrusion Detection System (NIDS) that monitors network flows and classifies them into 7 categories:

| Integer | Class | Description |
|---|---|---|
| 0 | benign | Normal network traffic |
| 1 | c2_beaconing | Command-and-control callbacks (malware phoning home) |
| 2 | ddos | Distributed denial-of-service attacks |
| 3 | dns_anomaly | DGA (domain generation algorithm) or DNS tunneling |
| 4 | exfiltration | Data theft — large outbound transfers |
| 5 | malware_tls | Malware communicating over encrypted TLS sessions |
| 6 | port_scan | Reconnaissance — scanning ports to find open services |

It operates on **network flow features** (not raw packet payloads), making it compatible with encrypted traffic and computationally efficient.

---

**Q: What is the two-stage architecture of Aegis inference?**

Aegis uses two models in sequence:

**Stage 1 — Isolation Forest (anomaly detection)**:
- An unsupervised model trained only on benign traffic
- Computes an anomaly score for each new flow
- Threshold: 0.621 — flows with score above this are flagged as potentially anomalous
- Purpose: fast pre-filter that catches anything "unusual" before the expensive classifier runs
- If a flow scores below the threshold (normal-looking), it's classified as benign immediately

**Stage 2 — XGBoost Classifier (threat classification)**:
- A supervised 7-class classifier
- Only called when Stage 1 flags the flow as anomalous
- Assigns one of the 7 threat classes (or benign if it's a false alarm from Stage 1)
- Uses SHAP TreeExplainer to generate supporting evidence for the classification

This two-stage approach reduces latency (most traffic is benign, so Stage 2 runs infrequently) and improves precision (Stage 1 filters obvious normal traffic before the classifier can misclassify it).

---

**Q: What is Isolation Forest and how does it work?**

Isolation Forest is an **unsupervised anomaly detection algorithm**. The core intuition is: *anomalies are rare and different, so they're easier to isolate*.

The algorithm:
1. Builds multiple random decision trees (isolation trees)
2. At each split, randomly selects a feature and a random split value between that feature's min and max
3. **Anomaly score** = how quickly a data point gets isolated (reaches a leaf node)
4. Anomalies, being rare and distinct, require fewer splits to isolate → shorter path length → higher anomaly score
5. Normal points, being common and similar to many others, require more splits → longer path → lower anomaly score

For Aegis:
- Trained only on benign traffic → it learns the distribution of "normal"
- At inference, new flows are scored against this learned normal distribution
- Flows with path length below the 0.621 threshold = normal; above = investigate

---

**Q: What are the key hyperparameters for the Aegis XGBoost model?**

Tuned by Optuna (20 trials):
- `n_estimators`: 50–400 (number of trees)
- `max_depth`: 3–10 (tree depth)
- `learning_rate`: 0.01–0.3 (log-uniform)
- `min_child_weight`: 1–10 (leaf minimum weight)
- `subsample`: 0.6–1.0
- `colsample_bytree`: 0.6–1.0

XGBoost is chosen over other classifiers for network traffic because:
- Handles mixed numeric/boolean/ordinal features without scaling
- `sample_weight` support for class imbalance (SYN floods generate 1000× more flows than C2 beaconing)
- Native SHAP integration via `TreeExplainer` for evidence generation
- Fast inference — critical for real-time traffic analysis

---

**Q: How does Aegis handle class imbalance?**

Class imbalance is severe: a SYN flood generates thousands of flows per second; a C2 beacon generates one per minute. Without correction, XGBoost would learn "predict ddos for everything" and achieve high accuracy on volume while missing rare but critical attack types.

The solution is **sample weights** computed as:
```
weight_i = total_samples / (n_classes × count_of_class_i)
```

This is the same formula as scikit-learn's `class_weight='balanced'`, applied manually because XGBoost's sklearn API accepts `sample_weight` arrays. The effect: rare classes (c2_beaconing, exfiltration) get upweighted in the loss function, forcing the model to pay attention to them even though they have fewer training rows.

---

**Q: What artifacts does Aegis training produce?**

After `python -m ml.train`, four files are written to `ml/`:

| File | Contents |
|---|---|
| `ml/model.joblib` | Trained XGBoost classifier |
| `ml/label_encoder.joblib` | LabelEncoder mapping int ↔ class name |
| `ml/encoders.joblib` | Frequency encoders for `ja4_hash` and `cipher_suite` |
| `ml/optuna_study.pkl` | Full Optuna study (all 20 trials, params, scores) |

Plus evaluation outputs:
- `ml/classification_report.txt` — per-class precision/recall/F1
- `ml/confusion_matrix.png` — heatmap (rows=actual, cols=predicted)

---

**Q: What is JA4 hashing and why is it a feature?**

**JA4** (and its predecessor JA3) is a TLS client fingerprinting technique. When a client initiates a TLS handshake, it sends a ClientHello message containing: TLS version, cipher suites offered, TLS extensions, and elliptic curves. JA4 hashes these values into a short fingerprint that identifies the TLS client implementation.

Why it matters for NIDS:
- Legitimate browsers (Chrome, Firefox) have well-known JA4 fingerprints
- Malware using custom TLS stacks produces unusual JA4 values not seen in normal traffic
- `malware_tls` traffic often has JA4 fingerprints that don't match any known browser/application

Since JA4 is a high-cardinality categorical variable (thousands of possible values), it's encoded via **frequency encoding**: the top 50 most common values get integer codes 1–50; everything else maps to 0 ("unknown"). This encoder is fit on training data only and persisted in `ml/encoders.joblib` so inference uses the identical mapping.

---

## 7. Aegis Bridge Pattern — Zero-Import Integration

**Q: What is the Aegis Bridge and why was it needed?**

The **Aegis Bridge** (`ml/aegis_bridge.py`) solves the problem of integrating a pre-trained model from a completely separate project (Aegis) into AutoMLOps without:
1. Installing Aegis as a package
2. Copying Aegis source code into AutoMLOps
3. Importing any Aegis modules (which might have conflicting dependencies)

The problem: AutoMLOps needs to run an Aegis pipeline (load model, make predictions, compute metrics) but cannot `import aegis` because Aegis is a separate repository at a different path.

The solution: **the bridge loads Aegis's `.joblib` files by absolute path using only standard Python and `joblib`**. Since `.joblib` files are serialized Python objects (XGBoost and sklearn models), they can be loaded without importing Aegis at all. The bridge then wraps these loaded objects in AutoMLOps's own bundle format, so the rest of the pipeline treats Aegis exactly like any other model.

---

**Q: How does the Aegis Bridge work step by step?**

```python
# ml/aegis_bridge.py
import joblib
import os

AEGIS_ML_DIR = os.getenv("AEGIS_ML_DIR", r"C:\Users\...\Aegis\ml")

def load_aegis_artifacts():
    model = joblib.load(os.path.join(AEGIS_ML_DIR, "model.joblib"))
    label_encoder = joblib.load(os.path.join(AEGIS_ML_DIR, "label_encoder.joblib"))
    encoders = joblib.load(os.path.join(AEGIS_ML_DIR, "encoders.joblib"))
    return model, label_encoder, encoders

def run_aegis_pipeline():
    model, le, encoders = load_aegis_artifacts()
    # Wrap in AutoMLOps bundle format
    bundle = {
        "model": model,
        "label_encoder": le,
        "encoders": encoders,
        "framework": "xgboost",
        "features": FEATURE_COLUMNS,
    }
    # Run on synthetic test data to compute metrics
    # Returns metrics dict compatible with quality gate
    return {"accuracy": 0.96, "f1": 0.95, ...}
```

Key design decision: the `AEGIS_ML_DIR` is an environment variable, so the bridge works on any machine where `AEGIS_ML_DIR` points to the Aegis project's `ml/` directory. No hardcoded paths in the code.

---

**Q: Why is the Aegis pipeline nearly instantaneous (2 seconds) compared to iris (30 seconds)?**

The Aegis pipeline doesn't retrain. When the runner dispatches to the Aegis framework, it:
1. Loads the pre-trained `.joblib` files (fast — just deserializing)
2. Runs a quick evaluation on synthetic test data to compute metrics
3. Returns the metrics

There's no Optuna tuning, no model fitting, no data splitting. The model was trained once during the Aegis project's development and the artifacts were saved. AutoMLOps's role is to register, version, monitor, and serve this pre-trained model — not to retrain it.

---

## 8. Webhook & Pipeline Trigger Flow

**Q: How does the GitHub webhook trigger a pipeline run?**

1. In GitHub repository settings → Webhooks, a webhook is configured with:
   - **Payload URL**: `https://<cloudflare-tunnel-url>/webhook/github`
   - **Content type**: `application/json`
   - **Secret**: `automlops-dev-secret`
   - **Events**: Just the push event

2. When a push happens, GitHub POSTs the event payload to the URL, including:
   - `X-Hub-Signature-256` header: `sha256=<HMAC of payload using the secret>`
   - `X-GitHub-Event` header: `push`
   - JSON body with repository name, commit SHA, ref (branch), etc.

3. AutoMLOps's `/webhook/github` endpoint:
   - Verifies the HMAC signature using `hmac.compare_digest()` (constant-time comparison, immune to timing attacks)
   - Looks up the repository by name in the database
   - Creates a Run record
   - Launches `launch_pipeline_thread(repo_id, commit_sha, run_id)` as a daemon thread
   - Returns `{"status": "queued", "run_id": "...", ...}` immediately

---

**Q: Why is the webhook URL `/webhook/github` and not just `/webhook`?**

The FastAPI router is structured with a prefix:
```python
# backend/main.py
app.include_router(webhook_router, prefix="/webhook")

# backend/routes/webhook.py
@router.post("/github")  # full path: /webhook/github
```

This allows multiple webhook sources to be added later under the same `/webhook` prefix (e.g., `/webhook/gitlab`, `/webhook/bitbucket`) without path conflicts. A common mistake during setup is setting GitHub's Payload URL to `/webhook` and getting a 404 because the actual route is `/webhook/github`.

---

**Q: Why is Cloudflare Tunnel used?**

GitHub's webhook servers are on the public internet. The AutoMLOps backend runs on `localhost:8000` — not accessible from the internet. **Cloudflare Tunnel** creates an encrypted tunnel from `localhost:8000` to a public HTTPS URL (`https://xxxx.trycloudflare.com`) without opening firewall ports, configuring NAT, or owning a domain.

The quick tunnel command:
```
cloudflared.exe tunnel --url http://localhost:8000 --no-autoupdate
```

**Limitation**: quick tunnels are ephemeral — the URL changes every time cloudflared restarts. Before every demo, you must re-run cloudflared and update the GitHub webhook Payload URL. A named tunnel (configured with `ebinthomas.dev` domain) would give a permanent URL, but requires Cloudflare account setup.

---

## 9. Quality Gate & Deployment

**Q: How does the quality gate work?**

The quality gate is **AND logic** — every metric must exceed its threshold. It reads from `metrics.json` (produced by training) and compares against `mlops.yaml`:

```yaml
metrics_threshold:
  accuracy: 0.92
  f1: 0.90
```

```python
# Pseudocode from runner/local_runner.py
metrics = json.load("metrics.json")
for metric, threshold in mlops_config["metrics_threshold"].items():
    if metrics.get(metric, 0) < threshold:
        return "failed"
return "passed"
```

If any single metric is below its threshold, the pipeline fails and no deployment happens. This prevents a model that's good at precision but poor at recall (or vice versa) from getting deployed.

---

**Q: What happens when the quality gate passes?**

1. **`deploy_model()`** is called, which:
   - Copies the model artifact to a versioned location
   - Records a Deployment entry in the database
   - Assigns a port for serving
   - Returns `{port, tunnel_url, deployed_at}`

2. **`on_training_complete()`** is called for post-training monitoring:
   - Runs **version comparison** (current metrics vs. previous run)
   - Generates an **AST diff** (code change summary)
   - Trains an **Isolation Forest anomaly model** on the new training data (async) for future drift detection
   - Stores the Evidently baseline for drift comparison

3. A **Discord alert** is sent: "Quality gate passed! Model deployed on port X."

---

## 10. Drift Detection & Auto-Retrain

**Q: What is data drift and why does it matter?**

**Data drift** occurs when the statistical distribution of production data shifts away from the distribution the model was trained on. For example:
- If petal_length was 1–7 cm in training data but new flowers being classified have petal_length 3–21 cm (a genetic variant), the model will make incorrect predictions because it's extrapolating beyond its training distribution
- In network traffic, drift might mean attackers have changed their techniques (different IAT patterns, new ports), making the model miss new attack variants

If drift is not detected and corrected, model performance degrades silently over time. This is called **model staleness** and is one of the most common causes of ML system failures in production.

---

**Q: How does Evidently AI detect drift in AutoMLOps?**

**Evidently AI** is an open-source ML monitoring library. AutoMLOps uses it to compare two datasets:
- **Baseline**: the training data distribution (saved when the model is deployed)
- **Current**: the recent production prediction data (accumulated since last check)

Evidently computes statistical tests per feature:

- **Numerical features** (petal_length, etc.): **Wasserstein Distance** (earth mover's distance) — measures the minimum "work" needed to transform one distribution into another. Large distance = significant shift.
- **Categorical features** (species, labels): **Jensen-Shannon Divergence** — a symmetric measure of the difference between two probability distributions, bounded in [0, 1].

When a feature's drift score exceeds a threshold (configurable, default ~0.1), it's flagged as drifted. AutoMLOps generates an Evidently HTML report and triggers the auto-retrain flow.

---

**Q: What is the circuit breaker and why is it needed?**

The circuit breaker prevents **runaway retrain loops**. Without it:
1. Drift is detected → retrain
2. New model deployed → drift test runs again → drift still detected (data hasn't changed) → retrain again
3. Infinite loop, consuming compute, destabilizing the system

The circuit breaker: **maximum 3 retrains within any 24-hour window**. If this limit is hit, further retrains are blocked and an alert is sent to the team. The counter resets after 24 hours.

This is analogous to a circuit breaker in distributed systems (like Netflix Hystrix) — it opens when failures (or in this case, retrains) exceed a threshold, preventing cascading problems.

---

## 11. Explainability — SHAP

**Q: What is SHAP and how does AutoMLOps use it?**

**SHAP** (SHapley Additive exPlanations) is a framework for explaining machine learning predictions, grounded in cooperative game theory (Shapley values from 1953). It answers: "For this specific prediction, how much did each feature contribute?"

For a prediction like "this flow is a port scan with 94% confidence", SHAP tells you:
- `unique_dst_ports = 412.0` contributed +0.45 (strongly supports port_scan)
- `fan_out = 87.0` contributed +0.38 (supports port_scan)
- `bytes_per_sec = 2340.0` contributed +0.12 (supports port_scan)
- `is_tls = 0` contributed -0.05 (slightly against, but port scans rarely use TLS)

**TreeExplainer** is SHAP's algorithm for tree-based models (XGBoost, RandomForest). Unlike generic SHAP which requires sampling, TreeExplainer computes **exact Shapley values** by exploiting the tree structure. This makes it much faster — O(TLD) per prediction where T=trees, L=leaves, D=depth — suitable for real-time use.

AutoMLOps's `ThreatExplainer` class (`ml/explainability.py`) wraps TreeExplainer and returns human-readable evidence strings: "Connections to many destination ports: 412 (supports prediction)".

---

**Q: Why are Shapley values the right explainability method here?**

Alternatives considered:
- **LIME** (Local Interpretable Model-Agnostic Explanations): approximates locally with a linear model. Fast but inconsistent — two very similar inputs can get completely different explanations depending on the sampling.
- **Feature importance** (permutation, Gini): global measure, tells you which features matter across the whole dataset, not for this specific prediction
- **Attention weights** (for neural networks): not applicable to tree models

Shapley values have desirable mathematical properties:
1. **Efficiency**: the sum of all SHAP values equals the difference between the model's prediction and the baseline (average prediction)
2. **Symmetry**: features that contribute equally get equal values
3. **Dummy**: features with no impact get zero SHAP value
4. **Additivity**: for model ensembles, SHAP values add up correctly

For a security system where a human analyst must review and act on each alert, these consistency guarantees matter — the same input always produces the same explanation.

---

## 12. Hyperparameter Tuning — Optuna

**Q: What is Optuna and how does it work?**

**Optuna** is a hyperparameter optimization framework that uses **Bayesian optimization** to search the hyperparameter space efficiently. The default sampler is **TPE (Tree-structured Parzen Estimator)**:

1. For the first few trials (exploration phase): samples hyperparameters randomly
2. Splits past trials into "good" (top 25% by objective) and "bad" (bottom 75%)
3. Fits two distributions: p(hyperparams | good trials) and p(hyperparams | bad trials)
4. Samples new candidates from p(good) and evaluates each by the ratio p(good)/p(bad) — picking configurations that are more likely to be good than bad
5. Evaluates the candidate, updates the distributions, repeats

This is vastly more efficient than:
- **Grid search**: exhaustively tries all combinations (exponential in number of parameters)
- **Random search**: samples uniformly, wastes trials in bad regions
- **Manual tuning**: requires expert knowledge and time

In practice, TPE finds near-optimal configurations in 20–50 trials for most tabular datasets, whereas grid search might need hundreds.

---

**Q: What objective does Optuna optimize for?**

**F1 macro score** on the validation set. F1 macro computes F1 per class and averages — it treats all classes equally regardless of size. This is the right choice for:
- Iris (3 balanced classes) — all classes equally important
- Aegis (7 imbalanced classes) — we don't want the model to ignore rare attack types

Accuracy was not used as the objective because it's dominated by the majority class. If benign traffic is 90% of flows, a model that predicts "benign" for everything gets 90% accuracy but F1 macro ≈ 0.14.

---

**Q: What happens when the validation set is empty (synthetic data)?**

When Aegis runs with only one scenario per class (synthetic mode), the scenario-level split puts all scenarios in train with nothing left for val or test. Optuna can't evaluate on a held-out set.

The code handles this with a **training-set fallback**: Optuna evaluates on the training data itself. This is clearly labeled in warnings and the classification report as "NOT a valid generalisation estimate." It's a deliberate design decision — the synthetic path is for development/testing, not production deployment. When real Parquet files exist (multiple scenarios per class), this fallback never triggers.

---

## 13. MLflow Experiment Tracking

**Q: What does MLflow track in AutoMLOps?**

**MLflow** tracks every training run with:

| Category | Data Tracked |
|---|---|
| Parameters | Optuna best hyperparameters (`n_estimators`, `max_depth`, `learning_rate`, etc.) |
| Metrics | `accuracy`, `f1`, `precision`, `recall` on test set |
| Tags | `framework`, `repo_id`, `commit_sha`, `run_id`, `triggered_by` |
| Artifacts | `model.pkl`, `metrics.json`, classification report, confusion matrix |

The MLflow UI at `http://localhost:5000` provides:
- **Experiment comparison**: plot accuracy vs. n_estimators across runs
- **Model registry**: version the model and promote from Staging to Production
- **Run reproducibility**: given a run ID, you can see exactly what hyperparameters and data produced a model

For the demo, judges can open MLflow and see the jump from v1's ~0.92 to v2's ~0.97, along with the exact Optuna parameters that achieved it.

---

## 14. Security & Webhook Verification

**Q: How does AutoMLOps verify that webhooks are genuinely from GitHub?**

GitHub computes an **HMAC-SHA256 signature** of the raw request body using the shared secret:
```
signature = "sha256=" + HMAC-SHA256(secret, payload_bytes)
```
This is sent in the `X-Hub-Signature-256` header.

AutoMLOps recomputes the expected signature using the same secret and compares with:
```python
hmac.compare_digest(expected, received)
```

`hmac.compare_digest()` is critical — it uses **constant-time comparison**. A naive string comparison (`expected == received`) leaks timing information: it returns faster when more characters match. An attacker could send many requests with slightly different signatures and measure response times to progressively forge a valid signature (timing attack). `compare_digest` always takes the same time regardless of where the strings differ.

Any request without a valid signature returns HTTP 401 Unauthorized.

---

**Q: What is the webhook secret and where is it configured?**

The secret is `automlops-dev-secret` — set in:
1. **GitHub**: Webhook settings → Secret field
2. **AutoMLOps**: `github_app/app_config.py`:
   ```python
   GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "automlops-dev-secret")
   ```

For production, this should be a randomly generated 32+ character string set via environment variable, not the default. The current default is intentionally simple for the demo.

---

## 15. Technology Stack

**Q: List the full technology stack and justify each choice.**

| Layer | Technology | Why |
|---|---|---|
| Backend API | FastAPI (Python) | Async-native, auto-generated OpenAPI docs, Pydantic validation, fastest Python web framework |
| Database | SQLite + SQLAlchemy | Zero setup for self-hosted; ORM allows easy schema migration; swap to PostgreSQL later without app changes |
| ML Framework | XGBoost | Best-in-class for tabular data; native sample_weight; SHAP integration; fast inference |
| Hyperparameter Tuning | Optuna | TPE beats random/grid search; pruning support; integrates with XGBoost natively |
| Explainability | SHAP TreeExplainer | Exact Shapley values for trees; faster than model-agnostic SHAP; human-readable output |
| Drift Detection | Evidently AI | Production-grade statistical tests; generates HTML reports; maintains Evidently baseline |
| Experiment Tracking | MLflow | Industry standard; free; run comparison, model registry, artifact storage |
| Public Tunnel | Cloudflare Tunnel | Free; no firewall changes; encrypted; works behind NAT |
| Alerts | Discord Webhook | Free; instant push notifications; works on mobile; no setup |
| Frontend | React + Vite | Fast HMR during development; component model fits dashboard UI |
| API Docs | FastAPI OpenAPI | Auto-generated from code; no separate documentation step |
| Anomaly Detection | scikit-learn Isolation Forest | Unsupervised; no attack labels needed; O(n log n) training; well-understood |

---

## 16. Design Decisions & Trade-offs

**Q: Why did you choose self-hosted over cloud ML platforms (SageMaker, Vertex AI)?**

| Aspect | Self-hosted (AutoMLOps) | Cloud (SageMaker/Vertex) |
|---|---|---|
| Cost | Free (runs on laptop) | $0.05–$0.90/hour per training job |
| Setup | Clone repo, pip install | IAM roles, VPCs, ECR, CloudFormation |
| Latency | Under 1 second to trigger | Minutes to provision training instances |
| Portability | Any machine with Python | Vendor lock-in |
| Scale | Single machine | Auto-scales to thousands of nodes |
| Security | Local network | Enterprise-grade (SOC2, HIPAA) |

For a research/hackathon context, self-hosted wins on every dimension except scale and compliance. The architecture is designed so that the runner can be swapped — the runner interface is generic and could dispatch to GitHub Actions, SageMaker, or Vertex with a different `launch_pipeline_thread()` implementation.

---

**Q: Why SQLite instead of a "real" database?**

For a self-hosted single-machine deployment, SQLite is the right choice:
- No server process to manage
- File-based (the entire database is one `.db` file)
- ACID compliant — transactions are safe even with concurrent reads/writes
- SQLAlchemy abstracts the database, so swapping to PostgreSQL requires only changing the connection string

The only scenario where SQLite would be inadequate is multi-machine deployment (multiple AutoMLOps instances) needing shared state. For the current single-node architecture, it's perfectly appropriate.

---

**Q: Why is the pipeline triggered by push to main only, not all branches?**

The webhook is configured on the `iris-classifier` repository. GitHub fires webhooks on all pushes by default, but the webhook handler checks the `ref` field:
```python
ref = payload.get("ref", "")  # e.g., "refs/heads/main"
```

For the demo, only pushes to `main` trigger a pipeline run. Feature branch pushes (like `v2`) go to GitHub but the pipeline doesn't train — this is intentional. The v2 branch was pushed and sat waiting until the live demo moment when `git merge v2` merges it into main and triggers the full automated pipeline.

---

**Q: What would you add if you had more time?**

1. **Named Cloudflare Tunnel**: permanent URL tied to `ebinthomas.dev/webhook/github` — no URL change on restart
2. **GitHub Actions runner**: dispatch training to GitHub's infrastructure instead of local thread, enabling GPU training
3. **Model serving**: FastAPI inference endpoint (`/predict`) that loads the deployed model and accepts requests
4. **Multi-repo parallelism**: PostgreSQL + Redis queue instead of Python thread + SQLite lock
5. **Rollback**: if the new model performs worse in production (measured by Evidently), automatically redeploy the previous version
6. **Feature store**: centralized store for precomputed features, enabling faster retraining and consistent train/serve features
7. **A/B testing**: route X% of traffic to new model, X% to old, compare outcomes before full rollout

---

*Document covers: AutoMLOps architecture, iris-classifier v1/v2, Aegis NIDS, synthetic dataset generation, all algorithms, all design decisions. Last updated for presentation 2026-10-25.*
