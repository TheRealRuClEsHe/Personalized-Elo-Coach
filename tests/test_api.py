"""
Tests for the HTTP surface.

The client fixture runs the app's lifespan, so these exercise the same
startup path production uses.
"""

from __future__ import annotations

import pytest

from conftest import SAMPLE_COACHED_PROFILE_ID


# ── /health ──────────────────────────────────────────────────────────────────

def test_health_reports_a_loaded_model(client):
    body = client.get('/health').json()
    assert body['status'] == 'ok'
    assert body['model_loaded'] is True


def test_health_exposes_training_metadata(client, distributions):
    body = client.get('/health').json()
    assert body['winning_model']
    assert body['winning_auc'] > 0.5
    assert body['feature_count'] == len(distributions['feature_cols'])
    assert len(body['elo_range']) == 2


# ── /analyze rejections ──────────────────────────────────────────────────────

def test_rejects_a_file_that_is_not_a_replay(client):
    response = client.post(
        '/analyze',
        files={'file': ('replay.mp4', b'not a replay', 'application/octet-stream')},
    )
    assert response.status_code == 400
    assert 'replay.mp4' in str(response.json()['detail'])


def test_unparseable_replay_returns_a_structured_error(client):
    response = client.post(
        '/analyze',
        files={'file': ('bad.aoe2record', b'\x00\x01\x02\x03garbage', 'application/octet-stream')},
    )
    assert response.status_code == 422
    detail = response.json()['detail']
    assert 'message' in detail
    assert 'error' in detail


@pytest.mark.parametrize('top_n', [0, 11, 99])
def test_rejects_out_of_range_recommendation_counts(client, top_n):
    response = client.post(
        f'/analyze?top_n={top_n}',
        files={'file': ('x.aoe2record', b'x', 'application/octet-stream')},
    )
    assert response.status_code == 422


def test_profile_id_is_accepted_and_reaches_the_parse_stage(client):
    """A valid profile_id must not itself be a validation failure."""
    response = client.post(
        f'/analyze?profile_id={SAMPLE_COACHED_PROFILE_ID}',
        files={'file': ('test.aoe2record', b'garbage', 'application/octet-stream')},
    )
    assert response.status_code == 422
    assert 'message' in response.json()['detail']


# ── /analyze round trip ──────────────────────────────────────────────────────

@pytest.fixture(scope='session')
def analysis(client, sample_replay):
    response = client.post(
        f'/analyze?profile_id={SAMPLE_COACHED_PROFILE_ID}&top_n=5',
        files={'file': (sample_replay.name, sample_replay.read_bytes(), 'application/octet-stream')},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_analysis_returns_a_win_probability(analysis):
    assert analysis['status'] == 'ok'
    assert 0.0 <= analysis['win_probability'] <= 1.0


def test_analysis_returns_the_requested_recommendations(analysis):
    assert 0 < len(analysis['recommendations']) <= 5
    first = analysis['recommendations'][0]
    assert {'rank', 'feature', 'percentile', 'message'} <= set(first)
    assert first['rank'] == 1


def test_analysis_names_both_players(analysis):
    assert len(analysis['players']) == 2
    assert analysis['players'][0]['profile_id'] == SAMPLE_COACHED_PROFILE_ID


def test_analysis_does_not_leak_the_server_temp_path(analysis, sample_replay):
    """The client uploaded a name; it must not learn where the server put it."""
    assert 'filepath' not in analysis
    assert analysis['filename'] == sample_replay.name
