# Design Decisions Log

Format for each entry:
- **ID**: DEC-001
- **Date**: YYYY-MM-DD
- **Decision**: What was decided
- **Rationale**: Why this choice was made
- **Alternatives considered**: What was rejected and why
- **Impact**: What this affects downstream

---

## DEC-001
- **ID**: DEC-001
- **Date**: 2026-05-13
- **Decision**: Defer `Action.TRAIN` (military unit training timestamp) from MVP feature set
- **Rationale**: Adding it requires re-running the 24-minute bulk parse, updating the parser, and re-saving the CSV. The derived feature (`military_response_time = first military unit - feudal time`) is a proxy that likely adds little signal beyond feudal time alone for v1.
- **Alternatives considered**: Add TRAIN to `scan_body()` now — rejected because it blocks model progress with no guaranteed payoff
- **Impact**: `military_response_time` feature not available in v1. Re-add in v2 if model needs more signal.

---

## DEC-002
- **ID**: DEC-002
- **Date**: 2026-05-13
- **Decision**: Drop 19 rows with null `resign_player` / `resign_time_min`
- **Rationale**: These games ended by disconnect or timeout — no RESIGN action was recorded, so `result` (win/loss) is unknown. They cannot be used as labeled training data.
- **Alternatives considered**: Impute result from leaderboard delta — rejected, unreliable and adds complexity
- **Impact**: Dataset reduces from 194 to ~175 games (~350 player rows)

---

## DEC-003
- **ID**: DEC-003
- **Date**: 2026-05-13
- **Decision**: Use under/above 1400 Elo as the two cohort split instead of 1000–1200 / 1200–1400 / 1400–1600 brackets
- **Rationale**: Only 194 personal games available — not enough to populate three meaningful cohorts. Under/above 1400 gives two cohorts with sufficient samples and maps cleanly to "earlier you" vs "later you" across your Elo progression.
- **Alternatives considered**: Three-bracket split (1000–1200 / 1200–1400 / 1400–1600) — rejected, too few games per bracket. Community replay data would be needed for this.
- **Impact**: Cohort analysis compares your own performance at different skill stages rather than across players. Visualization in Section 7 will show what changed as you crossed 1400.

---

## DEC-004
- **ID**: DEC-004
- **Date**: 2026-05-13
- **Decision**: Use `MY_PROFILE_ID = 3134896` to tag which player row is the user in each game
- **Rationale**: Player number (1 or 2) is assigned randomly by lobby slot — unreliable for identifying the user. `profile_id` is stable across all replays.
- **Alternatives considered**: Match by player name — rejected, names can change. Match by player number — rejected, not deterministic.
- **Impact**: Each game produces 2 player rows; `is_me` flag tags which row belongs to the user. Coach output uses only `is_me == True` rows.

---

## DEC-005
- **ID**: DEC-005
- **Date**: 2026-05-13
- **Decision**: `map_id`, `rated`, `num_players` not saved in `parsed_replays.csv` — added back as constants in feature engineering
- **Rationale**: These fields were used as filters in the bulk parser but not included in `scan_body()` return dict. All 194 games passed those filters so values are known constants (Arabia=9, rated=True, num_players=2).
- **Alternatives considered**: Re-run bulk parse with these fields included — rejected, not worth 24 min re-parse for fields with no variance
- **Impact**: These columns added back with constant values in `03_feature_engineering.ipynb`
