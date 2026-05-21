"""
tests/test_src_pipeline.py

Smoke tests for src/ modules. Run from the project root:
    python -m pytest tests/test_src_pipeline.py -v
or without pytest:
    python tests/test_src_pipeline.py

Tests that do NOT require a real .aoe2record file:
    - Module imports
    - Feature column alignment (MODEL_FEATURE_COLS vs cohort_distributions.pkl)
    - Feature engineering logic (build_delta_row via mock game dict)
    - Percentile ranking logic
    - Recommendation ranking
    - Model inference via features_delta.csv

Tests that DO require a real replay (skipped if no file found):
    - parse_header()
    - parse_replay() + build_delta_row() end-to-end
    - run_pipeline() full round-trip
"""

import sys
import math
import pickle
from pathlib import Path

import pandas as pd
import numpy as np

# Run from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

REPO      = Path(__file__).parent.parent
MODEL_DIR = REPO / 'models'
DATA_DIR  = REPO / 'data'

PASS = '✓'
FAIL = '✗'

errors = []


def check(label, condition, detail=''):
    if condition:
        print(f'  {PASS}  {label}')
    else:
        print(f'  {FAIL}  {label}  {detail}')
        errors.append(label)


# ── 1. Imports ────────────────────────────────────────────────────────────────
print('\n[1] Module imports')
try:
    from src.parser import (
        parse_header, parse_replay, flatten_player_row,
        TRACKED_TECHS, TRACKED_BUILDINGS, BUILDING_COUNT_MAP,
        WALL_IDS, MARKET_IDS, VILLAGER_ID, MY_PROFILE_ID,
        ARABIA_MAP_ID, RM_1V1_LEADERBOARD_ID, MIN_DURATION_MIN,
    )
    check('src.parser', True)
except Exception as e:
    check('src.parser', False, str(e))

try:
    from src.features import build_delta_row, MODEL_FEATURE_COLS, extract_player_features
    check('src.features', True)
except Exception as e:
    check('src.features', False, str(e))

try:
    from src.coaching import (
        compute_percentile_rank, get_user_profile,
        rank_recommendations, COACHING_MESSAGES,
    )
    check('src.coaching', True)
except Exception as e:
    check('src.coaching', False, str(e))

try:
    from src.model import load_artifacts, predict_win_prob, run_pipeline
    check('src.model', True)
except Exception as e:
    check('src.model', False, str(e))


# ── 2. Constants sanity ───────────────────────────────────────────────────────
print('\n[2] Constants')
check('MODEL_FEATURE_COLS has 70 entries', len(MODEL_FEATURE_COLS) == 70,
      f'got {len(MODEL_FEATURE_COLS)}')
check('all MODEL_FEATURE_COLS end in _delta',
      all(c.endswith('_delta') for c in MODEL_FEATURE_COLS))
check('TRACKED_TECHS has 41 entries', len(TRACKED_TECHS) == 41,
      f'got {len(TRACKED_TECHS)}')
check('TRACKED_BUILDINGS has 4 entries', len(TRACKED_BUILDINGS) == 4)
check('MY_PROFILE_ID is correct', MY_PROFILE_ID == 3134896)


# ── 3. Feature alignment vs cohort_distributions.pkl ─────────────────────────
print('\n[3] Feature alignment vs cohort_distributions.pkl')
try:
    _, dist = load_artifacts(MODEL_DIR)
    dist_cols = dist['feature_cols']
    missing   = set(MODEL_FEATURE_COLS) - set(dist_cols)
    extra     = set(dist_cols) - set(MODEL_FEATURE_COLS)
    check('MODEL_FEATURE_COLS matches dist[feature_cols]',
          not missing and not extra,
          f'missing={missing}  extra={extra}')
    # Note: 4 techs are all-null in training data (never researched) so they have
    # no percentile breakpoints. NB05 explicitly skips them. Expected: 66 of 70.
    check('dist has percentiles for most features (>=60)',
          len(dist['percentiles']) >= 60,
          f'{len(dist["percentiles"])} vs {len(dist_cols)}')
except Exception as e:
    check('load_artifacts', False, str(e))


# ── 4. build_delta_row() via mock game dict ───────────────────────────────────
print('\n[4] build_delta_row() with mock game')

from collections import defaultdict

def _mock_stats(feudal=10.5, castle=18.0, vills=22, result=1, elo=1750):
    s = {
        'villagers_dark_age': vills, 'villagers_feudal_age': vills,
        'villagers_castle_age': 0, 'villagers_imperial_age': 0,
        'mil_trained_dark_age': 0, 'mil_trained_feudal_age': 2,
        'mil_trained_castle_age': 0, 'mil_trained_imperial_age': 0,
        'apm_dark_age': 100, 'apm_feudal_age': 150,
        'apm_castle_age': 0, 'apm_imperial_age': 0,
        'gather_point_count': 10, 'wall_count': 0,
        'move_count': 80, 'order_count': 30, 'stance_count': 5, 'ungarrison_count': 0,
        'first_wall_min': None, 'resign_time_min': None, 'resigned': False,
        'market_min': None, 'market_count': 0,
        'feudal_min': feudal, 'castle_min': castle, 'imperial_min': None,
        'result': result, 'elo': elo,
        'thresholds': {'feudal_complete': feudal + 2.16,
                       'castle_complete': castle + 2.66,
                       'imperial_complete': float('inf')},
        'military_buildings_placed': defaultdict(int, {12: 1}),
    }
    # fill all TRACKED_TECHS and TRACKED_BUILDINGS with None
    for col in list(TRACKED_TECHS.values()) + list(TRACKED_BUILDINGS.values()):
        if col not in s:
            s[col] = None
    s['feudal_min'] = feudal
    s['castle_min'] = castle
    return s

mock_game = {
    'filepath': 'mock.aoe2record',
    'map_id': ARABIA_MAP_ID,
    'rated': True,
    'num_players': 2,
    'duration_min': 25.0,
    'de_players': {
        1: {'profile_id': MY_PROFILE_ID, 'name': 'TheRealRuClEsHe', 'civilization_id': 18},
        2: {'profile_id': 9999999,        'name': 'Opponent',         'civilization_id': 5},
    },
    'player_stats': {
        1: _mock_stats(feudal=10.5, castle=18.0, vills=22, result=1, elo=1750),
        2: _mock_stats(feudal=11.0, castle=19.0, vills=20, result=0, elo=1780),
    },
}

try:
    delta, meta = build_delta_row(mock_game, profile_id=MY_PROFILE_ID)
    check('build_delta_row returns 70 cols', len(delta) == 70, f'got {len(delta)}')
    check('feudal_min_delta correct',
          abs(delta['feudal_min_delta'] - (10.5 - 11.0)) < 1e-9,
          f'got {delta["feudal_min_delta"]}')
    check('villagers_dark_age_delta correct',
          delta['villagers_dark_age_delta'] == 2,  # 22 - 20
          f'got {delta["villagers_dark_age_delta"]}')
    check('market_min_delta is None (neither player built market)',
          delta['market_min_delta'] is None)
    check('meta my_player_num is 1', meta['my_player_num'] == 1)
    check('meta my_result is 1 (win)', meta['my_result'] == 1)
    check('meta my_elo is 1750', meta['my_elo'] == 1750)
except Exception as e:
    check('build_delta_row', False, str(e))


# ── 5. Percentile ranking ─────────────────────────────────────────────────────
print('\n[5] Percentile ranking')
try:
    model, dist = load_artifacts(MODEL_DIR)

    # feudal_min_delta: clamp to 10th pct
    val = dist['percentiles']['feudal_min_delta'][10] - 1.0
    pct = compute_percentile_rank(val, 'feudal_min_delta', dist)
    check('value below 10th pct → returns 10.0', pct == 10.0, f'got {pct}')

    # None input → None output
    pct_none = compute_percentile_rank(None, 'feudal_min_delta', dist)
    check('None value → None percentile', pct_none is None)

    # Median-ish value → ~50th pct
    val50 = dist['percentiles']['feudal_min_delta'][50]
    pct50 = compute_percentile_rank(val50, 'feudal_min_delta', dist)
    check('median value → ~50th pct', 45 < pct50 < 55, f'got {pct50}')
except Exception as e:
    check('percentile ranking', False, str(e))


# ── 6. Recommendations ────────────────────────────────────────────────────────
print('\n[6] Recommendation ranking')
try:
    delta_dict = {col: delta.get(col) for col in MODEL_FEATURE_COLS}
    profile    = get_user_profile(delta_dict, dist)
    shap_imp   = {col: 1.0 / len(MODEL_FEATURE_COLS) for col in MODEL_FEATURE_COLS}
    recs       = rank_recommendations(profile, shap_imp, top_n=5)

    check('returns 5 recommendations', len(recs) == 5, f'got {len(recs)}')
    check('ranks are 1–5', [r['rank'] for r in recs] == [1, 2, 3, 4, 5])
    check('sorted by priority descending',
          all(recs[i]['priority'] >= recs[i+1]['priority'] for i in range(len(recs)-1)))
    check('each rec has required keys',
          all({'feature','feature_col','value','percentile','priority','direction','message'}.issubset(r) for r in recs))
except Exception as e:
    check('recommendations', False, str(e))


# ── 7. Model inference via features_delta.csv ─────────────────────────────────
print('\n[7] Model inference (features_delta.csv)')
try:
    df = pd.read_csv(DATA_DIR / 'features_delta.csv')

    probs, actuals = [], []
    for _, row in df.iterrows():
        d   = {col: row.get(col) for col in MODEL_FEATURE_COLS}
        probs.append(predict_win_prob(model, d, dist['feature_cols']))
        actuals.append(int(row['result']))

    probs   = np.array(probs)
    actuals = np.array(actuals)
    acc     = (probs >= 0.5).astype(int)
    acc     = (acc == actuals).mean()

    check(f'inference on {len(df)} rows without error', True)
    check('all probs in [0, 1]', probs.min() >= 0 and probs.max() <= 1)
    check('mean win prob (wins) > mean win prob (losses)',
          probs[actuals == 1].mean() > probs[actuals == 0].mean())
    check('accuracy > 0.70', acc > 0.70, f'got {acc:.3f}')
except Exception as e:
    check('model inference', False, str(e))


# ── 8. Real replay test (skipped if no files found) ──────────────────────────
print('\n[8] Real replay parse (requires mounted replay directory)')
replay_dirs = [
    Path('C:/Users/liher/Games/Age of Empires 2 DE/76561198151543542/savegame'),
    REPO / 'data' / 'sample_replays',
    REPO / 'data' / 'bulk_replays',
]
replay_file = None
for d in replay_dirs:
    if d.exists():
        files = list(d.glob('*.aoe2record'))
        if files:
            replay_file = files[0]
            break

if replay_file is None:
    print('  -  No .aoe2record files found — skipping live parse test')
else:
    print(f'  Using: {replay_file.name}')
    try:
        from src.parser import parse_header, parse_replay
        map_id, rated, nplayers = parse_header(replay_file)
        check(f'parse_header returns tuple', isinstance(map_id, (int, type(None))))

        game = parse_replay(replay_file)
        check('parse_replay returns dict with expected keys',
              {'filepath','map_id','duration_min','player_stats','de_players'}.issubset(game))
        check('2 players parsed', len(game['player_stats']) == 2)

        result = run_pipeline(str(replay_file), model, dist, profile_id=MY_PROFILE_ID)
        check('run_pipeline status=ok', result['status'] == 'ok', result.get('error'))
        check('recommendations returned',
              isinstance(result.get('recommendations'), list) and len(result['recommendations']) > 0)
        check('win_probability in [0,1]',
              0.0 <= result.get('win_probability', -1) <= 1.0)
        print(f'     win_prob={result["win_probability"]:.3f}  actual={result["actual_result"]}')
    except Exception as e:
        check('live replay pipeline', False, str(e))


# ── Summary ───────────────────────────────────────────────────────────────────
print()
if errors:
    print(f'FAILED — {len(errors)} test(s): {errors}')
    sys.exit(1)
else:
    print('ALL TESTS PASSED')
