# Personalized-Elo-Coach

EloCoach is a data-driven coaching web application for Age of Empires II Definitive Edition. Players upload a replay file, and the site parses it, computes 70 in-game delta features (my stat minus opponent stat for every key in-game decision), runs it through a trained XGBoost classifier, and returns the top N coaching recommendations ranked by model importance × player weakness.

## Install

```
pip install -r requirements.txt
```

## Run

```
uvicorn app.main:app --reload
```

## Test

```
pytest
```

Model-quality checks over the full training set are marked `slow` and excluded by default — run them explicitly with `pytest -m slow`.

## More context

- [`DESIGN.md`](DESIGN.md) — design decisions log
- [`CONTEXT.md`](CONTEXT.md) — domain glossary
- [`docs/adr/`](docs/adr/) — architecture decision records
- [`ISSUES.md`](ISSUES.md) — problem/fix log
