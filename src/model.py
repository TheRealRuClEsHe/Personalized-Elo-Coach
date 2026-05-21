"""
src/model.py -- Model loading, inference, and end-to-end pipeline

Provides:
    load_artifacts(model_dir)         -> (model, distributions)
    predict_win_prob(model, delta_dict, feature_cols) -> float
    run_pipeline(filepath, model, distributions, profile_id) -> dict
"""

from __future__ import annotations

import logging
import pickle
import traceback
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

from src.parser import parse_replay, ARABIA_MAP_ID, MIN_DURATION_MIN
from src.features import build_delta_row, MODEL_FEATURE_COLS
from src.coaching import get_user_profile, rank_recommendations


def load_artifacts(model_dir):
    """Load model and cohort distributions. Returns (model, distributions)."""
    model_dir = Path(model_dir)
    with open(model_dir / 'elocoach_model.pkl', 'rb') as f:
        model = pickle.load(f)
    with open(model_dir / 'cohort_distributions.pkl', 'rb') as f:
        distributions = pickle.load(f)
    return model, distributions


def predict_win_prob(model, delta_dict, feature_cols):
    """
    Run model inference on a single delta feature dict.

    Python None values (tech never researched) are converted to float('nan')
    before building the DataFrame so XGBoost receives float64 columns only.
    XGBoost handles NaN natively (DEC-008).
    """
    estimator = getattr(model, 'best_estimator_', model)

    _nan = float('nan')
    row = {
        col: (float(delta_dict[col]) if delta_dict.get(col) is not None else _nan)
        for col in feature_cols
    }
    X = pd.DataFrame([row])[feature_cols]

    proba = estimator.predict_proba(X)[0]
    return float(proba[1])  # class 1 = win


def _compute_global_shap(model, distributions):
    """
    Return per-feature gain importance (normalized) as a SHAP proxy.
    Falls back to uniform if the booster cannot be reached.
    """
    feature_cols = distributions['feature_cols']
    estimator    = getattr(model, 'best_estimator_', model)

    try:
        importances = estimator.get_booster().get_score(importance_type='gain')
        total = sum(importances.values()) or 1.0
        result = {}
        for i, col in enumerate(feature_cols):
            result[col] = importances.get(col, importances.get(f'f{i}', 0.0)) / total
        return result
    except Exception:
        n = len(feature_cols)
        return {col: 1.0 / n for col in feature_cols}


def run_pipeline(filepath, model, distributions, profile_id=None, top_n=5):
    """
    End-to-end: parse -> features -> predict -> coaching.

    Returns a JSON-ready dict with win_probability, recommendations, and metadata.
    On any error returns {'status': 'error', 'error': <message>}.
    """
    try:
        game = parse_replay(filepath)

        warnings_list = []
        if game['map_id'] != ARABIA_MAP_ID:
            warnings_list.append(
                f"Map ID {game['map_id']} is not Arabia (9) -- model trained on Arabia only"
            )
        if game['duration_min'] < MIN_DURATION_MIN:
            warnings_list.append(
                f"Game is only {game['duration_min']:.1f} min "
                f"-- below {MIN_DURATION_MIN} min threshold"
            )

        delta_dict, meta = build_delta_row(game, profile_id=profile_id)

        feature_cols    = distributions['feature_cols']
        win_prob        = predict_win_prob(model, delta_dict, feature_cols)
        user_profile    = get_user_profile(delta_dict, distributions)
        shap_importance = _compute_global_shap(model, distributions)
        recommendations = rank_recommendations(user_profile, shap_importance, top_n=top_n)

        return {
            'status':          'ok',
            'error':           None,
            'warnings':        warnings_list,
            'filepath':        game['filepath'],
            'duration_min':    game['duration_min'],
            'my_elo':          meta['my_elo'],
            'opp_elo':         meta['opp_elo'],
            'my_civ':          meta['my_civ'],
            'opp_civ':         meta['opp_civ'],
            'win_probability': round(win_prob, 4),
            'actual_result':   meta['my_result'],
            'recommendations': recommendations,
            'elo_context': {
                'training_elo_range':  distributions.get('elo_range'),
                'training_elo_median': distributions.get('elo_median'),
                'winning_model':       distributions.get('winning_model'),
                'winning_auc':         distributions.get('winning_auc'),
            },
        }

    except Exception as e:
        log.error('run_pipeline failed for %s:\n%s', filepath, traceback.format_exc())
        return {
            'status':   'error',
            'error':    f"{type(e).__name__}: {e}",
            'filepath': str(filepath),
        }
