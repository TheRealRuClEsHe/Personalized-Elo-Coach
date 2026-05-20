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
- **Date**: 2026-05-13 (revised 2026-05-17)
- **Decision**: Drop cohort split for v1 — analyze all 141 games as one group
- **Rationale**: All recorded games are above 1400 (range 1484–1898). A 1600 threshold gives only 7 games below — too few for any meaningful comparison. A balanced split (median ~1790) has no strategic meaning. There is not enough data spread across skill levels to make cohort analysis useful. Revisit in v2 if early-career replays are added.
- **Alternatives considered**: 1400 threshold — rejected, no games below it. 1600 threshold — semantically meaningful but yields only 7 games below, unusable. Balanced median split — rejected, arbitrary boundary.
- **Impact**: No cohort column in v1 outputs. All 141 my-games rows treated as a single group for visualization and model training.

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

---

## DEC-006
- **ID**: DEC-006
- **Date**: 2026-05-17
- **Decision**: Missing Elo filter applied in `03_feature_engineering.ipynb`, not in the bulk parser
- **Rationale**: Notebook 02 filters determine *which games are worth parsing* (map, rated, 1v1, duration — checked before or during body scan). Notebook 03 filters determine *which parsed rows are usable as training data*. Missing Elo is a post-parse quality check — the game was valid and parsed, but the POSTGAME block yielded no rating. Same category as the null `resign_player` drop already in Section 2 of notebook 03.
- **Alternatives considered**: Add missing Elo check to bulk parser Phase 3 — rejected, the bulk parser took 24 minutes and re-running it to filter 2 rows is not worth it.
- **Impact**: 2 rows dropped in notebook 03 Section 2, alongside the null `resign_player` drop.

---

## DEC-007
- **ID**: DEC-007
- **Date**: 2026-05-17
- **Decision**: Fix Elo mis-assignment in `match_ratings()` using a slot offset (`pnum - 1`) rather than keying by `profile_id`
- **Rationale**: POSTGAME leaderboard entries use 0-indexed player numbers (0, 1) while header `de_players` uses 1-indexed numbers (1, 2). The original elimination approach incorrectly matched POSTGAME key `1` to header player `1`, swapping both Elos every game. The POSTGAME payload contains no `profile_id` field, so direct profile-based matching is not possible without a re-parse. The offset `lb.get(pnum - 1)` is structurally consistent — verified against raw replay data for `AgeIIDE_Replay_322460723.aoe2record` (POSTGAME key 1 = header player 2 = TheRealRuClEsHe).
- **Alternatives considered**: Key `leaderboard_ratings` by `profile_id` in the bulk parser and re-parse — rejected because POSTGAME entries lack `profile_id`; a re-parse would not solve the ambiguity. Keep elimination approach — rejected, it systematically swaps Elos in every game (ISSUE-003).
- **Impact**: `match_ratings()` in `03_feature_engineering.ipynb` (cell `9f98dd05`) replaced with `{pnum: lb.get(pnum - 1) for pnum in player_nums}`. No re-parse needed. Logged as ISSUE-003.

---

## DEC-008
- **ID**: DEC-008
- **Date**: 2026-05-20
- **Decision**: Leave `_min` timing columns as `NaN` rather than imputing with `duration_min`
- **Rationale**: XGBoost natively handles missing values by learning the optimal branch direction for NaN rows at each split during tree training. A NaN in `castle_min` correctly encodes "player never clicked up" — which is a distinct, meaningful signal. Imputing with `duration_min` fabricates a timing value ("clicked up at the last second"), which corrupts the learned split thresholds and destroys the distinction between "researched late" and "never researched."
- **Alternatives considered**: Impute with `duration_min` — rejected, structurally inaccurate and misleads the model. Impute with column mean — rejected, same problem at population scale. Drop rows with any null — rejected, would eliminate ~50% of the dataset since most games end before Imperial Age techs are researched.
- **Impact**: `_min` columns in `features.csv` retain NaN where the action did not occur. Section 3 (imputation) removed from `03_feature_engineering.ipynb`. XGBoost trained directly on this data with no preprocessing step for these columns.

---

## DEC-009
- **ID**: DEC-009
- **Date**: 2026-05-20
- **Decision**: No Elo-based cohort splits for modeling — `elo` retained as metadata only, not a model feature
- **Rationale**: Dataset has ~350 rows spanning Elo ~1484–1898. Splitting into Elo cohorts produces segments of ~140–175 rows each — too small for XGBoost to learn reliable patterns, and SHAP values extracted from such small samples carry high variance. `elo` is also excluded as a model feature because it is not tactically actionable: including it would dominate SHAP values with "have a higher Elo" — which is not a coaching signal. The goal is to isolate macro/timing decisions the player can actually change.
- **Alternatives considered**: Two cohorts by median Elo split — rejected, halves effective training data. Three cohorts (low/mid/high) — rejected, segment sizes ~100 rows each, too small. Include `elo` as model feature — rejected, summarizes historical skill, not current tactical decisions; would suppress real coaching signals in SHAP output.
- **Impact**: One model trained on full dataset. `elo` kept in `features.csv` for EDA reference and post-modeling coaching context (e.g., bracket comparisons) but excluded from the model feature matrix `X`. Every row must have a valid `elo` value — null Elo rows dropped in notebook 03.

---

## DEC-010
- **ID**: DEC-010
- **Date**: 2026-05-20
- **Decision**: Do not convert raw count features to rate-based features (e.g., `move_commands_per_min`). Drop `duration_min`, `apm_castle_age`, and `apm_imperial_age` from the model feature matrix instead.
- **Rationale**: Rate normalization (count / duration_min) reintroduces target leakage through the back door — `duration_min` was dropped precisely because game length is partially caused by outcome (losing players resign earlier, shortening the game). Any feature derived by dividing by `duration_min` inherits that leakage. Additionally, age-specific count features (e.g., `mil_trained_castle_age`) would require time-spent-in-that-age as the denominator, which is not tracked — dividing by total game duration produces a meaningless ratio. Finally, XGBoost is tree-based and makes threshold splits that naturally handle duration-skewed counts through feature interactions; the scaling benefits of rate normalization apply to linear and distance-based models, not gradient-boosted trees.
- **Alternatives considered**: Convert all full-game count features to rates — rejected, reintroduces `duration_min` leakage. Convert only age-specific counts — rejected, wrong denominator (time-in-age not tracked). No action — rejected, `duration_min`, `apm_castle_age`, `apm_imperial_age` are collinear proxies that add noise.
- **Impact**: `duration_min`, `apm_castle_age`, and `apm_imperial_age` remain in `features.csv` for EDA reference but are excluded from the model feature matrix `X` in notebook 05. Rate-based features deferred to v2 if a linear model is introduced.
