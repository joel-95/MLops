"""
AutoMLOps Model Serving Micro-Server
=====================================
A lightweight FastAPI application that serves a single trained model.
One instance is spawned per connected repository on its deterministic port
(8000 + sequential_id). Also logs every prediction to the traffic store.

Start via subprocess:
    MODEL_PATH=artifacts/model.pkl PORT=8001 REPO_ID=repo_iris python -m uvicorn deploy.serving_app:app --host 0.0.0.0 --port 8001
"""
import os
import pickle
import logging
from typing import Dict, Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = logging.getLogger("automlops.serving")

# ─── Environment Config ────────────────────────────────────────────────────────
MODEL_PATH = os.environ.get("MODEL_PATH", "artifacts/model.pkl")
REPO_ID = os.environ.get("REPO_ID", "unknown_repo")
PORT = int(os.environ.get("PORT", "8001"))

# ─── App Factory ──────────────────────────────────────────────────────────────
app = FastAPI(
    title=f"AutoMLOps Model Server ({REPO_ID})",
    description="Lightweight inference endpoint for a deployed AutoMLOps model.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Model Loading ─────────────────────────────────────────────────────────────
_MODEL_BUNDLE: Optional[Dict[str, Any]] = None


def _load_model() -> Optional[Dict[str, Any]]:
    """Loads the pickled model bundle (model + preprocessor) from MODEL_PATH."""
    global _MODEL_BUNDLE
    if not os.path.exists(MODEL_PATH):
        logger.warning(f"[Serving] Model file not found at {MODEL_PATH}")
        return None
    try:
        with open(MODEL_PATH, "rb") as f:
            bundle = pickle.load(f)
        logger.info(f"[Serving] Model loaded from {MODEL_PATH}")
        return bundle
    except Exception as e:
        logger.error(f"[Serving] Failed to load model bundle: {e}")
        return None


@app.on_event("startup")
def on_startup():
    global _MODEL_BUNDLE
    _MODEL_BUNDLE = _load_model()
    logger.info(f"[Serving] Model server ready. repo={REPO_ID} port={PORT}")


# ─── Request / Response Schemas ────────────────────────────────────────────────
class PredictRequest(BaseModel):
    features: Dict[str, Any]


class PredictResponse(BaseModel):
    prediction: Any
    confidence: Optional[float] = None
    repo_id: str
    warning: Optional[str] = None
    error: Optional[str] = None


# ─── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    """Health check — confirms the serving process is alive."""
    return {
        "status": "healthy",
        "repo_id": REPO_ID,
        "model_loaded": _MODEL_BUNDLE is not None,
        "model_path": MODEL_PATH
    }


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    """
    Runs inference on the provided feature dictionary.
    Also logs the request to the traffic store for monitoring.
    """
    global _MODEL_BUNDLE

    # Lazy reload if model wasn't ready at startup
    if _MODEL_BUNDLE is None:
        _MODEL_BUNDLE = _load_model()

    input_dict = request.features
    output_dict: Dict[str, Any] = {}

    if _MODEL_BUNDLE is None:
        output_dict = {
            "prediction": None,
            "confidence": 0.0,
            "warning": f"Model not loaded from {MODEL_PATH}"
        }
    else:
        try:
            model = _MODEL_BUNDLE.get("model")
            preprocessor = _MODEL_BUNDLE.get("preprocessor")

            X_vec = preprocessor.transform_single(input_dict)
            pred = model.predict(X_vec)[0]

            # Convert numpy types to Python native
            if hasattr(pred, "item"):
                pred = pred.item()

            confidence = None
            if hasattr(model, "predict_proba"):
                proba = model.predict_proba(X_vec)[0]
                confidence = round(float(max(proba)), 4)

            output_dict = {
                "prediction": pred,
                "confidence": confidence
            }
        except Exception as e:
            output_dict = {
                "prediction": None,
                "confidence": 0.0,
                "error": f"Inference error: {str(e)}"
            }

    # Log to traffic store for monitoring
    try:
        from monitoring.traffic_logger import log_prediction
        log_prediction(REPO_ID, input_dict, output_dict)
    except Exception as log_err:
        logger.warning(f"[Serving] Traffic logging failed: {log_err}")

    return PredictResponse(
        prediction=output_dict.get("prediction"),
        confidence=output_dict.get("confidence"),
        repo_id=REPO_ID,
        warning=output_dict.get("warning"),
        error=output_dict.get("error")
    )


@app.get("/")
def index():
    return {
        "service": "AutoMLOps Model Server",
        "repo_id": REPO_ID,
        "endpoints": {
            "predict": "POST /predict",
            "health": "GET /health"
        }
    }


# ─── Direct entrypoint ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
