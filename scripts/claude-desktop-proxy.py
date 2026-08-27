#!/usr/bin/env python3
"""Thin shim — delegates to claude_desktop_proxy package."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from claude_desktop_proxy.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
