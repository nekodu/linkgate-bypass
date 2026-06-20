#!/usr/bin/env python3
"""İnce sarmalayıcı: gerçek mantık linkgate paketinde.

Kullanım:
    python scripts/bypass.py https://ay.live/dzpal2
    python scripts/bypass.py https://ay.live/dzpal2 --engine fast --no-proxy
    python scripts/bypass.py --batch links.txt --json --check
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from linkgate.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
