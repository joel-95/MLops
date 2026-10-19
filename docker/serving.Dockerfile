# docker/serving.Dockerfile
# Serving image wrapping a model's predict.py with FastAPI, traffic logging, and health endpoints

FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PORT=8000 \
    MODEL_PATH=/app/artifacts/model.pkl

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pandas \
    numpy \
    scikit-learn \
    joblib

# Serving application wrapper
COPY <<'EOF' /app/serving_app.py
import os
import sys
import importlib.util
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

app = FastAPI(title="AutoMLOps Model Serving Service")

PREDICT_FUNC = None
REPO_ID = os.getenv("REPO_ID", "default_repo")

@app.on_event("startup")
def load_predict_module():
    global PREDICT_FUNC
    predict_file = os.getenv("PREDICT_MODULE_PATH", "/app/ml/predict.py")
    if not os.path.exists(predict_file):
        predict_file = "/app/predict.py"
        
    if os.path.exists(predict_file):
        spec = importlib.util.spec_from_file_location("predict_module", predict_file)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["predict_module"] = mod
        spec.loader.exec_module(mod)
        if hasattr(mod, "predict"):
            PREDICT_FUNC = mod.predict
            print(f"Loaded predict() from {predict_file}")
        else:
            print(f"Module at {predict_file} does not expose a predict() function!")
    else:
        print(f"Predict module not found at {predict_file}. Running in stub mode.")

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "repo_id": REPO_ID,
        "model_loaded": PREDICT_FUNC is not None
    }

@app.post("/predict")
def predict_endpoint(payload: Dict[str, Any]):
    if PREDICT_FUNC is None:
        raise HTTPException(status_code=503, detail="Prediction function not loaded")
    try:
        result = PREDICT_FUNC(payload)
        
        # Local traffic logging hook
        try:
            from monitoring.traffic_logger import log_prediction
            log_prediction(REPO_ID, payload, result)
        except Exception:
            pass
            
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")

EOF

EXPOSE 8000

CMD ["sh", "-c", "uvicorn serving_app:app --host 0.0.0.0 --port ${PORT:-8000}"]
