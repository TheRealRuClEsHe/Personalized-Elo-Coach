"""
src/features.py — Feature engineering for the API pipeline

Provides:
    extract_player_features(stats)   → flat numeric dict from one player's stats
    build_delta_row(game, profile_id) → (delta_dict, meta_dict)

Design notes:
- MODEL_FEATURE_COLS is the canonical ordered list of 70 delta features the
  model was trained on. This is the ground truth — never reorder or rename.
- Delta = me - opponent. For timing features (_min), lower delta = I clicked
  faster. For count features, higher delta = I did more.
- Missing values (NaN) are left as None/NaN — XGBoost handles them natively
  (DEC-008). Never impute.
- This module has no I/O — it takes dicts and returns dicts.
"""

from __future__ import annotations

import math
from typing import Optional

from src.parser import TRACKED_BUILDINGS, TRACKED_TECHS, BUILDING_COUNT_MAP, MY_PROFILE_ID

# ── The exact 70 features the model was trained on (from cohort_distributions.pkl)
# Order matters — this matches the column order in features_delta.csv.
MODEL_FEATURE_COLS = [
    'villagers_dark_age_delta',
    'villagers_feudal_age_delta',
    'villagers_castle_age_delta',
    'villagers_imperial_age_delta',
    'mil_trained_dark_age_delta',
    'mil_trained_feudal_age_delta',
    'mil_trained_castle_age_delta',
    'mil_trained_imperial_age_delta',
    'apm_dark_age_delta',
    'apm_feudal_age_delta',
    'apm_castle_age_delta',
    'apm_imperial_age_delta',
    'gather_point_count_delta',
    'wall_count_delta',
    'move_count_delta',
    'order_count_delta',
    'stance_count_delta',
    'ungarrison_count_delta',
    'first_wall_min_delta',
    'market_min_delta',
    'first_barracks_min_delta',
    'first_stable_min_delta',
    'first_archery_min_delta',
    'blacksmith_min_delta',
    'feudal_min_delta',
    'castle_min_delta',
    'imperial_min_delta',
    'double_bit_axe_min_delta',
    'bow_saw_min_delta',
    'two_man_saw_min_delta',
    'horse_collar_min_delta',
    'heavy_plow_min_delta',
    'crop_rotation_min_delta',
    'gold_mining_min_delta',
    'gold_shafting_mining_min_delta',
    'stone_mining_min_delta',
    'stone_shafting_mining_min_delta',
    'wheelbarrow_min_delta',
    'hand_cart_min_delta',
    'town_watch_min_delta',
    'town_patrol_min_delta',
    'loom_min_delta',
    'forging_min_delta',
    'iron_casting_min_delta',
    'blast_furnace_min_delta',
    'scale_mail_armor_min_delta',
    'chain_mail_armor_min_delta',
    'plate_mail_armor_min_delta',
    'scale_barding_armor_min_delta',
    'chain_barding_armor_min_delta',
    'plate_barding_armor_min_delta',
    'fletching_min_delta',
    'bodkin_arrow_min_delta',
    'bracer_min_delta',
    'padded_archer_armor_min_delta',
    'leather_archer_armor_min_delta',
    'ring_archer_armor_min_delta',
    'bloodlines_min_delta',
    'husbandry_min_delta',
    'thumb_ring_min_delta',
    'parthian_tactics_min_delta',
    'arson_min_delta',
    'gambeson_min_delta',
    'squires_min_delta',
    'chemistry_min_delta',
    'barracks_count_delta',
    'stable_count_delta',
    'archery_count_delta',
    'blacksmith_count_delta',
    'market_count_delta',
]

# Base feature names (without _delta suffix)
_BASE_COLS = [c.replace('_delta', '') for c in MODEL_FEATURE_COLS]


def _safe_sub(a, b):
    """Subtract two values that may be None/NaN. Returns None if either is None."""
    if a is None or b is None:
        return None
    if isinstance(a, float) and math.isnan(a):
        return None
    if isinstance(b, float) and math.isnan(b):
        return None
    return a - b


def extract_player_features(stats: dict) -> dict:
    """
    Flatten one player_stats entry into a plain dict of numeric features.

    Handles:
    - Direct scalar fields (count + timing cols)
    - military_buildings_placed → barracks_count, stable_count, etc.
    - market_count (stored separately in stats)

    Returns a dict keyed by base feature names (no _delta suffix).
    """
    mbp = dict(stats.get('military_buildings_placed', {}))

    feats = {}

    # ── Count features
    for col in (
        'villagers_dark_age', 'villagers_feudal_age',
        'villagers_castle_age', 'villagers_imperial_age',
        'mil_trained_dark_age', 'mil_trained_feudal_age',
        'mil_trained_castle_age', 'mil_trained_imperial_age',
        'apm_dark_age', 'apm_feudal_age', 'apm_castle_age', 'apm_imperial_age',
        'gather_point_count', 'wall_count',
        'move_count', 'order_count', 'stance_count', 'ungarrison_count',
        'market_count',
    ):
        feats[col] = stats.get(col, 0)

    # ── Timing features (may be None = never happened)
    for col in (
        ['first_wall_min', 'market_min']
        + list(TRACKED_BUILDINGS.values())
        + list(TRACKED_TECHS.values())
    ):
        feats[col] = stats.get(col)  # None if never happened

    # ── Building counts (from military_buildings_placed)
    for bid, col in BUILDING_COUNT_MAP.items():
        feats[col] = mbp.get(bid, 0)

    return feats


def build_delta_row(game: dict, profile_id: Optional[int] = None) -> tuple[dict, dict]:
    """
    Compute delta features from a parsed game, oriented as me - opponent.

    Parameters
    ----------
    game        : dict returned by parse_replay()
    profile_id  : int, optional
        If provided, this player is treated as "me."
        If None or not found, defaults to MY_PROFILE_ID, then falls back to
        the player with the lower player_num (player 1).

    Returns
    -------
    delta_dict : dict
        {feature_col: float | None}  — 70 delta features aligned to MODEL_FEATURE_COLS.
        None values represent "neither player performed this action."
    meta_dict : dict
        {
          'my_player_num'  : int,
          'opp_player_num' : int,
          'my_profile_id'  : int | None,
          'my_result'      : int,     # 0 = loss, 1 = win
          'my_elo'         : float | None,
          'opp_elo'        : float | None,
          'my_civ'         : int | None,
          'opp_civ'        : int | None,
          'duration_min'   : float,
        }

    Raises
    ------
    ValueError  if fewer than 2 players are found in the game.
    """
    player_nums  = sorted(game['player_stats'].keys())
    de_players   = game.get('de_players', {})

    if len(player_nums) < 2:
        raise ValueError(f"Expected 2 players, found {len(player_nums)}")

    # ── Identify me vs opponent ────────────────────────────────────────────────
    target_pid = profile_id or MY_PROFILE_ID
    my_player_num = None

    for pnum in player_nums:
        dp = de_players.get(pnum, {})
        if dp.get('profile_id') == target_pid:
            my_player_num = pnum
            break

    if my_player_num is None:
        # Profile not found — default to player 1
        my_player_num = player_nums[0]

    opp_player_num = next(p for p in player_nums if p != my_player_num)

    # ── Extract flat features ─────────────────────────────────────────────────
    me_feats  = extract_player_features(game['player_stats'][my_player_num])
    opp_feats = extract_player_features(game['player_stats'][opp_player_num])

    # ── Compute delta = me - opponent ─────────────────────────────────────────
    delta_dict = {}
    for base_col in _BASE_COLS:
        delta_col = base_col + '_delta'
        delta_dict[delta_col] = _safe_sub(
            me_feats.get(base_col),
            opp_feats.get(base_col),
        )

    # ── Metadata ──────────────────────────────────────────────────────────────
    my_stats  = game['player_stats'][my_player_num]
    opp_stats = game['player_stats'][opp_player_num]
    my_dp     = de_players.get(my_player_num, {})
    opp_dp    = de_players.get(opp_player_num, {})

    meta_dict = {
        'my_player_num':  my_player_num,
        'opp_player_num': opp_player_num,
        'my_profile_id':  my_dp.get('profile_id'),
        'my_result':      my_stats.get('result'),
        'my_elo':         my_stats.get('elo'),
        'opp_elo':        opp_stats.get('elo'),
        'my_civ':         my_dp.get('civilization_id') or my_dp.get('civ_id'),
        'opp_civ':        opp_dp.get('civilization_id') or opp_dp.get('civ_id'),
        'duration_min':   game['duration_min'],
    }

    return delta_dict, meta_dict
