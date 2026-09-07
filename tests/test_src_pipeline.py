"""
Tests for the analysis pipeline: delta features, percentile ranking, and
coaching recommendations.

Every delta is oriented coached player minus opponent (see CONTEXT.md).
"""

from __future__ import annotations

import pytest

from src.features import build_delta_row, MODEL_FEATURE_COLS
from src.coaching import (
    compute_percentile_rank,
    get_user_profile,
    rank_recommendations,
)
from src.model import predict_win_prob, run_pipeline

from conftest import SAMPLE_COACHED_PROFILE_ID

COACHED = 111  # mock_game's coached player


# ── Feature contract ─────────────────────────────────────────────────────────

def test_feature_columns_match_the_trained_artifact(distributions):
    """The hand-listed columns must agree with what the model was trained on."""
    trained = set(distributions['feature_cols'])
    declared = set(MODEL_FEATURE_COLS)
    assert declared == trained, (
        f'missing={trained - declared} extra={declared - trained}'
    )


def test_most_features_have_percentile_breakpoints(distributions):
    """
    A handful of techs are never researched in the training data and so have
    no breakpoints. The rest must, or they can never produce a recommendation.
    """
    assert len(distributions['percentiles']) >= 60


# ── Delta features ───────────────────────────────────────────────────────────

def test_build_delta_row_returns_the_full_feature_set(mock_game):
    delta, _ = build_delta_row(mock_game, profile_id=COACHED)
    assert set(delta) == set(MODEL_FEATURE_COLS)


def test_timing_delta_is_coached_player_minus_opponent(mock_game):
    """Coached player reached Feudal at 10.5, opponent at 11.0."""
    delta, _ = build_delta_row(mock_game, profile_id=COACHED)
    assert delta['feudal_min_delta'] == pytest.approx(10.5 - 11.0)


def test_count_delta_is_coached_player_minus_opponent(mock_game):
    """Coached player had 22 villagers, opponent 20."""
    delta, _ = build_delta_row(mock_game, profile_id=COACHED)
    assert delta['villagers_dark_age_delta'] == 2


def test_delta_is_none_when_neither_player_acted(mock_game):
    """Neither player built a Market, so the delta is unknown, not zero."""
    delta, _ = build_delta_row(mock_game, profile_id=COACHED)
    assert delta['market_min_delta'] is None


def test_meta_identifies_the_coached_player(mock_game):
    _, meta = build_delta_row(mock_game, profile_id=COACHED)
    assert meta['my_player_num'] == 1
    assert meta['opp_player_num'] == 2
    assert meta['my_result'] == 1
    assert meta['my_elo'] == 1750
    assert meta['opp_elo'] == 1780


def test_orientation_flips_when_the_other_player_is_coached(mock_game):
    """Coaching player 2 must invert every delta."""
    delta_p1, _ = build_delta_row(mock_game, profile_id=COACHED)
    delta_p2, meta = build_delta_row(mock_game, profile_id=222)
    assert meta['my_player_num'] == 2
    assert delta_p2['feudal_min_delta'] == pytest.approx(-delta_p1['feudal_min_delta'])
    assert delta_p2['villagers_dark_age_delta'] == -delta_p1['villagers_dark_age_delta']


# ── Percentile ranking ───────────────────────────────────────────────────────

def test_value_below_the_lowest_breakpoint_clamps_to_ten(distributions):
    breakpoints = distributions['percentiles']['feudal_min_delta']
    assert compute_percentile_rank(
        breakpoints[10] - 1.0, 'feudal_min_delta', distributions
    ) == 10.0


def test_value_above_the_highest_breakpoint_clamps_to_ninety(distributions):
    breakpoints = distributions['percentiles']['feudal_min_delta']
    assert compute_percentile_rank(
        breakpoints[90] + 1.0, 'feudal_min_delta', distributions
    ) == 90.0


def test_a_missing_measurement_has_no_percentile(distributions):
    assert compute_percentile_rank(None, 'feudal_min_delta', distributions) is None


def test_an_unknown_feature_has_no_percentile(distributions):
    assert compute_percentile_rank(1.0, 'not_a_feature', distributions) is None


def test_median_value_ranks_near_the_fiftieth_percentile(distributions):
    median = distributions['percentiles']['feudal_min_delta'][50]
    assert 45 < compute_percentile_rank(median, 'feudal_min_delta', distributions) < 55


# ── Recommendations ──────────────────────────────────────────────────────────

@pytest.fixture
def recommendations(mock_game, distributions):
    delta, _ = build_delta_row(mock_game, profile_id=COACHED)
    profile = get_user_profile(delta, distributions)
    uniform = {col: 1.0 / len(MODEL_FEATURE_COLS) for col in MODEL_FEATURE_COLS}
    return rank_recommendations(profile, uniform, top_n=5)


def test_returns_the_requested_number_of_recommendations(recommendations):
    assert len(recommendations) == 5


def test_recommendations_are_ranked_from_one(recommendations):
    assert [r['rank'] for r in recommendations] == [1, 2, 3, 4, 5]


def test_recommendations_are_ordered_by_descending_priority(recommendations):
    priorities = [r['priority'] for r in recommendations]
    assert priorities == sorted(priorities, reverse=True)


def test_each_recommendation_carries_the_fields_the_api_returns(recommendations):
    required = {
        'rank', 'feature', 'feature_col', 'value',
        'percentile', 'priority', 'direction', 'message',
    }
    for rec in recommendations:
        assert required <= set(rec)


def test_features_without_a_percentile_are_not_recommended(distributions):
    """A feature the coached player has no measurement for cannot be advised on."""
    profile = {'feudal_min_delta': {'value': None, 'percentile': None}}
    assert rank_recommendations(profile, {'feudal_min_delta': 1.0}, top_n=5) == []


# ── The sample replay, end to end ────────────────────────────────────────────

def test_sample_replay_parses_to_the_expected_shape(parsed_sample):
    assert {'filepath', 'map_id', 'duration_min', 'player_stats', 'de_players'} <= set(parsed_sample)


def test_sample_replay_has_two_players(parsed_sample):
    assert len(parsed_sample['player_stats']) == 2


def test_sample_replay_is_a_game_the_model_was_trained_for(parsed_sample):
    """Arabia, long enough to be meaningful — otherwise the pipeline warns."""
    assert parsed_sample['map_id'] == 9
    assert parsed_sample['duration_min'] > 8


def test_pipeline_produces_a_report_for_the_sample_replay(sample_replay, model, distributions):
    result = run_pipeline(
        str(sample_replay), model, distributions,
        profile_id=SAMPLE_COACHED_PROFILE_ID, top_n=5,
    )
    assert result['status'] == 'ok', result.get('error')
    assert 0.0 <= result['win_probability'] <= 1.0
    assert 0 < len(result['recommendations']) <= 5
    assert result['warnings'] == []


def test_pipeline_reports_an_error_rather_than_raising(model, distributions, tmp_path):
    """A file that is not a replay must come back as a status, not an exception."""
    junk = tmp_path / 'not-a-replay.aoe2record'
    junk.write_bytes(b'\x00\x01\x02\x03 definitely not a replay')
    result = run_pipeline(str(junk), model, distributions)
    assert result['status'] == 'error'
    assert result['error']


def test_inference_accepts_a_row_of_entirely_missing_features(model, distributions):
    """
    Techs that were never researched arrive as None. XGBoost must receive
    float NaN, not object dtype (ISSUE-007).
    """
    empty = {col: None for col in distributions['feature_cols']}
    prob = predict_win_prob(model, empty, distributions['feature_cols'])
    assert 0.0 <= prob <= 1.0


# ── Model quality (slow) ─────────────────────────────────────────────────────

@pytest.mark.slow
def test_model_ranks_wins_above_losses(model, distributions, features_delta_csv):
    """
    Guards against shipping a model that no longer discriminates. Runs over
    the full training set, so it is excluded from the default run.
    """
    import numpy as np
    import pandas as pd

    frame = pd.read_csv(features_delta_csv)
    cols = distributions['feature_cols']
    probs = np.array([
        predict_win_prob(model, {c: row.get(c) for c in cols}, cols)
        for _, row in frame.iterrows()
    ])
    actual = frame['result'].to_numpy(dtype=int)

    assert probs.min() >= 0.0 and probs.max() <= 1.0
    assert probs[actual == 1].mean() > probs[actual == 0].mean()
    assert ((probs >= 0.5).astype(int) == actual).mean() > 0.70
