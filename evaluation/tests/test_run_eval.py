"""Smoke test for the real-data evaluation harness.

Proves the methodology runs end to end on the synthetic sample and writes a metrics
file with the fields a Week-3 report needs. It is NOT an accuracy test -- the mock is
synthetic (see datasets/README.md), so it only checks the harness mechanics.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.run_eval import evaluate_manifest, main

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "datasets" / "manifests" / "sample_mock.json"
MOCK_FACE = ROOT / "interfaces" / "mock" / "mock_face.json"


def test_sample_manifest_exists():
    assert SAMPLE.exists(), "the runnable sample manifest must ship with the harness"


def test_evaluate_manifest_scores_the_sample():
    if not MOCK_FACE.exists():
        pytest.skip("mock data not generated; run interfaces/mock/generate_mocks.py")
    report = evaluate_manifest(SAMPLE)

    assert report["per_clip"], "harness produced no per-clip results"
    assert report["graded_accuracy"] is False, "the mock sample must never be graded accuracy"

    clip = report["per_clip"][0]
    assert clip["synthetic"] is True
    assert clip["frames"] == 300
    assert clip["contract_violations"] == 0
    assert not clip["module_errors"]
    # Every Week-3 headline metric must be present...
    for k in ("recall", "precision", "f1", "mean_alert_latency_s", "false_alarms_per_hour"):
        assert k in clip
    # ...and on the clean synthetic clip the one drowsy episode is caught with no
    # false alarm. (A value check of the mechanics, not a graded accuracy claim.)
    assert clip["recall"] == 1.0
    assert clip["false_positives"] == 0


def test_run_eval_writes_a_metrics_file(tmp_path):
    if not MOCK_FACE.exists():
        pytest.skip("mock data not generated; run interfaces/mock/generate_mocks.py")
    out = tmp_path / "eval.json"
    rc = main(["--manifest", str(SAMPLE), "--out", str(out)])
    assert rc == 0
    assert out.exists(), "run_eval must write the metrics file it was asked for"

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["manifest"] == "sample_mock"
    assert data["aggregate"]["clips"] == 1
    assert data["aggregate"]["recall"] == 1.0


def test_missing_real_clips_are_skipped_not_crashed(tmp_path):
    """A manifest naming a clip that is not on this machine must skip it cleanly,
    so the harness still runs when the gitignored real videos are absent."""
    manifest = tmp_path / "absent.json"
    manifest.write_text(json.dumps({
        "name": "absent", "split": "test",
        "clips": [{"file": "datasets/clips/does_not_exist.mp4",
                   "ground_truth": {"drowsy_episodes_s": [[1.0, 2.0]]}}],
    }), encoding="utf-8")
    report = evaluate_manifest(manifest)
    assert report["skipped"], "an absent clip must be reported as skipped"
    assert report["per_clip"] == []
