# `src/` is not an installable package

`src/` and `app/` are plain directories imported as `src.*` and `app.*` from the
repository root, not an installable distribution. `pyproject.toml` therefore
declares no `[project]` table and no build backend; tests import the code via
pytest's `pythonpath = ["."]` rather than `pip install -e .`.

This is deliberate. Renaming `src/` into a real package would rewrite every
import in `src/`, `app/`, `tests/`, `scripts/` and all seven notebooks, and the
notebooks are primary sources for how the model was built. The churn was not
worth it at the point this decision was made.

Revisit if the project ever needs to be installed as a dependency elsewhere, or
if the notebooks stop being load-bearing.
