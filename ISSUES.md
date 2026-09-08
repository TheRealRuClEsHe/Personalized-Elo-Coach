# Project Issues Log

Format for each entry:
- **ID**: ISSUE-001
- **Date**: YYYY-MM-DD
- **Problem**: What broke / what was the symptom
- **Proposed fix**: What we tried
- **Method**: Commands, code changes, configs applied
- **Result**: Worked / partially worked / failed + why
- **Tags**: #python #data #pipeline etc.

---

## ISSUE-001
- **ID**: ISSUE-001
- **Date**: 2026-05-13
- **Problem**: Bulk parsing 3627 `.aoe2record` files estimated to take 23+ hours. Single file body scan takes ~23s due to pure Python loop over tens of thousands of SYNC operations. Full parse on every file before applying any filters wasted time on team games and non-Arabia replays.
- **Proposed fix**: Two-stage optimization — (1) header-first filtering to skip body scan on files that fail map/rated/num_players filter; (2) multiprocessing for body scans on remaining ~300 qualifying files.
- **Method**: Split `parse_replay()` into `parse_header(f)` and `parse_body(f)`. Header parse measured at 0.06s avg / 0.23s max across 20 files. Body scan still ~23s per qualifying game. Multiprocessing across 12 cores (user's machine) pending implementation.
- **Result**: RESOLVED — `ProcessPoolExecutor` crashed on Windows/Jupyter (`OSError: handle is closed`, no `__main__` guard). Switched to `ThreadPoolExecutor` which works in Jupyter. Phase 1 (header scan): 1377.9s. Phase 2 (body scan, 12 threads): 66.8s — 12x speedup confirmed. Total: 24 min. 194 games kept, 0 body errors. Results cached to `data/parsed_replays.csv` — one-time cost.
- **Tags**: #performance #parsing #multiprocessing #pipeline #windows

---

## ISSUE-002
- **ID**: ISSUE-002
- **Date**: 2026-05-13
- **Problem**: `ProcessPoolExecutor` crashes in Jupyter on Windows with `OSError: handle is closed`. Windows requires a `if __name__ == '__main__':` guard when spawning new processes, which Jupyter notebooks cannot provide.
- **Proposed fix**: Replace `ProcessPoolExecutor` with `ThreadPoolExecutor`.
- **Method**: One-line swap in `cell-bulk-parse`. Threads share the same process so no `__main__` guard needed. File I/O and zlib decompression release Python's GIL so threads give real speedup despite the GIL.
- **Result**: RESOLVED — body scan dropped from ~115 min sequential to 66.8s with 12 threads.
- **Tags**: #windows #multiprocessing #jupyter #GIL

---

## ISSUE-003
- **ID**: ISSUE-003
- **Date**: 2026-05-17
- **Problem**: `match_ratings()` in `03_feature_engineering.ipynb` silently swapped Elos between players. POSTGAME leaderboard uses 0-indexed player numbers (0, 1) while header `de_players` uses 1-indexed player numbers (1, 2). The function's direct-match step found POSTGAME key `1` when looking up header player `1`, assigning the wrong player's rating. E.g. TheRealRuClEsHe (header player 2, POSTGAME key 1) received rating 1665 instead of 1715 in the first cross-checked game.
- **Proposed fix**: Replace the direct-match-then-elimination logic with a single offset lookup: `lb.get(pnum - 1)` for each header player number.
- **Method**: Edited cell `9f98dd05` in `03_feature_engineering.ipynb`. Replaced 10-line elimination function with one-liner `{pnum: lb.get(pnum - 1) for pnum in player_nums}`.
- **Result**: RESOLVED — confirmed correct. POSTGAME leaderboard uses 0-indexed 
  numbers (0, 1); header players use 1-indexed (1, 2). `lb.get(pnum - 1)` correctly 
  maps header player 1 → POSTGAME number 0, header player 2 → POSTGAME number 1. 
  Verified by inspecting raw POSTGAME block: `{'number': 0, 'rating': 1893}, 
  {'number': 1, 'rating': 1895}`.
- **Tags**: #data #feature-engineering #elo #bug

---

## ISSUE-004
- **ID**: ISSUE-004
- **Date**: 2026-05-19
- **Problem**: `wall_count` is 0 for all 377 rows, `market_count` is 0 for all rows, and `first_wall_min` is 100% null in `parsed_replays.csv`. BUILD action tracking for WALL_IDS `{72, 117, 155}` and market building ID `137` never fires. All other tracked buildings (barracks=12, archery=87, stable=101, blacksmith=103) show realistic non-zero values, confirming the BUILD action parsing itself works — the IDs for walls and market are simply wrong or DE uses a different action type for walls.
- **Proposed fix**: (1) Audit all unique `building_id` values that actually appear in BUILD actions across parsed replays to find the correct DE IDs. (2) Check whether DE wall placement uses a separate `WALL` action type rather than `BUILD`. (3) Correct `WALL_IDS` and market ID in `02_bulk_parsing_new.ipynb`, then re-run Phase 2 only.
- **Method**: PENDING — need to add a BUILD action audit spike before fixing.
- **Result**: PENDING
- **Tags**: #data #parsing #building-ids #walls #feature-engineering

---

## ISSUE-005
- **ID**: ISSUE-005
- **Date**: 2026-05-19
- **Problem**: `is_me` column is all `False` in `parsed_replays.csv`. `player_name` is stored as `"b'TheRealRuClEsHe'"` (Python bytes repr) instead of `"TheRealRuClEsHe"` (decoded string), so `player_name == MY_PLAYER_NAME` always evaluates to `False`.
- **Proposed fix**: In `flatten_player_row()` in `02_bulk_parsing_new.ipynb`, decode bytes before comparison: `if isinstance(player_name, bytes): player_name = player_name.decode('utf-8', errors='replace')`.
- **Method**: Changed `MY_PLAYER_NAME` from a single string to a set containing both the raw string and the bytestring repr: `MY_PLAYER_NAME = {'TheRealRuClEsHe', "b'TheRealRuClEsHe'"}`. Updated the `is_me` check to use `in` instead of `==`.
- **Result**: RESOLVED — implemented by user directly in notebook 02 setup cell.
- **Tags**: #data #parsing #player-name #bytes #feature-engineering

---

## ISSUE-006
- **ID**: ISSUE-006
- **Date**: 2026-05-20
- **Problem**: Both models in `05_modeling.ipynb` scored below the AUC < 0.60 stop threshold (LR: 0.5722, XGBoost: 0.5396 — effectively random). Diagnostic checklist cleared leakage (no suspect columns in X) and volume (280 training rows > 250 threshold). Root cause: the feature matrix is built from individual player rows in isolation. A `feudal_min` of 8.5 minutes is a win if the opponent clicked up at 9.2 and a loss if they clicked up at 7.8. The absolute value carries no learnable signal — what determines the outcome is the relative gap between the two players. Since the model never sees both rows from the same game simultaneously, there is no pattern to learn from absolute individual stats at this Elo range (1484–1898) where both players' metrics heavily overlap.
- **Proposed fix**: Restructure `features.csv` from two rows per game (one per player) to one row per game using within-game deltas. For each game, pair the two player rows, compute `my_stat - opponent_stat` for every feature, and use `did_i_win` as the label. This gives the model a learnable signal: "when your feudal time is 45 seconds faster than your opponent's, you tend to win." Add a restructuring cell to `03_feature_engineering.ipynb` that reads `parsed_replays.csv`, pairs rows by game, computes deltas, and saves `data/features_delta.csv`. Retrain both models on the new format.
- **Method**: Added Section 5 and 6 to `03_feature_engineering.ipynb`. For each game grouped by `filepath`, paired player_num=1 and player_num=2 rows, computed `p1_stat - p2_stat` for all numeric feature columns, kept `result = int(p1_result)` as label. Saved output to `data/features_delta.csv` (one row per game). Updated `04_eda.ipynb` to read `features_delta.csv` for distribution plots, heatmap (top 25 by Cohen's d), and effect size ranking. Updated `05_modeling.ipynb` to train LR + XGBoost on delta columns only. Fixed `np.percentile` crash on all-NaN columns with empty-array guard.
- **Result**: RESOLVED — XGBoost AUC jumped from 0.5396 to **0.753** with delta features. LR remained near-random (0.510), confirming the signal is non-linear. Model saved to `models/elocoach_model.pkl`. Cohort distributions saved to `models/cohort_distributions.pkl`. SHAP analysis and coaching recommendations implemented in `06_shap_analysis.ipynb`.
- **Tags**: #modeling #feature-engineering #data-structure #auc #diagnosis #resolved
---

## ISSUE-007
- **ID**: ISSUE-007
- **Date**: 2026-05-21
- **Problem**: `POST /analyze` returns 422 with `ValueError: DataFrame.dtypes for data must be int, float, bool or category. Invalid columns: first_stable_min_delta: object, double_bit_axe_min_delta: object, ...` when uploading a real replay. Root cause: `build_delta_row()` returns `None` (Python None) for techs that were never researched in the game. When these are assembled into a dict and passed to `pd.DataFrame([row])`, Pandas infers object dtype for any column whose only value is `None`. XGBoost's `predict_proba` rejects object-dtype columns.
- **Proposed fix**: In `predict_win_prob()`, replace Python `None` with `float('nan')` before constructing the DataFrame. `float('nan')` is a float, so Pandas infers float64 dtype, which XGBoost accepts. XGBoost handles NaN natively (DEC-008).
- **Method**: Rewrote the row-building step in `src/model.py::predict_win_prob()`: `row = {col: (float(delta_dict[col]) if delta_dict.get(col) is not None else float('nan')) for col in feature_cols}`. Removed downstream `.astype(float)` call (not needed with this approach). File written via bash heredoc to avoid Windows-mount encoding corruption that caused null bytes in earlier write attempts.
- **Result**: RESOLVED -- `predict_win_prob()` now handles all-None rows correctly. Confirmed with test: 30+ None-valued delta features, win probability returned as 0.832 without error. All 34 tests pass.
- **Tags**: #api #fastapi #xgboost #dtype #none #nan #inference

---

## ISSUE-008
- **ID**: ISSUE-008
- **Date**: 2026-05-22
- **Problem**: `POST /analyze` returns 422 with `RuntimeError: could not parse:` for replay file `AgeIIDE_Replay_479421981.aoe2record` (4285 KB). Fails in 16ms on Railway (Linux), parses fine locally (Windows). Root cause narrowed down: failure is in mgz-fast's compiled C extension (`fast_header_parse`), before the body scan starts. The file IS a valid 1v1 Arabia game (confirmed by local parse: players [1,2], map_id 9). This is a Linux vs Windows binary incompatibility in mgz-fast 1.0.0 -- the .so on Linux handles this file differently than the .pyd on Windows. Python version is now confirmed to be 3.11.15 on Railway (nixpacks.toml fix worked), ruling out Python 3.13 as the cause. Pinning construct==2.8.16 also did not fix it.
- **Proposed fix**: (1) Add full traceback logging to `run_pipeline` and `parse_header`/`parse_replay` so the exact failing line in mgz-fast is visible in Railway logs. (2) Investigate pure-mgz fallback (no C extension) or newer mgz-fast release. (3) Short-term: show user a clear error message identifying the file as unsupported format.
- **Method**: Deployed traceback logging. Railway logs confirmed exact failure: `mgz/fast/header.py line 46, in de_string: assert data.read(2) == b'\x60\x0a'` -- `AssertionError`. Discovered the local venv contains an EXTENDED header.py (982 lines) vs the PyPI build (768 lines) with per-save-version byte-skip logic (`save >= 66.3`, `save >= 67.2`, etc.) that handles newer AoE2 DE patch formats. The PyPI wheel and local wheel are both labeled 1.0.0 but contain different code. Fix: vendored the local header.py as `src/mgz_fast_header.py` and replaced the installed module at startup in `app/main.py` using `importlib.util.spec_from_file_location` before any src imports run.
- **Result**: RESOLVED -- vendored header deployed and confirmed working. AgeIIDE_Replay_479421981.aoe2record now parses correctly on Railway: LOSS, Elo 2686 vs 2818, 31.5 min, win probability 19.4%, coaching recommendations returned successfully.
- **Tags**: #parsing #mgz #compatibility #production #linux #c-extension

---

## ISSUE-009
- **ID**: ISSUE-009
- **Date**: 2026-05-25
- **Problem**: `VILLAGER_ID = 83` only tracks male villagers. Female villagers use unit ID `293` and are produced by certain civilizations (Aztecs always produce female; other civs may alternate). Any game where a player uses such a civ results in undercounted `villagers_{phase}` stats, potentially zeroing out the villager count entirely for that player. This silently corrupts V1 training data and will also affect the upcoming V2 TC idle time calculation.
- **Proposed fix**: Replace the scalar `VILLAGER_ID = 83` with a set `VILLAGER_IDS = {83, 293}` and update the DE_QUEUE check from `uid == VILLAGER_ID` to `uid in VILLAGER_IDS`.
- **Method**: Two edits to `src/parser.py`: (1) line 32 — changed constant to `VILLAGER_IDS = {83, 293}`; (2) line 236 — changed condition to `if uid in VILLAGER_IDS`. Bug discovered during V2 feature feasibility audit (notebook 07_v2_tc_vill_idle) while inspecting the AoE2 unit reference table.
- **Result**: RESOLVED — both edits applied. Note: existing `parsed_replays.csv` and trained model were built with the old constant. Villager counts for Aztec/female-vill civ matchups are undercounted in the current dataset. Impact on model AUC is unknown but likely small given Aztec is one civ of many. Will be corrected automatically when bulk parse is re-run for V2.
- **Tags**: #parsing #villager #bug #data #feature-engineering #v2

---

## ISSUE-010
- **ID**: ISSUE-010
- **Date**: 2026-09-07
- **Problem**: `tests/` contained 444 lines across two files but **zero `def test_` functions and zero `assert` statements**. Both files were top-to-bottom print scripts built around a `check(label, condition)` helper that appended failures to an `errors` list and printed ✓/✗. Because all work happened at module level, pytest executed everything (including loading both `.pkl` artifacts and running inference over `features_delta.csv`) during *collection*, then collected no tests. A regression printed ✗ and the suite still reported success. Both files also began with `sys.path.insert(0, repo_root)`. Compounding this, `tests/test_src_pipeline.py` imported `VILLAGER_ID` from `src.parser`, but ISSUE-009 renamed that constant to `VILLAGER_IDS`; the import raised, was swallowed by a bare `except`, and the module then died with `NameError: MY_PROFILE_ID is not defined`. The file had been dead since ISSUE-009 and nothing reported it. There was also no CI, so nothing ran the suite at all.
- **Proposed fix**: Add `pyproject.toml` with `pythonpath = ["."]` to remove the path hacks, a `conftest.py` holding session-scoped fixtures so artifacts load once and only on demand, and convert each `check()` call into a real assertion inside a `def test_*` function. Curate rather than port 1:1: drop tautologies (`check(..., True)`), bare count assertions, and any test pinning `MY_PROFILE_ID`, which the player-identity work will delete. Quarantine the `accuracy > 0.70` model-quality gate behind a `slow` marker so it stays out of the edit loop. Add GitHub Actions to actually run it.
- **Method**: Added `pyproject.toml` (pytest config + PEP 735 `[dependency-groups]`, no `[project]` table — see ADR-0001). Added `tests/conftest.py` with session-scoped `artifacts`/`model`/`distributions`/`client`/`parsed_sample` fixtures and a `mock_game` fixture using arbitrary profile IDs (111/222) rather than the production constant. Rewrote both test files as 37 assertion-based tests. Committed `data/sample_replays/AgeIIDE_Replay_456895186.aoe2record` and added a `.gitignore` negation, since a blanket `*.aoe2record` rule would otherwise have silently excluded it; the previously dead "live replay" sections now run against it instead of a hardcoded Windows path. Rebuilt `.venv` on Python 3.11.15 (it was a broken 3.9.6 venv with no interpreter binary).
- **Result**: RESOLVED — 36 tests pass in 2.6s for the default run, 1 slow test passes in 8.0s. Previously: 0 tests collected, 1 collection error, 43.75s.
- **Tags**: #testing #pytest #ci #tooling #regression #tech-debt

---

## ISSUE-011
- **ID**: ISSUE-011
- **Date**: 2026-09-07
- **Problem**: The vendored mgz-fast header fix from ISSUE-008 was applied by monkey-patching `sys.modules['mgz.fast.header']` inside `app/main.py` at import time. Only the ASGI entrypoint applied it, so every other caller — `tests/`, `scripts/`, the notebooks — imported the **unpatched** PyPI parser while `src/parser.py`'s own docstring claimed it was "import-safe ... without side effects." Confirmed empirically on a fresh 3.11 venv: PyPI `mgz-fast` 1.0.0 installs a 767-line header versus the 982-line vendored copy, and `from src.parser import parse_replay` on a real replay failed with `RuntimeError: could not parse` while the same replay parsed fine through `app/main.py`. This made end-to-end parser coverage impossible from tests.
- **Proposed fix**: Move the patch behind the parser's own seam. A new `src/mgz_compat.py` applies the replacement on import; `src/parser.py` imports it ahead of its own `mgz` imports. Remove the block from `app/main.py`.
- **Method**: Added `src/mgz_compat.py` exposing `apply()` and applying on import. Added `import src.mgz_compat` to `src/parser.py` above the `from mgz.fast import ...` lines, with a comment explaining the ordering requirement, and deleted the stale comment pointing at `main.py`. Removed the 12-line patch block plus the now-unused `importlib.util` and `sys` imports from `app/main.py`.
- **Result**: RESOLVED — `from src.parser import parse_replay` now parses the sample replay with no entrypoint involvement (map_id 9, 45.5 min). Every caller gets the same parser as production.
- **Tags**: #parsing #mgz #seam #architecture #import-safety

---

## ISSUE-012
- **ID**: ISSUE-012
- **Date**: 2026-09-07
- **Problem**: `/improve-codebase-architecture`'s report flagged repo layout contradictions (candidate C6): `.gitignore` claimed `models/*.pkl` was ignored while both `.pkl` files were deliberately tracked for Railway deploy; a stray `pytest-cache-files-skjyc6kr/` was committed despite the `pytest-cache*/` gitignore rule; generated plots were split across `plots/` and `data/plots/` with no single source of truth; `requirements-dev.txt` was a 136-line raw `pip freeze` dump made redundant by `pyproject.toml`'s `[dependency-groups]` (added in ISSUE-010); `sanity_check.py` was an orphaned Week-1 environment check superseded by the real test suite; and `README.md` was 2 lines with no install/run/test instructions.
- **Proposed fix**: Drop the false `models/*.pkl` gitignore rule; untrack the stray pytest cache directory; merge `data/plots/` into `plots/`; delete `requirements-dev.txt` and `sanity_check.py`; rewrite `README.md` with a real quickstart linking `DESIGN.md`/`CONTEXT.md`/`docs/adr/`/`ISSUES.md`.
- **Method**: Edited `.gitignore` to remove the `models/*.pkl` line. Ran `git rm -r --cached pytest-cache-files-skjyc6kr/`. Ran `git mv` on all 6 files from `data/plots/` into `plots/`. Ran `git rm requirements-dev.txt sanity_check.py`. Rewrote `README.md` with install/run/test sections and links to the other docs. Verified no Python code referenced either plots directory before merging, and no other file referenced `sanity_check.py`, before deleting.
- **Result**: RESOLVED — confirmed via `git status`/`git ls-files` that the moves/deletes match the plan, and `pytest` (36 passed, 1 slow deselected) still passes against `.venv-1` (Python 3.11.15) after the changes.
- **Tags**: #hygiene #gitignore #docs #tooling #architecture-review
