"""
src/coaching.py — Percentile ranking and coaching recommendation logic
Extracted from 06_shap_analysis.ipynb

Provides:
    compute_percentile_rank(value, col, distributions) → float | None
    get_user_profile(delta_dict, distributions)         → {col: {value, percentile}}
    rank_recommendations(user_profile, shap_importance, top_n) → list[dict]
    COACHING_MESSAGES                                   → {col: (direction, message)}

Design notes:
- Percentile breakpoints are stored in cohort_distributions.pkl at keys [10,25,50,75,90].
- Timing features (_min): lower is better. Weakness = high percentile.
- Count/activity features: higher is better. Weakness = low percentile.
- Priority = shap_importance × weakness_score (0–1).
"""

from __future__ import annotations

import math
from typing import Optional

# ── Coaching messages ─────────────────────────────────────────────────────────
# {delta_col: (direction, message)}
# direction: 'negative' = lower value is better (timing), 'positive' = higher is better
COACHING_MESSAGES: dict[str, tuple[str, str]] = {
    'feudal_min_delta': (
        'negative',
        'Your feudal time is slower than opponents. Click up earlier — feudal time is the single '
        'biggest win predictor in this Elo range. Aim to click feudal by 9:30–10:00.',
    ),
    'castle_min_delta': (
        'negative',
        'Your castle age timing is behind. Rushing to Castle unlocks Knights, Crossbows, and Unique '
        'Units before your opponent. Target castle click-up by 17–18 minutes.',
    ),
    'hand_cart_min_delta': (
        'negative',
        'You research Hand Cart later than opponents. Hand Cart is one of the most cost-efficient '
        'villager upgrades — delay hurts your economy for the rest of the game.',
    ),
    'gold_mining_min_delta': (
        'negative',
        'You start mining gold later than opponents. Getting gold miners up early funds military '
        'production and prevents being outnumbered when pressure comes.',
    ),
    'loom_min_delta': (
        'negative',
        'You research Loom later than opponents. Loom is critical for villager survival during early '
        'scout rushes — research it within the first 2 minutes.',
    ),
    'imperial_min_delta': (
        'negative',
        'Your Imperial Age timing lags. In late-game scenarios Imperial timing determines access to '
        'Trebuchets, Paladins, and elite upgrades before your opponent can respond.',
    ),
    'double_bit_axe_min_delta': (
        'negative',
        'You research Double-Bit Axe later than opponents. This is your first eco upgrade in Feudal — '
        'research it immediately after transitioning to stay even on wood income.',
    ),
    'horse_collar_min_delta': (
        'negative',
        'Your Horse Collar timing is slow. Getting this early in Feudal increases farm output and lets '
        'you sustain villager production through the dark age transition.',
    ),
    'wheelbarrow_min_delta': (
        'negative',
        'You research Wheelbarrow later than opponents. Wheelbarrow is the biggest mid-game eco '
        'upgrade — research it in early Castle Age to compound your food income.',
    ),
    'bow_saw_min_delta': (
        'negative',
        'Slow Bow Saw research. Wood is the bottleneck for Castle Age production — getting this '
        'upgrade early lets you run more production buildings without choking.',
    ),
    'town_watch_min_delta': (
        'negative',
        'You research Town Watch late. This gives map awareness and protects your villagers from '
        'early raiding — worth researching in Feudal when scouting picks up.',
    ),
    'move_count_delta': (
        'positive',
        'Your move command count is lower than opponents, suggesting less active micro. '
        'Keep units moving, harass more, and actively scout with your military.',
    ),
    'order_count_delta': (
        'positive',
        'Fewer order commands means less active villager management. '
        'Queue villagers consistently and issue explicit gather orders after each build.',
    ),
    'villagers_dark_age_delta': (
        'positive',
        'You have fewer villagers when reaching Feudal Age than opponents'
        'Keep TC always producing. Never let it go idle.',
    ),
    'villagers_feudal_age_delta': (
        'positive',
        'You have fewer villagers when reaching Castle Age than opponents'
        'Keep TC always producing. Never let it go idle.',
    ),
    'villagers_castle_age_delta': (
        'positive',
        'Fewer villagers at Castle Age means your economy is behind. '
        'Keep TC always producing. Never let it go idle between ages.',
    ),
    'mil_trained_feudal_age_delta': (
        'positive',
        'You train fewer military units in Feudal Age than opponents. '
        'Even 2–3 scouts or spearmen provide map control and deny opponent scouting.',
    ),
    'mil_trained_castle_age_delta': (
        'positive',
        'Fewer Castle Age military units trained. Build 1–2 production buildings immediately '
        'upon entering Castle Age and start pressure.',
    ),
    'mil_trained_imperial_age_delta': (
        'positive',
        'You train fewer military units in Imperial Age than opponents. '
        'Sustained military production in Imperial is critical especially in late game situations where one fight can decide the game.',
    ),
    'apm_feudal_age_delta': (
        'positive',
        'Lower actions-per-minute in Feudal Age suggests you are less active during the critical '
        'economic phase. Focus on eco upgrades, villager tasking, and scouting simultaneously.',
    ),
    'apm_castle_age_delta': (
        'positive',
        'Lower Castle Age APM. Castle Age is when fights happen — focus on army micro, '
        'TC production, and economy simultaneously.',
    ),
    'gather_point_count_delta': (
        'positive',
        'Fewer gather point commands. Setting gather points on resources and drop sites '
        'is a high-leverage habit that keeps villagers working without constant attention.',
    ),
    'first_wall_min_delta': (
        'negative',
        'You build your first wall later than opponents. Early walls provide map control and protect '
        'your economy from early aggression — start building walls in Feudal especially on open maps like Arabia',
    ),
    'first_barracks_min_delta': (
        'negative',
        'You build your first Barracks later than opponents. Early Barracks gives you map control '
        'and the option for a Feudal push before the opponent walls or pressures.',
    ),
    'barracks_count_delta': (
        'positive',
        'Fewer Barracks built than opponents. More production buildings means faster army '
        'replenishment — add a second or third Barracks when transitioning to Castle.',
    ),
    'first_stable_min_delta': (
        'negative',
        'Slower Stable timing. Stable gives you Knight production — the dominant Castle Age unit. '
        'Getting it up quickly after Castle click-up is a core habit.',
    ),
    'first_archery_min_delta': (
        'negative',
        'Slower Archery Range timing. If you plan an Archer-based strategy, the range should go '
        'up in Feudal right after Barracks — delay costs you units and map presence.',
    ),
}


# ── Percentile ranking ────────────────────────────────────────────────────────

def compute_percentile_rank(value, col: str, distributions: dict) -> Optional[float]:
    """
    Return the percentile rank of `value` within the stored distribution for `col`.

    Uses linear interpolation between stored breakpoints [10, 25, 50, 75, 90].
    Returns None if col not in distributions or value is NaN/None.
    """
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None

    percs = distributions.get('percentiles', {}).get(col)
    if percs is None:
        return None

    breakpoints = [10, 25, 50, 75, 90]
    vals = [percs[p] for p in breakpoints]

    if value <= vals[0]:
        return 10.0
    if value >= vals[-1]:
        return 90.0

    for i in range(len(vals) - 1):
        if vals[i] <= value <= vals[i + 1]:
            span = vals[i + 1] - vals[i] + 1e-9
            frac = (value - vals[i]) / span
            return breakpoints[i] + frac * (breakpoints[i + 1] - breakpoints[i])

    return 50.0


def get_user_profile(delta_dict: dict, distributions: dict) -> dict:
    """
    Given one delta feature dict, return percentile profile.

    Returns
    -------
    {col: {'value': float | None, 'percentile': float | None}}
    for each col in delta_dict.
    """
    profile = {}
    for col, val in delta_dict.items():
        if isinstance(val, float) and math.isnan(val):
            val = None
        pct = compute_percentile_rank(val, col, distributions)
        profile[col] = {'value': val, 'percentile': pct}
    return profile


# ── Recommendation engine ─────────────────────────────────────────────────────

# Features where LOWER delta = better performance (you were faster)
_LOWER_IS_BETTER = frozenset(
    col for col in COACHING_MESSAGES if COACHING_MESSAGES[col][0] == 'negative'
)


def rank_recommendations(
    user_profile: dict,
    global_shap_importance: dict,
    top_n: int = 5,
) -> list[dict]:
    """
    Rank delta features by coaching priority.

    Priority logic:
    - Timing features (_min, lower=better):
        weakness_score = percentile / 100   (high pct = you are slow = weak)
    - Count/activity features (higher=better):
        weakness_score = 1 - percentile / 100  (low pct = you do less = weak)
    priority = shap_importance × weakness_score

    Parameters
    ----------
    user_profile        : output of get_user_profile()
    global_shap_importance : {col: float} — mean |SHAP| per feature
    top_n               : number of recommendations to return

    Returns
    -------
    list of dicts, sorted by priority descending:
    [
      {
        'rank'            : int,
        'feature'         : str,   # human-readable (no _delta suffix)
        'feature_col'     : str,   # full delta col name
        'value'           : float | None,
        'percentile'      : float | None,
        'shap_importance' : float,
        'priority'        : float,
        'direction'       : str,   # 'negative' | 'positive'
        'message'         : str,   # coaching text (empty string if no message)
      }
    ]
    """
    rows = []
    for col, info in user_profile.items():
        pct = info.get('percentile')
        if pct is None:
            continue
        shap_imp = global_shap_importance.get(col, 0.0)

        # Determine if timing (lower=better) by col name or direction in messages
        is_timing = '_min_delta' in col or col in _LOWER_IS_BETTER
        weakness_score = (pct / 100.0) if is_timing else (1.0 - pct / 100.0)
        priority = shap_imp * weakness_score

        msg_entry = COACHING_MESSAGES.get(col, ('', ''))
        direction = msg_entry[0] if msg_entry[0] else ('negative' if is_timing else 'positive')
        message   = msg_entry[1] if len(msg_entry) > 1 else ''

        rows.append({
            'feature':          col.replace('_delta', ''),
            'feature_col':      col,
            'value':            info['value'],
            'percentile':       pct,
            'shap_importance':  shap_imp,
            'priority':         priority,
            'direction':        direction,
            'message':          message,
        })

    rows.sort(key=lambda r: r['priority'], reverse=True)
    top = rows[:top_n]
    for i, r in enumerate(top):
        r['rank'] = i + 1

    return top
