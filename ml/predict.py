import os
import pickle
from typing import Dict, Any, Optional

MODEL_BUNDLE = None
MODEL_PATH = os.getenv("MODEL_PATH", "artifacts/model.pkl")


def load_model():
    global MODEL_BUNDLE
    if os.path.exists(MODEL_PATH):
        try:
            with open(MODEL_PATH, "rb") as f:
                MODEL_BUNDLE = pickle.load(f)
        except Exception as e:
            print(f"Failed to load model bundle from {MODEL_PATH}: {e}")


# Load once at import time
load_model()


def predict(input_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Standardized inference contract (Section 2.4).
    
    Args:
        input_dict: Dictionary mapping feature names to values.
            e.g.: {"sepal_length": 5.1, "sepal_width": 3.5, "petal_length": 1.4, "petal_width": 0.2}

    Returns:
        Dict with keys:
            - 'prediction': Predicted class label or numerical value
            - 'confidence': Probability score (0.0 - 1.0) or None for regression
    """
    global MODEL_BUNDLE
    if MODEL_BUNDLE is None:
        load_model()

    if MODEL_BUNDLE is None:
        # Fallback heuristic prediction if no model file trained yet
        return {
            "prediction": 0,
            "confidence": 0.5,
            "warning": "Model artifact not loaded. Default heuristic prediction used."
        }

    model = MODEL_BUNDLE.get("model")
    preprocessor = MODEL_BUNDLE.get("preprocessor")

    try:
        # Apply fitted preprocessing bundle
        X_vec = preprocessor.transform_single(input_dict)
        pred = model.predict(X_vec)[0]

        confidence = None
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(X_vec)[0]
            confidence = round(float(max(proba)), 4)

        return {
            "prediction": int(pred) if hasattr(pred, "item") and isinstance(pred.item(), int) else pred,
            "confidence": confidence
        }
    except Exception as e:
        return {
            "prediction": None,
            "confidence": 0.0,
            "error": f"Inference processing error: {str(e)}"
        }
