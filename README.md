# EloCoach

**Upload an Age of Empires II replay, get three specific things to work on.**

EloCoach parses an `.aoe2record` replay, measures 70 in-game decisions as differences between the two players, runs them through a trained XGBoost win-probability model, and returns the coaching points where the model says the decision matters *and* the player is measurably behind.

🔗 **[Live demo](https://personalized-elo-coach.onrender.com)** — free tier, first request may take ~30s to wake.

[![tests](https://github.com/herculesli/Personalized-Elo-Coach/actions/workflows/tests.yml/badge.svg)](https://github.com/herculesli/Personalized-Elo-Coach/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue)

<!-- TODO: add a screenshot or GIF of the analysis output here — this is the highest-value thing missing -->

---

## The problem

Post-game screens tell a player *what happened* — villager counts, resources collected, army size. They don't say which of those numbers actually cost the game, or which are within a normal range for that player's level. Coaching content is generic; personal coaching is expensive.

EloCoach answers a narrower question: **given how this specific game was played, which decisions had the most influence on the outcome, and which of those is this player worst at?**

## How it works

```
.aoe2record  →  parse  →  70 delta features  →  XGBoost  →  win probability
                                    ↓                            ↓
                          percentile vs. training      SHAP feature importance
                          population (weakness)                  ↓
                                    └──────────  rank  ──────────┘
                                                  ↓
                                    top 3 coaching recommendations
```

**Delta features, not raw stats.** Every feature is *coached player minus opponent* — Feudal Age timing difference, villager-idle-time difference, and so on. Models trained on individual player stats scored below 0.60 AUC; game outcomes depend on relative performance, not absolute numbers. Switching to deltas is what made the model work.

**Ranking by importance × weakness.** A recommendation surfaces only when both conditions hold: SHAP says the feature drives win probability, *and* the player sits in a weak percentile for it. A player who is already top-decile at Castle Age timing doesn't get told to click up faster.

## Results

| | AUC |
|---|---|
| Logistic regression baseline | 0.510 |
| XGBoost (5-fold CV) | 0.696 |
| **XGBoost (held-out test)** | **0.753** |

Trained on 194 parsed 1v1 Arabia replays → 141 games (~350 player rows) after filtering for rated games, complete outcome labels, and valid Elo.

**This is a small dataset and the README should say so.** ~350 rows is enough to find directional signal, not enough for reliable per-segment estimates — which is exactly why Elo-bracket cohort modeling was cut (see DESIGN.md, DEC-003 and DEC-009).

## Tech stack

| Layer | Tools |
|---|---|
| **API** | FastAPI, Uvicorn, Starlette |
| **Replay parsing** | `mgz`, `mgz-fast`, `construct` |
| **ML** | XGBoost 3.2, scikit-learn, SHAP |
| **Data** | pandas, NumPy |
| **Frontend** | Static HTML/CSS/JS |
| **Deploy** | Render (Nixpacks + Procfile), Python 3.11 |
| **CI** | GitHub Actions — pytest + separate model-quality job |

## Engineering decisions worth reading

The reasoning is logged in [`DESIGN.md`](DESIGN.md) (10 decisions) and [`ISSUES.md`](ISSUES.md) (11 issues). Three that mattered most:

- **[DEC-010] Rejected rate-normalized features** (`commands_per_min` and similar). Dividing by game duration reintroduces target leakage through the back door — losing players resign earlier, so duration is partly *caused* by the outcome. Dropped the collinear duration proxies instead.
- **[DEC-008] Left timing columns as `NaN` rather than imputing.** A missing `castle_min` means the player never clicked up — a real, distinct signal. Imputing with game duration fabricates "clicked up at the last second" and destroys the difference between *researched late* and *never researched*. XGBoost learns the split direction for NaN natively.
- **[ISSUE-003] Found and fixed a systematic Elo swap.** The post-game leaderboard block is 0-indexed while the replay header is 1-indexed, so every game had both players' ratings transposed. Fixed with a slot offset after verifying against raw replay bytes.

## Repository layout

```
src/          parser, feature engineering, model inference, coaching logic
app/          FastAPI backend + static frontend
notebooks/    01 exploration → 07 iteration (parsing, EDA, modeling, SHAP)
models/       trained model + percentile distributions
tests/        35 tests (API contract + pipeline)
docs/adr/     architecture decision records
DESIGN.md     design decisions with rationale and rejected alternatives
ISSUES.md     bug log with root causes
CONTEXT.md    domain glossary
```

## Run locally

```bash
git clone https://github.com/herculesli/Personalized-Elo-Coach.git
cd Personalized-Elo-Coach
python -m venv .venv && source .venv/bin/activate    # Python 3.11
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000` and upload a replay. A sample is included at `data/sample_replays/`.

**Endpoints**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Model status + training metadata |
| `POST` | `/analyze` | Upload `.aoe2record` → JSON coaching report |

## Limitations

- **1v1 Arabia only.** Other maps and team games are out of scope; the feature set assumes a standard 1v1 opening.
- **Small, narrow training set.** 141 games between Elo 1484–1898, drawn from one player's match history. Recommendations are least reliable outside that band.
- **Percentiles are population-wide, not Elo-bracketed.** With ~350 rows, splitting by Elo left segments too small for stable estimates (DEC-003, DEC-009).
- **Correlation, not causation.** SHAP explains what drives the *model's* prediction, not what would happen if a player changed that behavior.

## License

MIT — see [LICENSE](LICENSE).
