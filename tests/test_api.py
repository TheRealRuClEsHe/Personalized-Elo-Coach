"""
tests/test_api.py

API integration tests. Run from project root:
    python -m pytest tests/test_api.py -v
or:
    python tests/test_api.py

Tests that do NOT require a real replay:
    - /health endpoint
    - /analyze — wrong file extension → 400
    - /analyze — garbage binary → 422 (parse error surfaces cleanly)
    - /analyze — top_n out of range → 422 (FastAPI validation)
    - /analyze — profile_id passed through query param

Tests that DO require a real replay (skipped if none found):
    - Full round-trip: upload → parse → predict → recommendations
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from app.main import app

REPO = Path(__file__).parent.parent

PASS = '✓'
FAIL = '✗'
errors = []


def check(label, condition, detail=''):
    if condition:
        print(f'  {PASS}  {label}')
    else:
        print(f'  {FAIL}  {label}  {detail}')
        errors.append(label)


with TestClient(app) as client:

    # ── /health ───────────────────────────────────────────────────────────────
    print('\n[1] GET /health')
    r = client.get('/health')
    check('status 200', r.status_code == 200, str(r.status_code))
    data = r.json()
    check('status=ok', data.get('status') == 'ok')
    check('model_loaded=True', data.get('model_loaded') is True)
    check('winning_model present', bool(data.get('winning_model')))
    check('winning_auc > 0.5', (data.get('winning_auc') or 0) > 0.5)
    check('feature_count=70', data.get('feature_count') == 70, str(data.get('feature_count')))
    check('elo_range is list of 2', isinstance(data.get('elo_range'), list) and len(data['elo_range']) == 2)

    # ── /analyze — bad file extension ────────────────────────────────────────
    print('\n[2] POST /analyze — wrong extension')
    r = client.post('/analyze',
        files={'file': ('replay.mp4', b'notathing', 'application/octet-stream')})
    check('status 400', r.status_code == 400, str(r.status_code))
    check('detail mentions filename', 'replay.mp4' in str(r.json().get('detail', '')))

    # ── /analyze — correct extension, garbage content ─────────────────────────
    print('\n[3] POST /analyze — .aoe2record, garbage binary')
    r = client.post('/analyze',
        files={'file': ('bad.aoe2record', b'\x00\x01\x02\x03garbage', 'application/octet-stream')})
    check('status 422', r.status_code == 422, str(r.status_code))
    detail = r.json().get('detail', {})
    check('detail has message key', isinstance(detail, dict) and 'message' in detail)
    check('detail has error key', isinstance(detail, dict) and 'error' in detail)

    # ── /analyze — top_n out of range ────────────────────────────────────────
    print('\n[4] POST /analyze — top_n=99 (out of range)')
    r = client.post('/analyze?top_n=99',
        files={'file': ('x.aoe2record', b'x', 'application/octet-stream')})
    check('status 422 (FastAPI validation)', r.status_code == 422, str(r.status_code))

    print('\n[5] POST /analyze — top_n=0 (out of range)')
    r = client.post('/analyze?top_n=0',
        files={'file': ('x.aoe2record', b'x', 'application/octet-stream')})
    check('status 422 (FastAPI validation)', r.status_code == 422, str(r.status_code))

    # ── /analyze — profile_id query param parses correctly ───────────────────
    print('\n[6] POST /analyze — profile_id query param')
    # Garbage binary → 422, but the 400 for bad extension takes priority if wrong ext
    # So use correct ext to confirm profile_id is parsed before the file error
    r = client.post('/analyze?profile_id=3134896',
        files={'file': ('test.aoe2record', b'garbage', 'application/octet-stream')})
    # Should fail at parse (422), not at profile_id validation
    check('profile_id accepted (reaches parse stage)', r.status_code == 422, str(r.status_code))

    # ── Real replay round-trip (skipped if no replay found) ──────────────────
    print('\n[7] POST /analyze — real replay (requires .aoe2record file)')
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
        print('  -  No .aoe2record files found — skipping live replay test')
    else:
        print(f'  Using: {replay_file.name}')
        with open(replay_file, 'rb') as fh:
            content = fh.read()

        r = client.post(
            '/analyze?profile_id=3134896&top_n=5',
            files={'file': (replay_file.name, content, 'application/octet-stream')},
        )
        check('status 200', r.status_code == 200, str(r.status_code))
        if r.status_code == 200:
            data = r.json()
            check('status=ok', data.get('status') == 'ok')
            check('win_probability in [0,1]',
                  0.0 <= data.get('win_probability', -1) <= 1.0)
            check('recommendations is list',
                  isinstance(data.get('recommendations'), list))
            check('up to 5 recommendations',
                  0 < len(data.get('recommendations', [])) <= 5)
            check('duration_min > 0', (data.get('duration_min') or 0) > 0)
            check('no filepath leaked', 'filepath' not in data)
            check('filename present', bool(data.get('filename')))

            recs = data['recommendations']
            if recs:
                first = recs[0]
                check('rec has rank/feature/percentile/message',
                      all(k in first for k in ('rank', 'feature', 'percentile', 'message')))

            print(f'     win_prob={data["win_probability"]}  actual={data["actual_result"]}')
            print(f'     top rec: {recs[0]["feature"] if recs else "none"}')


# ── Summary ───────────────────────────────────────────────────────────────────
print()
if errors:
    print(f'FAILED — {len(errors)} test(s): {errors}')
    import sys; sys.exit(1)
else:
    print('ALL TESTS PASSED')
