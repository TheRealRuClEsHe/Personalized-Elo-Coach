"""
src/mgz_compat.py -- Compatibility shim for mgz-fast.

mgz-fast 1.0.0 on PyPI ships a header parser that rejects replays saved by
newer AoE2 DE patches: it raises AssertionError in de_string on the marker
bytes, surfacing as "could not parse" (ISSUE-008). A build of the same
version number carries an extended header with per-save-version byte-skip
logic; that file is vendored here as mgz_fast_header.py.

Importing this module replaces mgz.fast.header with the vendored copy. It
must happen before anything imports mgz.fast.header, so src/parser.py
imports it first, ahead of its own mgz imports.

This lives beside the parser rather than in an entrypoint so that every
caller -- the API, the tests, the scripts, the notebooks -- parses replays
the same way. Applying it in app/main.py alone left every other caller with
the unpatched parser.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_VENDORED_HEADER = Path(__file__).parent / 'mgz_fast_header.py'


def apply() -> bool:
    """Install the vendored header as mgz.fast.header. Returns True if applied."""
    if not _VENDORED_HEADER.exists():
        return False

    spec = importlib.util.spec_from_file_location('mgz.fast.header', _VENDORED_HEADER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules['mgz.fast.header'] = module
    return True


applied = apply()
