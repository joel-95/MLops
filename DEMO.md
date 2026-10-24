# AutoMLOps Demo Script

## 5 Minutes Before You Present

### 1. Start the backend (if not already running)
Open a terminal in `C:\Users\ebint\OneDrive\Documents\GitHub\ai\MLops` and run:
```
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
Verify: open `http://localhost:8000/health` — should say `{"status":"healthy"}`.

### 2. Start the frontend (if not already running)
In a second terminal:
```
cd frontend
npm run dev
```
Open `http://localhost:5173` in Chrome.

### 3. Start the Cloudflare tunnel
In a third terminal:
```
C:\Users\ebint\AppData\Local\cloudflared\cloudflared2.exe tunnel --url http://localhost:8000 --no-autoupdate
```
Wait ~8 seconds. Copy the `https://xxxx-xxxx.trycloudflare.com` URL that appears.

### 4. Update the GitHub webhook
1. Go to https://github.com/ebinthomas06/iris-classifier/settings/hooks
2. Click the existing webhook
3. Change **Payload URL** to: `<your-new-tunnel-url>/webhook/github`
4. Secret stays: `automlops-dev-secret`
5. Click **Update webhook**

### 5. Quick sanity check
- Dashboard shows **iris-classifier** with Pipeline: passed, Accuracy ~0.97
- Dashboard shows **repo_aegis** (Aegis NIDS) in the list
- Keep the cloudflared terminal window open and visible (or minimised — just don't close it)

---

## Demo Order

### Part 1 — What is AutoMLOps? (2 min, just talk through the dashboard)

Open the dashboard. Point out:
- Left panel: connected repos (iris-classifier, Aegis NIDS)
- Each repo shows pipeline status, deploy status, model metrics
- The platform handles train → quality gate → deploy → monitor → auto-retrain automatically

**Talking point:** "Every time a developer pushes code, AutoMLOps pulls it, trains the model, checks if it meets quality thresholds, and only deploys if it passes. No manual steps."

---

### Part 2 — Aegis NIDS: Pre-trained XGBoost model (3 min)

Click on **repo_aegis** in the dashboard.

1. Click **Run Pipeline**
   - Explain: "This is a pre-trained network intrusion detection model. We import it without modifying the original project."
   - It completes in ~2 seconds (no retraining — just loads artifacts)
   - Show: Accuracy 0.96, F1 0.95

2. Click **Run Monitoring**
   - Show the SHAP feature importance / explainability section
   - Explain: "SHAP tells us which network features most influenced the threat classification — packets per second, periodicity score, DNS entropy."

3. Point to the 7 threat classes:
   - benign, ddos, c2_beaconing, dns_anomaly, exfiltration, malware_tls, port_scan

**Talking point:** "We bridge an existing trained model directly into the AutoMLOps lifecycle — zero changes to the original Aegis project."

---

### Part 3 — Live Demo: Push triggers automatic retraining (5 min, the main event)

Click on **iris-classifier** in the dashboard.

**Before the push:** point out the current metrics:
- Framework: sklearn (RandomForest baseline)
- Accuracy: ~0.92, F1: ~0.92

Now open a terminal. Say: "I'm going to merge the XGBoost branch into main — this simulates a developer upgrading the model."

```powershell
cd "C:\Users\ebint\AppData\Local\Temp\iris-classifier-setup\iris-classifier"
git checkout main
git merge v2
git push origin main
```

Switch back to the dashboard. Within 10–15 seconds:
- Pipeline status changes to **running**
- After ~30 seconds: Pipeline **passed**, metrics update
- Accuracy jumps to **~0.97**, F1 to **~0.97**

**Talking point:** "GitHub sent a webhook the moment we pushed. AutoMLOps received it, ran Optuna hyperparameter tuning across 20 trials, evaluated the quality gate — accuracy threshold 0.92 — it passed, so it deployed automatically."

Point to the **Reports** section:
- Version comparison: v1 vs v2 side by side
- Shows exactly which metrics improved and by how much

---

### Part 4 — Drift Detection & Auto-Retrain Circuit Breaker (3 min)

Stay on the iris-classifier page.

1. Click **Simulate Normal Traffic (150 samples)**
   - "We're logging synthetic predictions to simulate production traffic."

2. Click **Simulate Drifted Traffic (150 samples)**
   - "This shifts petal_length 3x off the normal distribution — simulating real-world data drift."

3. Click **Run Monitoring**
   - Show: **Drift Detected** — petal_length flagged
   - Evidently HTML report appears (version comparison + drift report)

4. Click **Trigger Retrain**
   - Explain: "AutoMLOps has a circuit breaker — it won't retrain more than 3 times in 24 hours to prevent runaway retraining loops."

**Talking point:** "This closes the full MLOps loop: train → deploy → monitor → detect drift → retrain → redeploy. All automated."

---

## If Something Goes Wrong

| Problem | Fix |
|---|---|
| Dashboard blank / API error | Restart backend: `python -m uvicorn backend.main:app --port 8000` |
| Webhook 404 on GitHub | Tunnel URL changed — re-run cloudflared, update webhook URL |
| Pipeline stuck on "running" | Refresh page — or click Run Pipeline again (lock clears after 60s) |
| Aegis pipeline fails | Set env var: `set AEGIS_ML_DIR=C:\Users\ebint\OneDrive\Documents\GitHub\Aegis\ml` |
| Metrics show N/A after push | Wait 30s, click Refresh — Optuna tuning takes ~20–30s |

---

## Key Numbers to Know

| | v1 (sklearn) | v2 (XGBoost) |
|---|---|---|
| Model | RandomForest | XGBoost + Optuna |
| Accuracy | ~0.92 | ~0.97 |
| F1 | ~0.92 | ~0.97 |
| Training time | ~0.5s | ~12s (20 Optuna trials) |

**Aegis NIDS:** 36 network-flow features, 7 threat classes, XGBoost + Isolation Forest two-stage inference.
