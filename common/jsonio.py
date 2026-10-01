"""Read/write sequences of contract payloads as JSON.

Used by the mock replay path, by each module's ``run.py --dump``, and by
evaluation. Keeping it in one place means every ``results/*.json`` in the repo
has the same shape and ``evaluation/`` can read any of them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from interfaces.contracts import from_dict, to_dict


def write_sequence(path: str | Path, payloads: list[Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([to_dict(p) for p in payloads], indent=1) + "\n",
                    encoding="utf-8")
    return path


def read_sequence(path: str | Path) -> list[Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [from_dict(x) for x in raw]
