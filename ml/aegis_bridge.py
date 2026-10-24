"""
AutoMLOps ↔ Aegis NIDS Bridge
==============================
Loads the trained Aegis NIDS model artifacts (model.joblib, iso_forest.joblib)
and wraps them in AutoMLOps' standard bundle format so they plug directly into
the existing serving pipeline, explainability module, and monitoring stack.

Zero changes to the Aegis project — this module only reads files by path.

Usage:
    from ml.aegis_bridge import load_aegis_bundle
    bundle = load_aegis_bundle()          # uses AEGIS_ML_DIR env var
    # bundle is now a standard AutoMLOps {model, preprocessor, framework, ...} dict
    # Pass it to explain_prediction(), deploy_model(), etc. unchanged.

Environment:
    AEGIS_ML_DIR  Path to the Aegis project's ml/ directory.
                  Defaults to ../../Aegis/ml relative to this file.
"""
import os
import logging
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("automlops.aegis_bridge")

# ── Path resolution ────────────────────────────────────────────────────────────
# Default: MLops is at .../GitHub/ai/MLops, Aegis is at .../GitHub/Aegis/ml
_DEFAULT_AEGIS_ML_DIR = Path(__file__).resolve().parent.parent.parent.parent / "Aegis" / "ml"
AEGIS_ML_DIR = Path(os.getenv("AEGIS_ML_DIR", str(_DEFAULT_AEGIS_ML_DIR)))

# ── Feature contract (copied from Aegis features/schema.py — NOT imported) ────
# Exact column order the XGBoost model and Isolation Forest expect.
FEATURE_COLUMNS: List[str] = [
    "packets_per_sec", "bytes_per_sec", "outbound_inbound_ratio",
    "orig_bytes", "resp_bytes", "orig_pkts", "resp_pkts",
    "fan_out", "fan_in", "unique_dst_ips", "unique_dst_ports",
    "iat_mean", "iat_std", "iat_min", "iat_max", "connection_frequency",
    "src_ip_entropy", "periodicity_score",
    "dns_query_entropy", "domain_length_mean", "domain_length_max",
    "subdomain_count", "dns_record_type_a_ratio", "dns_record_type_txt_ratio",
    "dns_query_count",
    "tls_version", "cipher_suite_enc", "is_tls", "ja4_hash_enc",
    "is_quic", "quic_0rtt", "quic_pkt_size_mean", "quic_pkt_size_std",
    "src_port", "dst_port", "duration",
]

# Boolean columns — cast to int 0/1
BOOL_COLUMNS = ["is_tls", "is_quic", "quic_0rtt"]

# Optional feature groups: fill with 0 if missing (DNS absent on non-DNS flows, etc.)
FILL_ZERO_COLUMNS = [
    "dns_query_entropy", "domain_length_mean", "domain_length_max",
    "subdomain_count", "dns_record_type_a_ratio", "dns_record_type_txt_ratio",
    "dns_query_count", "tls_version", "cipher_suite_enc", "ja4_hash_enc",
    "quic_pkt_size_mean", "quic_pkt_size_std",
    "iat_std", "iat_min", "iat_max", "periodicity_score",
]

PERIODICITY_CAP = 100.0  # raw value can reach 1e9 when IAT std ≈ 0

# ── Label mapping ──────────────────────────────────────────────────────────────
# Derived from sklearn LabelEncoder alphabetical sort of Aegis CLASS_NAMES.
# Verified against Aegis ml/train.py CLASS_NAMES list.
INT_TO_CLASS: Dict[int, str] = {
    0: "benign",
    1: "c2_beaconing",
    2: "ddos",
    3: "dns_anomaly",
    4: "exfiltration",
    5: "malware_tls",
    6: "port_scan",
}

# Confidence below this threshold → prediction becomes "unknown_anomaly"
CONFIDENCE_THRESHOLD = 0.50


# ── Label decoder ──────────────────────────────────────────────────────────────

class _DictLabelDecoder:
    """
    Minimal LabelEncoder-compatible decoder backed by the hardcoded INT_TO_CLASS
    map. Avoids needing label_encoder.joblib from Aegis.
    """
    def inverse_transform(self, indices) -> List[str]:
        return [INT_TO_CLASS.get(int(i), f"class_{i}") for i in indices]

    @property
    def classes_(self) -> List[str]:
        return [INT_TO_CLASS[i] for i in sorted(INT_TO_CLASS)]


# ── Preprocessor ──────────────────────────────────────────────────────────────

class NIDSPreprocessorBundle:
    """
    Implements the same interface as AutoMLOps' PreprocessorBundle so the existing
    serving_app.py and explainability.py work with no changes.

    Replicates Aegis ml/train.py preprocess() logic:
      1. Fill NaN / missing optional features with 0
      2. Cast boolean columns to int
      3. Cap periodicity_score at 100
      4. Return features in exact FEATURE_COLUMNS order

    Note on ja4_hash_enc / cipher_suite_enc: Aegis frequency-encodes these at
    training time (encoders.joblib). Since we don't run Aegis training, callers
    should pass already-encoded integers (or 0 = "rare/unknown" — the model
    handles this gracefully as it was trained with many unseen hashes mapped to 0).
    """

    def __init__(self):
        self.feature_names_out: List[str] = FEATURE_COLUMNS
        self.numerical_features: List[str] = FEATURE_COLUMNS
        self.categorical_features: List[str] = []

    def transform_single(self, input_dict: Dict[str, Any]) -> np.ndarray:
        row: Dict[str, float] = {}

        # Step 1 — fill zeros for optional feature groups
        for col in FILL_ZERO_COLUMNS:
            row[col] = float(input_dict.get(col, 0.0))

        # Step 2 — fill remaining features (default 0 if absent)
        for col in FEATURE_COLUMNS:
            if col not in row:
                row[col] = float(input_dict.get(col, 0.0))

        # Step 3 — cast booleans to int
        for col in BOOL_COLUMNS:
            row[col] = float(int(bool(row[col])))

        # Step 4 — cap periodicity_score
        row["periodicity_score"] = min(row["periodicity_score"], PERIODICITY_CAP)

        # Return as (1, 36) float64 array in exact model column order
        values = [row[col] for col in FEATURE_COLUMNS]
        return np.array(values, dtype=np.float64).reshape(1, -1)


# ── Bundle loader ──────────────────────────────────────────────────────────────

def load_aegis_bundle(aegis_ml_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Loads Aegis NIDS artifacts and wraps them in the AutoMLOps bundle format.

    Returns a dict with keys:
        model          — XGBClassifier (36 features, 7 threat classes)
        preprocessor   — NIDSPreprocessorBundle (AutoMLOps interface)
        framework      — "aegis_nids"
        label_encoder  — _DictLabelDecoder (maps int → threat class name)
        iso_bundle     — raw iso_forest.joblib dict {model, threshold, feature_columns, ...}
                         or None if iso_forest.joblib is missing

    Raises:
        FileNotFoundError if AEGIS_ML_DIR does not exist or model.joblib is absent.
    """
    import joblib

    ml_dir = Path(aegis_ml_dir or AEGIS_ML_DIR)

    if not ml_dir.exists():
        raise FileNotFoundError(
            f"Aegis ml directory not found at: {ml_dir}\n"
            f"Set the AEGIS_ML_DIR environment variable to the correct path, e.g.:\n"
            f"  set AEGIS_ML_DIR=C:\\Users\\ebint\\OneDrive\\Documents\\GitHub\\Aegis\\ml"
        )

    model_path = ml_dir / "model.joblib"
    iso_path   = ml_dir / "iso_forest.joblib"

    if not model_path.exists():
        raise FileNotFoundError(f"model.joblib not found in {ml_dir}")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        xgb_model = joblib.load(model_path)

    iso_bundle = None
    if iso_path.exists():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            iso_bundle = joblib.load(iso_path)
        logger.info(f"[AegisBridge] Isolation Forest loaded (threshold={iso_bundle.get('threshold', 'N/A'):.4f})")

    logger.info(
        f"[AegisBridge] XGBoost model loaded from {model_path} | "
        f"n_classes={xgb_model.n_classes_} | n_features={xgb_model.n_features_in_}"
    )

    return {
        "model":         xgb_model,
        "preprocessor":  NIDSPreprocessorBundle(),
        "framework":     "aegis_nids",
        "label_encoder": _DictLabelDecoder(),
        "iso_bundle":    iso_bundle,
        "aegis_ml_dir":  str(ml_dir),
    }


# ── NIDS inference helper ──────────────────────────────────────────────────────

def predict_nids(bundle: Dict[str, Any], input_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Runs the full Aegis two-stage inference:
      Stage 1 — Isolation Forest anomaly pre-filter
      Stage 2 — XGBoost multi-class threat classification

    Returns:
        {
          "threat_class":   str   — predicted class or "unknown_anomaly"
          "prediction":     str   — alias for threat_class (AutoMLOps compat)
          "confidence":     float — XGBoost max class probability
          "anomaly_score":  float — Isolation Forest score (higher = more anomalous)
          "is_anomaly":     bool  — True if Isolation Forest flagged the flow
          "top_features":   list  — placeholder (SHAP from explain_prediction)
          "evidence":       list  — human-readable threat signals
        }
    """
    preprocessor  = bundle["preprocessor"]
    model         = bundle["model"]
    label_decoder = bundle["label_encoder"]
    iso_bundle    = bundle.get("iso_bundle")

    X = preprocessor.transform_single(input_dict)

    # ── XGBoost classification ─────────────────────────────────────────────
    proba      = model.predict_proba(X)[0]
    pred_idx   = int(np.argmax(proba))
    confidence = float(np.max(proba))
    threat_class = label_decoder.inverse_transform([pred_idx])[0]

    if confidence < CONFIDENCE_THRESHOLD:
        threat_class = "unknown_anomaly"

    # ── Isolation Forest anomaly score ─────────────────────────────────────
    anomaly_score = 0.0
    is_anomaly    = False
    if iso_bundle is not None:
        try:
            iso_model  = iso_bundle["model"]
            threshold  = iso_bundle.get("threshold", 0.5)
            raw_score  = float(-iso_model.score_samples(X)[0])  # higher = more anomalous
            anomaly_score = raw_score
            is_anomaly    = raw_score > threshold
        except Exception as e:
            logger.warning(f"[AegisBridge] Isolation Forest scoring failed: {e}")

    # ── Human-readable evidence ────────────────────────────────────────────
    evidence = _build_threat_evidence(input_dict, threat_class)

    return {
        "threat_class":  threat_class,
        "prediction":    threat_class,
        "confidence":    round(confidence, 4),
        "anomaly_score": round(anomaly_score, 4),
        "is_anomaly":    is_anomaly,
        "top_features":  [],
        "evidence":      evidence,
    }


def _build_threat_evidence(features: Dict[str, Any], threat_class: str) -> List[str]:
    """Builds rule-based human-readable signals based on dominant features."""
    ev = []
    pps = float(features.get("packets_per_sec", 0))
    bps = float(features.get("bytes_per_sec", 0))
    ratio = float(features.get("outbound_inbound_ratio", 1))
    fan_out = float(features.get("fan_out", 0))
    iat_std = float(features.get("iat_std", 1))
    periodicity = float(features.get("periodicity_score", 0))
    dns_entropy = float(features.get("dns_query_entropy", 0))
    dst_ports = float(features.get("unique_dst_ports", 0))

    if threat_class == "ddos":
        if pps > 1000:
            ev.append(f"Extreme packet rate ({pps:.0f} pkt/s) — volumetric flood signature")
        if bps > 1e6:
            ev.append(f"High bandwidth ({bps/1e6:.1f} MB/s) — bandwidth exhaustion attack")

    elif threat_class == "c2_beaconing":
        if periodicity > 10:
            ev.append(f"High periodicity score ({periodicity:.1f}) — regular interval beaconing")
        if iat_std < 0.5:
            ev.append("Low IAT variance — machine-generated heartbeat timing")

    elif threat_class == "dns_anomaly":
        if dns_entropy > 3.5:
            ev.append(f"High DNS query entropy ({dns_entropy:.2f}) — DGA / tunnelling pattern")
        if float(features.get("dns_record_type_txt_ratio", 0)) > 0.3:
            ev.append("Elevated TXT record ratio — DNS exfiltration channel signature")

    elif threat_class == "port_scan":
        if dst_ports > 20:
            ev.append(f"High unique destination ports ({int(dst_ports)}) — port scanning activity")
        if fan_out > 50:
            ev.append(f"Wide fan-out ({fan_out:.0f}) — reconnaissance sweep")

    elif threat_class == "exfiltration":
        if ratio > 10:
            ev.append(f"Outbound/inbound byte ratio = {ratio:.1f} — asymmetric data exfiltration")

    elif threat_class == "malware_tls":
        ev.append("Encrypted session with suspicious JA4/cipher fingerprint")

    if not ev:
        ev.append(f"Classification: {threat_class} (confidence {0:.0%})")

    return ev
