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
        'Your feudal age timing is slower than opponent. Clicking up earlier is usually signals better '
        'economy management.',
    ),
    'castle_min_delta': (
        'negative',
        'Your castle age timing is slower than opponent. Castle Age unlocks Knights, Crossbows, Unique '
        'Units and other powerful units.',
    ),
    'hand_cart_min_delta': (
        'negative',
        'You research Hand Cart later than opponent. delaying this eco upgrades means your villagers '
        'are less efficient for the rest of the game.',
    ),
    'gold_mining_min_delta': (
        'negative',
        'You researched gold mining later than opponent. Getting gold miners up early funds military '
        'production and prevents being outnumbered when pressure comes.',
    ),
    'loom_min_delta': (
        'negative',
        'You research Loom later than opponent. Loom is critical for villager survival during early '
        'scout rushes — research it within the first 2 minutes.',
    ),
    'imperial_min_delta': (
        'negative',
        'Your Imperial Age timing lags. In late-game scenarios Imperial timing determines access to '
        'Trebuchets, Paladins, and elite upgrades before your opponent can respond.',
    ),
    'double_bit_axe_min_delta': (
        'negative',
        'You research Double-Bit Axe later than opponent. This is your first eco upgrade in Feudal — '
        'research it immediately after transitioning to stay even on wood income.',
    ),
    'horse_collar_min_delta': (
        'negative',
        'Your Horse Collar timing is slow. Getting this early in Feudal increases farm output and lets '
        'you sustain villager production through the dark age transition.',
    ),
    'wheelbarrow_min_delta': (
        'negative',
        'You research Wheelbarrow later than opponent. Wheelbarrow is the biggest mid-game eco '
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
        'Your move command count is lower than opponent, suggesting less active micro. '
        'Keep units moving, harass more, and actively scout with your military.',
    ),
    'order_count_delta': (
        'positive',
        'Fewer order commands means less active villager management. '
        'Queue villagers consistently and issue explicit gather orders after each build.',
    ),
    'villagers_dark_age_delta': (
        'positive',
        'You have fewer villagers when reaching Feudal Age than opponent. '
        'Keep TC always producing. Never let it go idle.',
    ),
    'villagers_feudal_age_delta': (
        'positive',
        'You have fewer villagers when reaching Castle Age than opponent. '
        'Keep TC always producing. Never let it go idle.',
    ),
    'villagers_castle_age_delta': (
        'positive',
        'Fewer villagers at Castle Age means your economy is behind. '
        'Keep TC always producing. Never let it go idle.',
    ),
    'villagers_imperial_age_delta': (
        'positive',
        'Fewer villagers in Imperial Age than your opponent. '
        'Keep TC always producing — villager lead in late game means faster unit replenishment and stronger eco recovery after fights.',
    ),
    'mil_trained_feudal_age_delta': (
        'positive',
        'You train fewer military units in Feudal Age than opponent. '
        'Even 2–3 scouts or spearmen provide map control and deny opponent scouting.',
    ),
    'mil_trained_castle_age_delta': (
        'positive',
        'Fewer Castle Age military units trained. Build 1–2 production buildings immediately '
        'upon entering Castle Age and start pressure.',
    ),
    'mil_trained_imperial_age_delta': (
        'positive',
        'You train fewer military units in Imperial Age than opponent. '
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
        'You build your first wall later than opponent. Early walls provide map control and protect '
        'your economy from early aggression — start building walls in Feudal especially on open maps like Arabia',
    ),
    'first_barracks_min_delta': (
        'negative',
        'You build your first Barracks later than opponent. Early Barracks gives you map control '
        'and the option for a Feudal push before the opponent walls or pressures.',
    ),
    'barracks_count_delta': (
        'positive',
        'Fewer Barracks built than opponent. More production buildings means faster army '
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
    # ── Count features ────────────────────────────────────────────────────────
    'mil_trained_dark_age_delta': (
        'positive',
        'Fewer military units trained in Dark Age than your opponent. A few scouts or militia '
        'provide map control and deny your opponent\'s scouting before Feudal.',
    ),
    'apm_dark_age_delta': (
        'positive',
        'Lower actions-per-minute in Dark Age. The opening build phase demands multitasking — '
        'queue villagers, move your scout, task villagers to new resources, and plan simultaneously.',
    ),
    'apm_imperial_age_delta': (
        'positive',
        'Lower APM in Imperial Age. Late game demands constant attention — produce units, '
        'research upgrades, manage siege, and keep villagers tasked while fighting.',
    ),
    'wall_count_delta': (
        'positive',
        'Fewer wall segments built than your opponent. Walls limit raid paths and force opponent '
        'to commit to a frontal assault. Prioritize walling chokepoints and woodlines in Feudal.',
    ),
    'stance_count_delta': (
        'positive',
        'Fewer stance commands than your opponent. Setting aggressive stance on scouts and '
        'defensive stance on villagers under attack is a low-cost habit that saves units.',
    ),
    'ungarrison_count_delta': (
        'positive',
        'Fewer ungarrison commands. During raids, villagers should garrison quickly then ungarrison '
        'to resume work once the threat clears — delays cost you villager working time.',
    ),
    'stable_count_delta': (
        'positive',
        'Fewer Stables built than your opponent. More Stables means faster Knight production '
        'and quicker army replenishment after fights — add a second Stable in Castle Age.',
    ),
    'archery_count_delta': (
        'positive',
        'Fewer Archery Ranges built than your opponent. If playing an Archer strategy, '
        'multiple ranges sustain pressure — add a second range once you hit Castle Age.',
    ),
    'blacksmith_count_delta': (
        'positive',
        'Fewer Blacksmiths built. Multiple Blacksmiths let you research attack and armor '
        'upgrades in parallel — one extra Blacksmith in Castle Age pays for itself quickly.',
    ),
    'market_count_delta': (
        'positive',
        'Fewer Markets built than your opponent. Markets let you convert excess resources '
        'into gold and are required for Guilds and trade — build one in Castle Age.',
    ),

    # ── Timing: eco buildings ─────────────────────────────────────────────────
    'blacksmith_min_delta': (
        'negative',
        'You build your Blacksmith later than opponent. The Blacksmith unlocks all attack '
        'and armor upgrades — build it immediately upon reaching Castle Age.',
    ),
    'market_min_delta': (
        'negative',
        'You build your Market later than opponent. An early Market lets you sell excess '
        'resources for gold when your mines run low — a critical safety valve in long games.',
    ),

    # ── Timing: lumber upgrades ───────────────────────────────────────────────
    'two_man_saw_min_delta': (
        'negative',
        'Slow Two-Man Saw research. Your primary Castle Age lumber upgrade — '
        'research it early to keep wood income competitive during heavy production phases.',
    ),

    # ── Timing: farm upgrades ─────────────────────────────────────────────────
    'heavy_plow_min_delta': (
        'negative',
        'You research Heavy Plow late. Heavy Plow significantly increases farm yield — '
        'research it in Castle Age to sustain villager production through the mid-game.',
    ),
    'crop_rotation_min_delta': (
        'negative',
        'Slow Crop Rotation research. The final farm upgrade gives the highest yield — '
        'research it in Imperial Age to maximise food income for sustained unit production.',
    ),

    # ── Timing: mining upgrades ───────────────────────────────────────────────
    'gold_shafting_mining_min_delta': (
        'negative',
        'You research Gold Shaft Mining late. This Castle Age upgrade increases gold miner '
        'output — research it upon reaching Castle Age to sustain military production longer.',
    ),
    'stone_mining_min_delta': (
        'negative',
        'Slow Stone Mining research. If you plan to build Castles or Stone Walls, '
        'research Stone Mining early in Feudal to accelerate your stone income.',
    ),
    'stone_shafting_mining_min_delta': (
        'negative',
        'You research Stone Shaft Mining late. Faster stone collection lets you get Castles '
        'up sooner — essential for a Castle-drop or tower rush strategy.',
    ),

    # ── Timing: town upgrades ─────────────────────────────────────────────────
    'town_patrol_min_delta': (
        'negative',
        'Slow Town Patrol research. Town Patrol extends your line of sight beyond Town Watch — '
        'research it in Castle Age to maintain map awareness as armies get larger.',
    ),

    # ── Timing: blacksmith attack upgrades ────────────────────────────────────
    'forging_min_delta': (
        'negative',
        'You research Forging late. The first Blacksmith attack upgrade — research in Feudal '
        'or early Castle Age. Attack advantage compounds through every fight.',
    ),
    'iron_casting_min_delta': (
        'negative',
        'Slow Iron Casting research. The second attack upgrade — research in Castle Age '
        'to keep your army damage ahead of your opponent\'s armor.',
    ),
    'blast_furnace_min_delta': (
        'negative',
        'You research Blast Furnace late. The final attack upgrade — a must-have before '
        'Imperial Age battles. Delay lets your opponent\'s units survive longer in every fight.',
    ),

    # ── Timing: infantry armor ────────────────────────────────────────────────
    'scale_mail_armor_min_delta': (
        'negative',
        'Slow Scale Mail Armor research. The first infantry armor upgrade — research in '
        'early Castle Age if running infantry to increase survivability in prolonged fights.',
    ),
    'chain_mail_armor_min_delta': (
        'negative',
        'You research Chain Mail Armor late. Keep the infantry armor chain moving in Castle Age '
        'to stay ahead in sustained fights.',
    ),
    'plate_mail_armor_min_delta': (
        'negative',
        'Slow Plate Mail Armor research. Maximum infantry armor — research in Imperial Age '
        'to make your infantry line significantly harder to kill in late-game fights.',
    ),

    # ── Timing: cavalry armor ─────────────────────────────────────────────────
    'scale_barding_armor_min_delta': (
        'negative',
        'You research Scale Barding Armor late. The first cavalry armor upgrade — get it in '
        'early Castle Age when running Knights to improve their survivability.',
    ),
    'chain_barding_armor_min_delta': (
        'negative',
        'Slow Chain Barding Armor research. The second cavalry armor upgrade — research in '
        'Castle Age to keep your Knights alive through sustained pressure.',
    ),
    'plate_barding_armor_min_delta': (
        'negative',
        'You research Plate Barding Armor late. Full cavalry armor is critical for late-game '
        'Paladin and Knight fights — delays cost you units in every engagement.',
    ),

    # ── Timing: archer attack upgrades ────────────────────────────────────────
    'fletching_min_delta': (
        'negative',
        'Slow Fletching research. The first archer attack upgrade adds range and damage — '
        'research it immediately upon hitting Castle Age if playing an Archer composition.',
    ),
    'bodkin_arrow_min_delta': (
        'negative',
        'You research Bodkin Arrow late. The second archer attack upgrade — delays let your '
        'opponent\'s archers out-damage yours in Castle Age fights.',
    ),
    'bracer_min_delta': (
        'negative',
        'Slow Bracer research. The final archer attack upgrade adds range and damage — '
        'a must-have in Imperial Age for Arbalest or Cavalry Archer compositions.',
    ),

    # ── Timing: archer armor ──────────────────────────────────────────────────
    'padded_archer_armor_min_delta': (
        'negative',
        'You research Padded Archer Armor late. Reduces chip damage from Skirmishers and other '
        'archers — research in Feudal or early Castle Age if playing Archers.',
    ),
    'leather_archer_armor_min_delta': (
        'negative',
        'Slow Leather Archer Armor research. Keep the archer armor chain going in Castle Age '
        'to reduce losses in sustained archer fights.',
    ),
    'ring_archer_armor_min_delta': (
        'negative',
        'You research Ring Archer Armor late. Maximum archer armor — research in Imperial Age '
        'to make your ranged units significantly more resilient in late-game engagements.',
    ),

    # ── Timing: cavalry upgrades ──────────────────────────────────────────────
    'bloodlines_min_delta': (
        'negative',
        'Slow Bloodlines research. Bloodlines gives all cavalry +20 HP — one of the '
        'highest-value Stable upgrades. Research it as soon as you reach Castle Age.',
    ),
    'husbandry_min_delta': (
        'negative',
        'You research Husbandry late. Increases cavalry movement speed by 10% — '
        'critical for Knights raiding, catching archers, and escaping bad fights.',
    ),

    # ── Timing: archery/stable upgrades ───────────────────────────────────────
    'thumb_ring_min_delta': (
        'negative',
        'Slow Thumb Ring research. Maximises archer fire rate and accuracy — '
        'a high-priority Castle Age upgrade for any Archer or Cavalry Archer strategy.',
    ),
    'parthian_tactics_min_delta': (
        'negative',
        'You research Parthian Tactics late. Gives armor and attack bonuses to Cavalry Archers — '
        'essential if running a CA composition in Castle or Imperial Age.',
    ),

    # ── Timing: miscellaneous upgrades ────────────────────────────────────────
    'arson_min_delta': (
        'negative',
        'Slow Arson research. Gives infantry a bonus against buildings — research it if '
        'running a Feudal or early Castle Age infantry push.',
    ),
    'gambeson_min_delta': (
        'negative',
        'You research Gambeson late. Gives the militia line additional armor — '
        'an inexpensive Barracks upgrade that improves infantry survivability in early fights.',
    ),
    'squires_min_delta': (
        'negative',
        'Slow Squires research. Increases infantry movement speed — faster infantry means '
        'better raiding, quicker responses to attacks, and easier retreats.',
    ),
    'chemistry_min_delta': (
        'negative',
        'You research Chemistry late. Increases projectile damage for all ranged units and '
        'is required for Petards — a must-have in Imperial Age for any ranged composition.',
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
        shap_imp = global_shap_importance.get(col, 0.0) # how important this feature is to the model

        # Determine if timing (lower=better) by col name or direction in messages
        is_timing = '_min_delta' in col or col in _LOWER_IS_BETTER # Is this a timing feature (lower = better)?
        
        # weakness_score: how bad is the player at this feature?
        #   timing: high percentile = slow = weak → score close to 1.0
        #   count:  low percentile  = fewer = weak → score close to 1.0
        weakness_score = (pct / 100.0) if is_timing else (1.0 - pct / 100.0)

        # priority = model importance × how weak you are at it
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
