# -*- coding: utf-8 -*-
"""model_registry.py
Simple registry for forecast models used in Phase 3.
Provides a mapping of model names to versions and descriptions.
"""

MODEL_REGISTRY = {
    "naive": {
        "version": "1.0.0",
        "description": "Naive last‑value baseline model",
    },
    "holt_winters": {
        "version": "1.0.0",
        "description": "Exponential Smoothing (additive trend, no seasonality)",
    },
}

def get_model_info(name: str):
    """Return model metadata dict for *name* or raise KeyError."""
    if name not in MODEL_REGISTRY:
        raise KeyError(f"Model '{name}' not found in registry.")
    return MODEL_REGISTRY[name]
