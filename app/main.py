"""
app/main.py -- EloCoach FastAPI backend

Endpoints:
    GET  /health    -> model status + training metadata
    POST /analyze   -> upload .aoe2record -> JSON coaching report

Usage:
    uvicorn app.main:app --reload --port 8000

From project root. Model loads once at startup.
"""

import tempfile
import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.model import load_artifacts, run_pipeline

# -- Logging ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)s  %(message)s',
)
log = logging.getLogger(__name__)

# -- Model directory ----------------------------------------------------------
# Resolve relative to this file so the app works from any cwd
_APP_DIR    = Path(__file__).parent
_MODEL_DIR  = _APP_DIR.parent / 'models'
_STATIC_DIR = _APP_DIR / 'static'
_SAMPLE_DIR = _APP_DIR.parent / 'data' / 'sample_replays'
_DEMO_PROFILE_ID = 3134896  # Hercules's AoE2 profile ID

# -- App state (populated at startup) -----------------------------------------
_state: dict = {
    'model':         None,
    'distributions': None,
    'ready':         False,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model artifacts once at startup, release on shutdown."""
    log.info('Loading model artifacts from %s ...', _MODEL_DIR)
    try:
        model, distributions = load_artifacts(_MODEL_DIR)
        _state['model']         = model
        _state['distributions'] = distributions
        _state['ready']         = True
        log.info(
            'Model ready -- %s  AUC=%.3f  Elo range %s-%s',
            distributions.get('winning_model', '?'),
            distributions.get('winning_auc', 0),
            int(distributions['elo_range'][0]),
            int(distributions['elo_range'][1]),
        )
    except Exception as e:
        log.error('Failed to load model: %s', e)
        # App starts but /analyze will return 503
    yield
    log.info('Shutting down.')


app = FastAPI(
    title='EloCoach API',
    description='Upload an AoE2 DE replay and get personalized coaching based on your in-game decisions.',
    version='1.0.0',
    lifespan=lifespan,
)


# -- Health check -------------------------------------------------------------
@app.get('/health', summary='Model status and training metadata')
def health():
    """
    Returns model readiness and training metadata.
    Use this to confirm the server is up and the model loaded successfully.
    """
    if not _state['ready']:
        return JSONResponse(
            status_code=503,
            content={'status': 'unavailable', 'error': 'Model not loaded'},
        )

    dist = _state['distributions']
    return {
        'status':        'ok',
        'model_loaded':  True,
        'winning_model': dist.get('winning_model'),
        'winning_auc':   dist.get('winning_auc'),
        'elo_range':     dist.get('elo_range'),
        'elo_median':    dist.get('elo_median'),
        'feature_count': len(dist.get('feature_cols', [])),
    }


# -- Analyze endpoint ---------------------------------------------------------
@app.post('/analyze', summary='Upload a replay and get coaching')
async def analyze(
    file: UploadFile = File(..., description='.aoe2record replay file'),
    profile_id: Optional[int] = Query(
        default=None,
        description=(
            'Your AoE2 profile ID (e.g. 3134896). '
            'If omitted, defaults to the project owner profile ID. '
            'Used to identify which player to coach in the replay.'
        ),
    ),
    top_n: int = Query(
        default=5,
        ge=1,
        le=10,
        description='Number of coaching recommendations to return (1-10)',
    ),
):
    """
    Upload an .aoe2record file and receive a personalized coaching report.

    Response fields:
    - win_probability -- model predicted win probability for you (0-1)
    - actual_result   -- 1 if you won, 0 if you lost, null if unknown
    - recommendations -- top N coaching items ranked by priority
    - my_elo / opp_elo -- pre-game ratings from the replay POSTGAME block
    - duration_min    -- game length in minutes
    - warnings        -- non-fatal issues (e.g. non-Arabia map)

    Recommendation fields:
    - rank        -- 1 = highest priority
    - feature     -- what was measured (e.g. feudal_min)
    - percentile  -- your delta vs opponent, ranked against training data (10-90)
    - value       -- your raw delta (me minus opponent)
    - direction   -- negative = lower is better (timing), positive = higher is better (counts)
    - message     -- plain-English coaching advice
    - priority    -- SHAP importance x weakness score (for sorting)
    """
    # Guard: model must be loaded
    if not _state['ready']:
        raise HTTPException(
            status_code=503,
            detail='Model not loaded -- check /health for details',
        )

    # Guard: file type
    filename = file.filename or ''
    if not filename.lower().endswith('.aoe2record'):
        raise HTTPException(
            status_code=400,
            detail=f'Expected a .aoe2record file, got: "{filename}"',
        )

    # Save upload to temp file
    # mgz reads binary content -- the extension does not matter for parsing,
    # but keeping it makes debugging easier if the temp file leaks.
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix='.aoe2record',
            delete=False,
        ) as tmp:
            tmp_path = tmp.name
            content  = await file.read()
            tmp.write(content)

        log.info(
            'Analyzing %s  (%d bytes)  profile_id=%s',
            filename, len(content), profile_id,
        )

        # Run pipeline
        result = run_pipeline(
            filepath=tmp_path,
            model=_state['model'],
            distributions=_state['distributions'],
            profile_id=profile_id,
            top_n=top_n,
        )

        # Surface pipeline errors as HTTP 422
        if result.get('status') == 'error':
            log.warning('Pipeline error for %s: %s', filename, result.get('error'))
            raise HTTPException(
                status_code=422,
                detail={
                    'message': 'Failed to parse or process replay',
                    'error':   result.get('error'),
                    'file':    filename,
                },
            )

        # Swap filepath back to original filename (do not leak temp path)
        result['filename'] = filename
        result.pop('filepath', None)

        log.info(
            'Done -- win_prob=%.3f  actual=%s  recs=%d',
            result.get('win_probability', 0),
            result.get('actual_result'),
            len(result.get('recommendations', [])),
        )
        return result

    finally:
        # Always clean up the temp file
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# -- Demo endpoint ------------------------------------------------------------
@app.get('/demo', summary='Run the bundled sample replay and return coaching')
def demo(
    top_n: int = Query(
        default=5,
        ge=1,
        le=10,
        description='Number of coaching recommendations to return (1-10)',
    ),
):
    """
    Runs the bundled sample replay (Hercules's game) through the full pipeline
    and returns a coaching report. Useful for visitors without a replay file.
    """
    if not _state['ready']:
        raise HTTPException(
            status_code=503,
            detail='Model not loaded -- check /health for details',
        )

    # Find the first .aoe2record in the sample dir
    sample_files = list(_SAMPLE_DIR.glob('*.aoe2record'))
    if not sample_files:
        raise HTTPException(
            status_code=500,
            detail='No sample replay found on server.',
        )
    sample_path = sample_files[0]

    log.info('Demo request -- using %s  profile_id=%s', sample_path.name, _DEMO_PROFILE_ID)

    result = run_pipeline(
        filepath=str(sample_path),
        model=_state['model'],
        distributions=_state['distributions'],
        profile_id=_DEMO_PROFILE_ID,
        top_n=top_n,
    )

    if result.get('status') == 'error':
        raise HTTPException(
            status_code=422,
            detail={
                'message': 'Failed to process demo replay',
                'error':   result.get('error'),
            },
        )

    result['filename'] = sample_path.name
    result['is_demo'] = True
    result.pop('filepath', None)
    return result


# -- Static frontend ----------------------------------------------------------
# Mounted LAST so /health and /analyze are matched by the router first.
# html=True makes GET / serve index.html automatically.
app.mount('/', StaticFiles(directory=_STATIC_DIR, html=True), name='static')
