"""
Shared fixtures.

Artifacts load once per session rather than at import time, so collecting the
suite costs nothing and a test that does not need the model does not pay for
it.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest

from src.parser import TRACKED_BUILDINGS, TRACKED_TECHS, ARABIA_MAP_ID
from src.model import load_artifacts

REPO = Path(__file__).parent.parent
MODEL_DIR = REPO / 'models'
DATA_DIR = REPO / 'data'

SAMPLE_REPLAY = DATA_DIR / 'sample_replays' / 'AgeIIDE_Replay_456895186.aoe2record'

# The coached player in the sample replay. A property of that recording, not
# of the application's default identity.
SAMPLE_COACHED_PROFILE_ID = 3134896
SAMPLE_OPPONENT_PROFILE_ID = 1655684


@pytest.fixture(scope='session')
def artifacts():
    """(model, distributions) loaded once for the whole session."""
    return load_artifacts(MODEL_DIR)


@pytest.fixture(scope='session')
def model(artifacts):
    return artifacts[0]


@pytest.fixture(scope='session')
def distributions(artifacts):
    return artifacts[1]


@pytest.fixture(scope='session')
def features_delta_csv():
    """Path to the training delta features used by the model-quality check."""
    path = DATA_DIR / 'features_delta.csv'
    if not path.exists():
        pytest.skip(f'{path} not present')
    return path


@pytest.fixture(scope='session')
def sample_replay():
    """The committed sample replay, skipping if it is absent."""
    if not SAMPLE_REPLAY.exists():
        pytest.skip(f'{SAMPLE_REPLAY} not present')
    return SAMPLE_REPLAY


@pytest.fixture(scope='session')
def parsed_sample(sample_replay):
    """parse_replay() output for the sample replay, parsed once."""
    from src.parser import parse_replay
    return parse_replay(str(sample_replay))


@pytest.fixture(scope='session')
def client():
    """TestClient with the app's lifespan run, so the model is loaded."""
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def _player_stats(*, feudal, castle, villagers, result, elo):
    """One player's stats block, with every tracked timing defaulted to None."""
    stats = {
        'villagers_dark_age': villagers, 'villagers_feudal_age': villagers,
        'villagers_castle_age': 0, 'villagers_imperial_age': 0,
        'mil_trained_dark_age': 0, 'mil_trained_feudal_age': 2,
        'mil_trained_castle_age': 0, 'mil_trained_imperial_age': 0,
        'apm_dark_age': 100, 'apm_feudal_age': 150,
        'apm_castle_age': 0, 'apm_imperial_age': 0,
        'gather_point_count': 10, 'wall_count': 0,
        'move_count': 80, 'order_count': 30, 'stance_count': 5,
        'ungarrison_count': 0,
        'first_wall_min': None, 'market_min': None, 'market_count': 0,
        'imperial_min': None,
        'feudal_min': feudal, 'castle_min': castle,
        'result': result, 'elo': elo,
        'military_buildings_placed': defaultdict(int, {12: 1}),
    }
    for col in list(TRACKED_TECHS.values()) + list(TRACKED_BUILDINGS.values()):
        stats.setdefault(col, None)
    stats['feudal_min'] = feudal
    stats['castle_min'] = castle
    return stats


@pytest.fixture
def mock_game():
    """
    A two-player game with player 1 as the coached player.

    Player 1 is faster to both ages and two villagers ahead, so every delta
    has a known sign.
    """
    return {
        'filepath': 'mock.aoe2record',
        'map_id': ARABIA_MAP_ID,
        'rated': True,
        'num_players': 2,
        'duration_min': 25.0,
        'de_players': {
            1: {'profile_id': 111, 'name': 'Coached', 'civilization_id': 18},
            2: {'profile_id': 222, 'name': 'Opponent', 'civilization_id': 5},
        },
        'player_stats': {
            1: _player_stats(feudal=10.5, castle=18.0, villagers=22, result=1, elo=1750),
            2: _player_stats(feudal=11.0, castle=19.0, villagers=20, result=0, elo=1780),
        },
    }
