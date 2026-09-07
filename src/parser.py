"""
src/parser.py — Replay parsing logic extracted from 02_bulk_parsing_new.ipynb

Provides:
    parse_header(filepath)      → (map_id, rated, num_players)
    parse_replay(filepath)      → raw game dict (see docstring)
    flatten_player_row(game, player_num) → flat dict for batch CSV pipeline

No file paths, logging config, or pandas imports here — keep this import-safe
so the API can load it without side effects.
"""

import logging
import os
from collections import defaultdict

# Must precede the mgz imports below: installs the vendored header that
# supports newer AoE2 DE save formats. See src/mgz_compat.py.
import src.mgz_compat  # noqa: F401

from mgz.fast import operation, Operation, meta
from mgz.fast.header import parse as fast_header_parse

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
ARABIA_MAP_ID         = 9
RM_1V1_LEADERBOARD_ID = 3
MIN_DURATION_MIN      = 8

MY_PROFILE_ID  = 3134896
MY_PLAYER_NAME = {'TheRealRuClEsHe', "b'TheRealRuClEsHe'"}

VILLAGER_IDS = {83, 293}   # 83 = male villager, 293 = female villager (Aztecs + civ-dependent)

TRACKED_BUILDINGS = {
    12:  'first_barracks_min',
    101: 'first_stable_min',
    87:  'first_archery_min',
    103: 'blacksmith_min',
}

BUILDING_COUNT_MAP = {
    12:  'barracks_count',
    101: 'stable_count',
    87:  'archery_count',
    103: 'blacksmith_count',
}

WALL_IDS   = {72, 117, 155}   # Palisade, Stone, Fortified
MARKET_IDS = {84, 116, 137}   # Feudal, Castle, Imperial market

TRACKED_TECHS = {
    101: 'feudal_min',   102: 'castle_min',   103: 'imperial_min',
    211: 'double_bit_axe_min',     212: 'bow_saw_min',              221: 'two_man_saw_min',
    14:  'horse_collar_min',       13:  'heavy_plow_min',           12:  'crop_rotation_min',
    55:  'gold_mining_min',        182: 'gold_shafting_mining_min',
    278: 'stone_mining_min',       279: 'stone_shafting_mining_min',
    213: 'wheelbarrow_min',        249: 'hand_cart_min',
    8:   'town_watch_min',         280: 'town_patrol_min',          22: 'loom_min',
    67:  'forging_min',            68:  'iron_casting_min',         75: 'blast_furnace_min',
    74:  'scale_mail_armor_min',   76:  'chain_mail_armor_min',     77: 'plate_mail_armor_min',
    81:  'scale_barding_armor_min', 82: 'chain_barding_armor_min',  80: 'plate_barding_armor_min',
    199: 'fletching_min',          200: 'bodkin_arrow_min',         201: 'bracer_min',
    215: 'padded_archer_armor_min', 218: 'leather_archer_armor_min', 219: 'ring_archer_armor_min',
    435: 'bloodlines_min',         39:  'husbandry_min',
    437: 'thumb_ring_min',         436: 'parthian_tactics_min',
    602: 'arson_min',              875: 'gambeson_min',
    216: 'squires_min',            47:  'chemistry_min',
}


def parse_header(filepath):
    """
    Fast header-only parse — used to pre-screen replays.

    Returns
    -------
    (map_id, rated, num_players) : tuple
        map_id      : int   — e.g. 9 for Arabia
        rated       : bool
        num_players : int   — number of human players
    """
    with open(filepath, 'rb') as f:
        try:
            h = fast_header_parse(f)
        except RuntimeError:
            import traceback
            log.error('mgz-fast header parse failed (Linux binary incompatibility?):\n%s',
                      traceback.format_exc())
            raise RuntimeError(
                'mgz-fast could not parse this replay header. '
                'The file may use a newer patch format unsupported on Linux.'
            )
        de      = h.get('de') or {}
        players = [p for p in (h.get('players') or []) if p and p.get('type') == 1]
        return de.get('rms_map_id'), de.get('rated', False), len(players)


def parse_replay(filepath):
    """
    Full parse of one .aoe2record file.

    Returns a dict:
    {
        'filepath'     : str,
        'map_id'       : int,
        'rated'        : bool,
        'num_players'  : int,
        'duration_min' : float,
        'de_players'   : {player_num: {profile_id, name, civilization_id, ...}},
        'player_stats' : {player_num: {all tracked features + result + elo}},
    }

    result  : 0 = loss (resigned), 1 = win
    elo     : pre-game rating from POSTGAME leaderboard block (may be None)

    Raises on malformed / unreadable file — let callers handle exceptions.
    """
    filepath = str(filepath)

    with open(filepath, 'rb') as f:

        # ── Header ────────────────────────────────────────────────────────────
        try:
            h = fast_header_parse(f)
        except RuntimeError:
            import traceback
            log.error('mgz-fast header parse failed in parse_replay (Linux binary issue?):\n%s',
                      traceback.format_exc())
            raise RuntimeError(
                'mgz-fast could not parse this replay header. '
                'The file may use a newer AoE2 DE patch format unsupported on Linux. '
                'Please try a different replay file.'
            )
        de     = h.get('de') or {}
        map_id = de.get('rms_map_id')
        rated  = de.get('rated', False)

        header_players = {p['number']: p for p in (h.get('players') or [])
                          if p and p.get('type') == 1}
        de_players     = {p['number']: p for p in (de.get('players') or [])
                          if p.get('number', -1) >= 1}

        # ── Feature init ──────────────────────────────────────────────────────
        player_stats = defaultdict(lambda: {
            'villagers_dark_age': 0,    'villagers_feudal_age': 0,
            'villagers_castle_age': 0,  'villagers_imperial_age': 0,
            'mil_trained_dark_age': 0,  'mil_trained_feudal_age': 0,
            'mil_trained_castle_age': 0, 'mil_trained_imperial_age': 0,
            'apm_dark_age': 0,          'apm_feudal_age': 0,
            'apm_castle_age': 0,        'apm_imperial_age': 0,
            'gather_point_count': 0,
            'wall_count': 0,
            'move_count': 0, 'order_count': 0, 'stance_count': 0, 'ungarrison_count': 0,
            'first_wall_min': None, 'resign_time_min': None, 'resigned': False,
            'market_min': None, 'market_count': 0,
            **{v: None for v in TRACKED_BUILDINGS.values()},
            **{v: None for v in TRACKED_TECHS.values()},
            'thresholds': {
                'feudal_complete':   float('inf'),
                'castle_complete':   float('inf'),
                'imperial_complete': float('inf'),
            },
            'military_buildings_placed': defaultdict(int),
        })

        leaderboard_ratings = {}
        game_time_ms        = 0
        world_time_ms       = None

        # ── Body scan ─────────────────────────────────────────────────────────
        meta(f)
        eof = os.fstat(f.fileno()).st_size

        while f.tell() < eof:
            try:
                op_type, payload = operation(f)
            except EOFError:
                break

            if op_type == Operation.SYNC:
                game_time_ms += payload[0]
                continue

            if op_type == Operation.ACTION:
                action_type, ap = payload
                pid = ap.get('player_id')
                if not pid:
                    continue

                t   = round(game_time_ms / 60000, 2)
                s   = player_stats[pid]
                thr = s['thresholds']
                act = action_type.name if hasattr(action_type, 'name') else str(action_type)

                if   t < thr['feudal_complete']:   phase = 'dark_age'
                elif t < thr['castle_complete']:   phase = 'feudal_age'
                elif t < thr['imperial_complete']: phase = 'castle_age'
                else:                              phase = 'imperial_age'

                if act == 'RESIGN':
                    if not s['resigned']:
                        s['resigned']        = True
                        s['resign_time_min'] = t

                elif act == 'RESEARCH':
                    tech = ap.get('technology_id')
                    if tech == 101:   thr['feudal_complete']   = t + 2.16
                    elif tech == 102: thr['castle_complete']   = t + 2.66
                    elif tech == 103: thr['imperial_complete'] = t + 3.16
                    if tech in TRACKED_TECHS and s[TRACKED_TECHS[tech]] is None:
                        s[TRACKED_TECHS[tech]] = t

                elif act in ('BUILD', 'WALL'):
                    bid = ap.get('building_id')
                    if bid in TRACKED_BUILDINGS:
                        s['military_buildings_placed'][bid] += 1
                        feat = TRACKED_BUILDINGS[bid]
                        if s[feat] is None:
                            s[feat] = t
                    elif bid in WALL_IDS:
                        s['wall_count'] += 1
                        if s['first_wall_min'] is None:
                            s['first_wall_min'] = t
                    elif bid in MARKET_IDS:
                        s['market_count'] += 1
                        if s['market_min'] is None:
                            s['market_min'] = t

                if act in ('MOVE', 'ORDER', 'STANCE', 'BUILD', 'RESEARCH',
                           'DE_QUEUE', 'GATHER_POINT', 'DE_TRANSFORM'):
                    s[f'apm_{phase}'] += 1

                    if act == 'DE_QUEUE':
                        uid    = ap.get('unit_id')
                        amount = ap.get('amount', 1) or 1
                        if uid in VILLAGER_IDS:
                            s[f'villagers_{phase}'] += amount
                        else:
                            s[f'mil_trained_{phase}'] += amount
                    elif act == 'GATHER_POINT': s['gather_point_count'] += 1
                    elif act == 'MOVE':         s['move_count']         += 1
                    elif act == 'ORDER':        s['order_count']        += 1
                    elif act == 'STANCE':       s['stance_count']       += 1
                    elif act == 'UNGARRISON':   s['ungarrison_count']   += 1

            elif op_type == Operation.POSTGAME:
                world_time_ms = payload.get('world_time')
                for lb in (payload.get('leaderboards') or []):
                    if lb.get('id') == RM_1V1_LEADERBOARD_ID:
                        for entry in (lb.get('players') or []):
                            leaderboard_ratings[entry['number']] = entry['rating']
                break

    duration_min     = round((world_time_ms or game_time_ms) / 60000, 2)
    num_real_players = len(header_players)

    # result: resigned = loss, other = win
    losers = {pid for pid, s in player_stats.items() if s['resigned']}

    # Elo: POSTGAME slots are 0-indexed; header player_nums are 1-indexed.
    # Fix from DEC-007: use pnum - 1 as the POSTGAME key (slot offset).
    for pid, s in player_stats.items():
        s['result'] = 0 if pid in losers else 1
        s['elo']    = leaderboard_ratings.get(pid - 1)  # DEC-007 slot offset

    return {
        'filepath':     filepath,
        'map_id':       map_id,
        'rated':        rated,
        'num_players':  num_real_players,
        'duration_min': duration_min,
        'de_players':   de_players,
        'player_stats': dict(player_stats),
    }


def flatten_player_row(game, player_num):
    """
    Convert one player's stats dict to a flat row dict for the batch CSV pipeline.
    Used in 02_bulk_parsing_new.ipynb — not needed by the API directly.
    """
    s  = dict(game['player_stats'][player_num])
    dp = game['de_players'].get(player_num, {})

    profile_id  = dp.get('profile_id')
    player_name = dp.get('name', '')
    civ_id      = dp.get('civilization_id') or dp.get('civ_id')
    is_me       = (player_name in MY_PLAYER_NAME)

    mbp             = dict(s.pop('military_buildings_placed', {}))
    market_count    = s.pop('market_count', 0)
    building_counts = {name: mbp.get(bid, 0) for bid, name in BUILDING_COUNT_MAP.items()}
    building_counts['market_count'] = market_count

    s.pop('thresholds', None)
    s.pop('resigned', None)
    s.pop('resign_time_min', None)

    return {
        'filepath':        game['filepath'],
        'map_id':          game['map_id'],
        'rated':           game['rated'],
        'num_players':     game['num_players'],
        'duration_min':    game['duration_min'],
        'player_num':      player_num,
        'profile_id':      profile_id,
        'player_name':     player_name,
        'civilization_id': civ_id,
        'is_me':           is_me,
        **s,
        **building_counts,
    }
