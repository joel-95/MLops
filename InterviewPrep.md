# AutoMLOps Interview Prep — Complete Study Guide

> Study this before the presentation. Every question they can ask is answered here.

---

## 1. What Is This Project? (The One-Line Answer)

**AutoMLOps** is a self-hosted machine learning lifecycle platform that automatically trains, validates, deploys, and monitors ML models whenever a developer pushes code to GitHub — with zero manual steps.

---

## 2. The Full Architecture (Know This Cold)

```
GitHub Push
    │
    ▼
GitHub Webhook (POST /webhook/github)
    │
    ▼
FastAPI Backend  ←→  SQLite Database
    │
    ├── Pipeline Runner (background thread)
    │       ├── Train model (sklearn / xgboost / aegis_nids)
    │       ├── Quality Gate (check accuracy/F1 thresholds)
    │       └── POST result to /webhook/pipeline-result
    │
    ├── Deploy (serving_app.py on dedicated port)
    │
    ├── Monitor (Evidently drift detection)
    │       └── Circuit Breaker (max 3 retrains / 24h)
    │
    └── MLflow (experiment tracking)

React Frontend (port 5173) ←→ FastAPI Backend (port 8000)
Cloudflare Tunnel → exposes port 8000 to the internet for webhooks
```

---

## 3. Technology Stack

| Component | Technology | Why |
|---|---|---|
| Backend API | FastAPI (Python) | Async, fast, auto-generates docs at /docs |
| Frontend | React + Vite | Fast dev server, component-based UI |
| Database | SQLite (SQLAlchemy ORM) | Zero-setup, sufficient for demo scale |
| ML Training | scikit-learn, XGBoost, Optuna | Industry standard for tabular data |
| Explainability | SHAP TreeExplainer | Model-agnostic feature importance |
| Drift Detection | Evidently AI | Generates HTML drift reports |
| Experiment Tracking | MLflow | Logs every training run with params + metrics |
| Public URL | Cloudflare Tunnel | Exposes localhost to GitHub webhooks securely |
| Anomaly Detection | Isolation Forest | Unsupervised, no labelled anomaly data needed |

---

## 4. How Each Part Works

### 4.1 GitHub Webhook
- When you push to GitHub, GitHub sends a POST request to `/webhook/github`
- The backend verifies the HMAC-SHA256 signature using the shared webhook secret (`automlops-dev-secret`)
- If it matches the repo in the database, it spawns a **pipeline thread**
- Returns immediately (HTTP 200) — the training happens in the background

**Q: Why verify the HMAC signature?**
Without it, anyone who knows your URL could fake a push event and trigger your pipeline. HMAC-SHA256 means only GitHub (who knows the secret) can produce a valid signature.

### 4.2 Pipeline Runner (`runner/local_runner.py`)
Steps in order:
1. Mark run as "running" in DB
2. Read `framework` from the repo's stored `mlops.yaml`
3. Dispatch to the right trainer (`sklearn` → `train_v1()`, `xgboost` → `train_xgboost()`, `aegis_nids` → load bridge)
4. Trainer writes `metrics.json` and `artifacts/model.pkl`
5. Quality gate checks `metrics.json` against thresholds in `mlops.yaml`
6. If passed: deploy + trigger monitoring
7. POST callback to `/webhook/pipeline-result`
8. Update DB

**Q: Why run training in a background thread?**
FastAPI must return HTTP 200 immediately. Training can take 30+ seconds. If we waited, the webhook would time out and GitHub would mark it failed.

### 4.3 Quality Gate (`ml/quality_gate.py`)
- Reads `metrics_threshold` from `mlops.yaml`
- For each metric: compares actual vs threshold
- Lower-is-better: `loss`, `rmse`, `mae` — checks `actual ≤ threshold`
- Higher-is-better: `accuracy`, `f1`, `precision`, `recall` — checks `actual ≥ threshold`
- **AND logic**: ALL metrics must pass. One failure = gate fails = no deployment

**Q: What happens if the quality gate fails?**
The model is NOT deployed. The old deployed version keeps serving predictions. A failure alert is sent. The pipeline status shows "failed" in the dashboard.

### 4.4 Deployment (`deploy/serving_app.py`)
- Each repo gets a **dedicated port** (deterministic, derived from repo ID hash)
- iris-classifier → port 8003
- A Flask/FastAPI serving app loads `artifacts/model.pkl` and exposes `/predict`
- The Cloudflare tunnel (or localhost) proxies requests to it

### 4.5 Monitoring (`monitoring/monitor.py` + Evidently)
- After deployment, trains an **Isolation Forest** on the baseline training data
- Every monitoring cycle: compares recent traffic features vs baseline
- Uses **Evidently** to generate HTML drift reports
- Tracks per-column drift scores (Jensen-Shannon divergence / Wasserstein distance)
- **Circuit breaker**: if drift detected, triggers retrain — but max 3 retrains per 24 hours to prevent runaway loops

### 4.6 MLflow Integration
- Every training run logs: hyperparameters, metrics, model artifact path
- Accessible at `http://localhost:5000` (MLflow UI)
- Lets you compare run histories over time

---

## 5. Model 1 — Iris Classifier (The Live Demo Model)

### 5.1 Dataset
- 150 samples, 3 classes: setosa, versicolor, virginica
- 4 features: sepal_length, sepal_width, petal_length, petal_width (all in cm)
- Perfectly balanced (50 samples per class)
- A classic, well-understood benchmark dataset

### 5.2 v1 — RandomForest Baseline (`framework: sklearn`)

**What it does:**
- StandardScaler normalises the 4 features (mean=0, std=1)
- RandomForestClassifier: 100 trees, max_depth=4
- Train/test split: 80/20, stratified

**Why StandardScaler?**
Tree-based models don't need it, but it's good practice for pipelines that might include SVM or kNN in future. Included for correctness.

**Why RandomForest?**
- Ensemble of decision trees → reduces overfitting
- Handles small datasets well
- Robust to outliers
- Fast to train

**Expected metrics:**
- Accuracy: ~0.92
- F1: ~0.92

### 5.3 v2 — XGBoost + Optuna (`framework: xgboost`)

**What it does:**
1. Loads iris data, encodes labels (LabelEncoder: setosa=0, versicolor=1, virginica=2)
2. Computes class-balanced sample weights
3. Runs 20 Optuna trials to find best hyperparameters
4. Trains final XGBoost model with best params
5. Evaluates on held-out 20% test set

**Expected metrics:**
- Accuracy: ~0.97
- F1: ~0.97

**Quality gate thresholds for iris-classifier:**
```yaml
metrics_threshold:
  accuracy: 0.92
  f1: 0.90
```
v2 comfortably passes. v1 just barely passes.

---

## 6. Model 2 — Aegis NIDS (Network Intrusion Detection System)

### 6.1 What Is NIDS?
A Network Intrusion Detection System monitors network traffic and classifies connections as benign or malicious. Instead of looking at packet payloads (deep packet inspection), Aegis uses **network flow features** — statistical properties of connections — making it protocol-agnostic and faster.

### 6.2 The 7 Threat Classes
| Class | What It Means |
|---|---|
| **benign** | Normal, legitimate traffic |
| **ddos** | Distributed Denial of Service — flood attack to exhaust resources |
| **c2_beaconing** | Command & Control — malware phoning home at regular intervals |
| **dns_anomaly** | DNS tunnelling or DGA (Domain Generation Algorithm) — hides data in DNS |
| **exfiltration** | Data theft — large outbound transfers, high out/in byte ratio |
| **malware_tls** | Malware using encrypted TLS channel — suspicious JA4/cipher fingerprints |
| **port_scan** | Reconnaissance — probing many ports/hosts to find open services |

### 6.3 The 36 Input Features (Know the Groups)

**Volume & Rate (7):**
`packets_per_sec`, `bytes_per_sec`, `outbound_inbound_ratio`, `orig_bytes`, `resp_bytes`, `orig_pkts`, `resp_pkts`

**Topology / Fan-out (4):**
`fan_out`, `fan_in`, `unique_dst_ips`, `unique_dst_ports`

**Timing / Inter-Arrival Time (6):**
`iat_mean`, `iat_std`, `iat_min`, `iat_max`, `connection_frequency`, `src_ip_entropy`

**Periodicity (1):**
`periodicity_score` — capped at 100 to handle near-zero IAT std edge case

**DNS Features (7):**
`dns_query_entropy`, `domain_length_mean`, `domain_length_max`, `subdomain_count`, `dns_record_type_a_ratio`, `dns_record_type_txt_ratio`, `dns_query_count`

**TLS / Encryption (4):**
`tls_version`, `cipher_suite_enc`, `is_tls`, `ja4_hash_enc`

**QUIC Protocol (4):**
`is_quic`, `quic_0rtt`, `quic_pkt_size_mean`, `quic_pkt_size_std`

**Connection Basics (3):**
`src_port`, `dst_port`, `duration`

**Q: Why 36 features and not raw packets?**
Flow features are computed over an entire connection (not per-packet), making them compact and model-friendly. Raw packets would require deep packet inspection which is computationally expensive and legally restricted in some jurisdictions.

### 6.4 Two-Stage Inference Architecture

**Stage 1 — Isolation Forest (anomaly pre-filter):**
- Trained on benign traffic baseline
- Scores each flow: higher score = more anomalous
- Threshold: 0.621 (from `iso_forest.joblib`)
- Returns `anomaly_score` (float) and `is_anomaly` (bool)
- Purpose: catches truly novel attacks that XGBoost has never seen

**Stage 2 — XGBoost Classifier:**
- `objective: multi:softprob` — outputs probability per class
- 7 classes, probability vector sums to 1.0
- `argmax(proba)` → predicted class
- If `max(proba) < 0.50` (confidence threshold) → prediction becomes `unknown_anomaly`
- Otherwise → returns the class name

**Q: Why two stages?**
XGBoost can only classify into the 7 classes it was trained on. A completely new attack type would be silently misclassified. Isolation Forest catches "I've never seen anything like this" regardless of what class it would be.

**Q: Why confidence threshold 0.50?**
If the model is unsure (e.g., 35% ddos, 30% port_scan, 25% exfiltration) it means the traffic doesn't clearly fit any known pattern. Flagging it as `unknown_anomaly` is safer than making a low-confidence decision.

### 6.5 XGBoost Model Details
- `objective: multi:softprob` — softmax multi-class with probability output
- `num_class: 7`
- `eval_metric: mlogloss` — multi-class log loss
- No StandardScaler — Aegis uses raw feature values (XGBoost is scale-invariant)
- `use_label_encoder` removed (deprecated in XGBoost 2.0+)

### 6.6 SHAP Explainability (TreeExplainer)
- Uses `shap.TreeExplainer` — exact Shapley values computed directly from tree structure (no sampling)
- For `multi:softprob`: SHAP output is 3D array `(n_samples, n_classes, n_features)` → we take the predicted class slice
- Each SHAP value = how much that feature pushed the prediction toward the predicted class
- Positive SHAP = feature pushes toward the class; Negative = pushes away
- Used in the dashboard to show "which features triggered this threat classification"

**Q: What is a SHAP value?**
Shapley values come from cooperative game theory. For a model prediction, the SHAP value for a feature is: "how much does this feature contribute to the difference between the actual prediction and the average prediction across all samples?" It distributes the prediction fairly among all features.

**Q: Why TreeExplainer instead of KernelExplainer?**
TreeExplainer is exact (not approximate) and O(TLD) — T trees, L leaves, D depth. KernelExplainer is model-agnostic but runs thousands of inference passes. For a forest/XGBoost model, TreeExplainer is 10-100x faster.

### 6.7 The Bridge Pattern (Why This Matters)

**The problem:** The Aegis model lives in a separate GitHub repo. We want to use it in AutoMLOps without:
- Copying the model code
- Modifying Aegis
- Creating a dependency between the two repos

**The solution (`ml/aegis_bridge.py`):**
- Loads `model.joblib` and `iso_forest.joblib` by file path only (zero Aegis imports)
- Wraps them in AutoMLOps' standard bundle format: `{model, preprocessor, framework, label_encoder, iso_bundle}`
- Implements `NIDSPreprocessorBundle.transform_single()` — the same interface as the iris preprocessor
- Hardcodes `INT_TO_CLASS = {0:"benign", 1:"c2_beaconing", ...}` — derived from LabelEncoder's alphabetical sort, avoiding the need for `label_encoder.joblib`
- Everything downstream (serving_app, explainability, monitoring) sees the exact same bundle format

**Q: What's the path resolution?**
`_DEFAULT_AEGIS_ML_DIR = Path(__file__).resolve().parent.parent.parent.parent / "Aegis" / "ml"`
That's 4 `.parent` calls: `ml/` → `MLops/` → `ai/` → `GitHub/` → then down to `Aegis/ml`. Can be overridden with `AEGIS_ML_DIR` env var.

---

## 7. XGBoost — Deep Dive Q&A

**Q: What is XGBoost?**
eXtreme Gradient Boosting. Builds an ensemble of decision trees sequentially — each tree corrects the errors of the previous one. Uses gradient descent in function space to minimise a differentiable loss function.

**Q: What is gradient boosting?**
Start with a simple prediction (e.g., mean). Compute residuals. Fit a tree to predict the residuals. Add the tree's output (scaled by learning rate) to the prediction. Repeat. Each iteration reduces the training loss.

**Q: What is `multi:softprob`?**
The softmax objective for multi-class classification. Instead of predicting a single class, the model outputs a probability distribution across all classes (probabilities sum to 1.0). Allows confidence estimation.

**Q: What is `mlogloss` (multi-class log loss)?**
`L = -1/N × Σ Σ y_ij × log(p_ij)` — average negative log probability assigned to the correct class. Penalises confident wrong predictions heavily.

**Q: What is `num_class`?**
Tells XGBoost how many classes exist. Required for `multi:softprob`. For Aegis: 7. For iris: 3.

**Q: What are the key hyperparameters?**
| Parameter | What It Controls |
|---|---|
| `max_depth` | How deep each tree can grow — higher = more complex, more overfit risk |
| `learning_rate` (eta) | Shrinks each tree's contribution — lower = more trees needed but more robust |
| `n_estimators` | Number of trees — more trees = better fit up to a point then overfitting |
| `subsample` | Fraction of training data per tree — prevents overfit via randomness |
| `colsample_bytree` | Fraction of features per tree — reduces correlation between trees |
| `min_child_weight` | Minimum sum of instance weights in a leaf — prevents tiny, noisy splits |
| `reg_alpha` / `reg_lambda` | L1/L2 regularisation — shrinks leaf weights to reduce overfit |

**Q: Why remove `use_label_encoder`?**
XGBoost 2.0 removed this parameter entirely. Passing it causes a `TypeError`. The encoder was a pre-2.0 shortcut that applied LabelEncoder internally — now callers encode labels themselves before training.

---

## 8. Optuna — Deep Dive Q&A

**Q: What is Optuna?**
An automatic hyperparameter optimisation framework. Instead of grid search (tries all combinations) or random search (tries random combinations), Optuna uses **Bayesian optimisation** with a **Tree-structured Parzen Estimator (TPE)** sampler.

**Q: What is TPE?**
TPE models the distribution of good hyperparameter values and bad ones separately. It uses the history of previous trials to pick the next trial's parameters such that the expected improvement is maximised. Better than random search after ~10 trials.

**Q: How many trials do we run?**
- Iris classifier: 20 trials (fast, small dataset)
- The search space: max_depth [3-10], learning_rate [0.01-0.3 log scale], n_estimators [50-400], subsample [0.6-1.0], colsample_bytree [0.6-1.0], min_child_weight [1-10], reg_alpha, reg_lambda

**Q: What is the objective function in Optuna?**
For each trial, train XGBoost with the suggested params and return the 5-fold cross-validation F1 score on the training set. Optuna maximises this score.

**Q: Why cross-validation in the objective, not just train/test split?**
CV gives a more reliable estimate of generalisation performance. A single train/test split can be lucky or unlucky. 5-fold CV averages over 5 different splits — more stable.

---

## 9. Isolation Forest — Deep Dive Q&A

**Q: What is Isolation Forest?**
An unsupervised anomaly detection algorithm. Key insight: anomalies are **easier to isolate** than normal points. Build random trees that recursively split data — anomalies get isolated in fewer splits (shorter path length).

**Q: How does it score anomalies?**
Anomaly score = `2^(-mean_path_length / c(n))` where `c(n)` is the average path length for a dataset of size n. Scores near 1 = anomaly. Scores near 0 = normal.

In the Aegis bridge, we use `-iso_model.score_samples(X)` which flips the sign so **higher = more anomalous**.

**Q: Why use Isolation Forest alongside XGBoost?**
XGBoost is supervised — it only knows the 7 classes it was trained on. Isolation Forest is unsupervised — it knows what "normal" looks like without needing labels. Together they handle:
- Known threats → XGBoost classifies them
- Novel/unknown threats → Isolation Forest flags them as anomalous

**Q: What is the threshold 0.621?**
Computed during Aegis training by finding the anomaly score cutoff that maximises the F1 score on a validation set containing both benign and anomalous traffic. Stored in `iso_forest.joblib`.

---

## 10. Drift Detection — Deep Dive Q&A

**Q: What is data drift?**
When the statistical distribution of real-world input features changes from the distribution the model was trained on. The model's predictions become unreliable.

**Q: How do we detect it?**
Using **Evidently AI**. It computes statistical tests on each feature column comparing a reference (training baseline) to the current (production traffic) distribution:
- Numerical features: **Wasserstein distance** (Earth Mover's Distance) — how much "work" to move one distribution to match the other
- Categorical features: **Jensen-Shannon divergence** — symmetric version of KL divergence

A column is flagged as drifted if its drift score exceeds a threshold (default: 0.1 for Wasserstein, 0.1 for JS divergence).

**Q: What happens when drift is detected?**
1. Dashboard shows "DRIFT DETECTED" with the drifted column names
2. `Trigger Retrain` becomes available
3. If auto-retrain is triggered: pipeline runs again with fresh data
4. Circuit breaker: max 3 auto-retrains per 24 hours (prevents infinite retrain loop if drift is persistent)

**Q: What is the circuit breaker pattern?**
From distributed systems: if an operation keeps failing or causing problems, "break" the circuit and stop attempting it. Here: if the model keeps retraining (because drift is persistent) but not solving the root problem, we stop after 3 times in 24h and require human intervention.

---

## 11. The Cloudflare Tunnel

**Q: Why do we need a tunnel?**
GitHub's servers need to reach your localhost backend to deliver webhook events. Your laptop is behind a router/NAT — not directly reachable from the internet. Cloudflare Tunnel creates an outbound connection from your machine to Cloudflare's edge, which then proxies inbound traffic back to localhost.

**Q: How does it work technically?**
`cloudflared` opens a persistent WebSocket connection to Cloudflare's edge. When GitHub sends a POST to your tunnel URL, Cloudflare forwards it through that connection to your local port 8000. No port forwarding or firewall changes needed.

**Q: Is this production-ready?**
For a demo, yes. In production you'd use a proper server with a public IP and TLS certificate (e.g., a VPS + nginx + Let's Encrypt), or a managed cloud service.

---

## 12. Common Presentation Questions & Answers

**Q: Why build this instead of using AWS SageMaker / Azure ML / GCP Vertex AI?**
Self-hosted means: no cloud vendor lock-in, no per-inference pricing, data stays on-premises (important for security/compliance), full control over the pipeline logic. Also — it's educational. We built every component and understand every line.

**Q: How is this different from MLflow?**
MLflow only tracks experiments (logs params/metrics). It doesn't: trigger training on pushes, enforce quality gates, deploy models, detect drift, or auto-retrain. AutoMLOps wraps the full lifecycle; MLflow is one component inside it.

**Q: What database does it use and why SQLite?**
SQLite — single file, zero setup, sufficient for a project of this scale. In production you'd use PostgreSQL for concurrent writes and proper transaction isolation.

**Q: Can it handle multiple ML frameworks?**
Yes. The `framework` key in `mlops.yaml` dispatches to the right trainer. Currently supported: `sklearn`, `xgboost`, `aegis_nids`. Adding PyTorch or TensorFlow would mean adding a new dispatch branch in `runner/local_runner.py`.

**Q: What is mlops.yaml and why?**
It's the "contract" between the model developer and the platform. Declares: what framework, what features, what dataset, what quality thresholds. The platform reads it to know how to train and validate the model. Inspired by GitHub Actions workflow files.

**Q: What is the serving app?**
After a model passes the quality gate, it's loaded into a lightweight FastAPI app (`deploy/serving_app.py`) that exposes `/predict`. Each repo gets its own port. The serving app loads `artifacts/model.pkl` (the bundle), accepts a JSON dict of features, runs preprocessing + inference, and returns `{prediction, confidence}` plus SHAP explanations.

**Q: What is weighted F1?**
`F1 = 2 × (precision × recall) / (precision + recall)`. Weighted F1 computes F1 for each class separately, then takes a weighted average by class support (number of true instances per class). Better than macro-F1 when classes are imbalanced.

**Q: What is log loss?**
`L = -1/N × Σ log(p_correct)`. Average negative log probability assigned to the correct class. Measures how confident and correct the model is. Lower is better. A model that says "90% correct" is penalised less than one that says "51% correct."

**Q: What is the difference between v1 and v2 of the iris classifier?**
| | v1 | v2 |
|---|---|---|
| Algorithm | RandomForestClassifier | XGBClassifier |
| Hyperparams | Fixed (100 trees, depth 4) | Optuna-tuned (20 trials) |
| Accuracy | ~0.92 | ~0.97 |
| Training time | ~0.5s | ~12s |
| Preprocessing | StandardScaler | LabelEncoder (no scaler — XGBoost doesn't need it) |

**Q: Why does XGBoost not need StandardScaler?**
XGBoost splits on feature thresholds — it doesn't compute distances or dot products. Whether `petal_length` is 1.4 cm or 0.14 (after scaling), the split threshold just adjusts accordingly. Distance-based models (kNN, SVM with RBF kernel) and gradient-based models (linear regression, neural networks) need scaling because large-magnitude features dominate.

**Q: What is stratified train/test split?**
Ensures the class distribution in the split mirrors the original dataset. For iris (50 samples each): a 20% stratified split gives exactly 10 setosa, 10 versicolor, 10 virginica in the test set. Without stratify, you might get an unrepresentative test set by chance.

**Q: How does the quality gate know what thresholds to use for each repo?**
Each repo's `mlops.yaml` is stored in the database when the repo is connected. The runner reads `mlops_config["metrics_threshold"]` from the DB. So iris-classifier has `{accuracy: 0.92, f1: 0.90}` and Aegis has its own thresholds — they're fully independent.

---

## 13. Things That Could Go Wrong (And Why They Don't)

| Scenario | What We Do |
|---|---|
| Webhook arrives while pipeline is running | Pipeline lock (`_running_pipelines` set) deduplicates — second trigger is silently dropped |
| Training raises an exception | try/except catches it, marks run as "failed", old deployed model keeps running |
| Quality gate fails | No deployment, previous model untouched, alert sent |
| Serving app crashes | Monitoring detects dead port, marks deployment inactive |
| Anomaly model training fails | Logged as warning, rest of pipeline continues |
| No `mlops.yaml` in repo | Fallback to `demo_repo/mlops.yaml` defaults |

---

## 14. Key Numbers to Have Ready

| | Value |
|---|---|
| Iris v1 accuracy | ~0.92 |
| Iris v2 accuracy | ~0.97 |
| Iris features | 4 (sepal_length, sepal_width, petal_length, petal_width) |
| Iris classes | 3 (setosa, versicolor, virginica) |
| Aegis features | 36 |
| Aegis classes | 7 |
| Aegis accuracy | 0.96 |
| Aegis F1 | 0.95 |
| Optuna trials | 20 (iris) |
| Isolation Forest threshold | 0.621 |
| Confidence threshold | 0.50 (below this → unknown_anomaly) |
| Circuit breaker limit | 3 retrains / 24 hours |
| Backend port | 8000 |
| Frontend port | 5173 |
| iris-classifier serving port | 8003 |
