"""Shared standalone-runner used by each module's ``run.py``.

Every sub-group needs the same thing: run MY module alone, against the standard
mock input, print what it produced, and save the result so it can be compared
across experiments. Writing that five times would guarantee five slightly
different versions, so it lives here once.

    python module_sg2/run.py                      # run against mock input
    python module_sg2/run.py --dump results/run01.json
    python module_sg2/run.py --config configs/experiment_a.yaml
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common.config import load_config
from common.jsonio import write_sequence
from common.timing import Stopwatch
from interfaces.contracts import validate

MOCK_DIR = Path(__file__).resolve().parents[1] / "interfaces" / "mock"


def _summarise(payloads: list[Any]) -> dict[str, Any]:
    """Headline numbers. Deliberately generic -- works for any payload type."""
    n = len(payloads)
    valid = [p for p in payloads if p.valid]
    out: dict[str, Any] = {
        "frames": n,
        "valid": len(valid),
        "invalid": n - len(valid),
    }
    reasons: dict[str, int] = {}
    for p in payloads:
        if not p.valid:
            reasons[p.reason] = reasons.get(p.reason, 0) + 1
    if reasons:
        out["invalid_reasons"] = reasons

    for field in ("ear", "mar", "perclos", "drowsy_score", "confidence"):
        vals = [getattr(p, field) for p in valid if getattr(p, field, None) is not None]
        if vals:
            out[field] = {"min": round(min(vals), 4), "max": round(max(vals), 4),
                          "mean": round(sum(vals) / len(vals), 4)}
    for field in ("blink_event", "yawn_event", "alert"):
        if valid and hasattr(valid[0], field):
            out[field + "_count"] = sum(1 for p in valid if getattr(p, field))
    if valid and hasattr(valid[0], "state"):
        counts: dict[str, int] = {}
        for p in payloads:
            counts[p.state.value] = counts.get(p.state.value, 0) + 1
        out["states"] = counts
    return out


def run_module(
    *,
    name: str,
    build,
    mock_input: str,
    call,
    default_config: Path,
    argv: list[str] | None = None,
) -> int:
    """Drive one module over a mock input sequence.

    name          : display name, e.g. "SG-2 Eye State"
    build          : (config dict) -> the module instance
    mock_input     : which mock file feeds this module, e.g. "mock_face.json"
    call           : (module, payload, index) -> output payload
    default_config : the module's configs/default.yaml
    """
    ap = argparse.ArgumentParser(description=f"Run {name} standalone against mock input.")
    ap.add_argument("--config", type=Path, default=default_config,
                    help=f"YAML config (default: {default_config.name})")
    ap.add_argument("--input", type=Path, default=MOCK_DIR / mock_input,
                    help=f"input sequence (default: interfaces/mock/{mock_input})")
    ap.add_argument("--dump", type=Path, default=None, help="write outputs to this JSON file")
    ap.add_argument("--limit", type=int, default=None, help="stop after N frames")
    ap.add_argument("--verbose", action="store_true", help="print every frame")
    args = ap.parse_args(argv)

    if not args.input.exists():
        print(f"input not found: {args.input}\n"
              f"run: python interfaces/mock/generate_mocks.py")
        return 2

    cfg = {}
    if args.config and Path(args.config).exists():
        cfg = load_config(args.config)

    from interfaces.contracts import from_dict
    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    inputs = [from_dict(x) for x in raw]
    if args.limit:
        inputs = inputs[: args.limit]

    module = build(cfg)
    if hasattr(module, "reset"):
        module.reset()

    timer = Stopwatch(name)
    outputs = []
    violations: list[str] = []
    for i, payload in enumerate(inputs):
        with timer:
            result = call(module, payload, i)
        outputs.append(result)
        errs = validate(result)
        if errs:
            violations.append(f"frame {result.frame_id}: {'; '.join(errs)}")
        if args.verbose:
            print(f"  {i:4d} valid={result.valid!s:<5} {result.reason or ''}")

    print(f"{name}")
    print(f"  config : {args.config}")
    print(f"  input  : {args.input.name}  ({len(inputs)} frames)")
    print(f"  timing : {json.dumps(timer.summary())}")
    print(f"  summary: {json.dumps(_summarise(outputs), indent=2)}")
    if violations:
        print(f"  CONTRACT VIOLATIONS: {len(violations)}")
        for v in violations[:10]:
            print(f"    ! {v}")
    else:
        print("  contract: OK, 0 violations")

    if args.dump:
        write_sequence(args.dump, outputs)
        print(f"  wrote  : {args.dump}")

    return 1 if violations else 0
