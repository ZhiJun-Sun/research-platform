#!/usr/bin/env python3
"""Small real training entrypoint used by HydroLab end-to-end acceptance.

The important integration rule is that every artifact is written below
HYDROLAB_OUTPUT_DIR (or the equivalent --output-dir template argument).  The
imported code directory can therefore stay read-only in the Docker runner.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def output_root(cli_value: str | None) -> Path:
    configured = cli_value or os.environ.get("HYDROLAB_OUTPUT_DIR")
    if not configured:
        raise SystemExit("HYDROLAB_OUTPUT_DIR or --output-dir is required")
    root = Path(configured).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir")
    parser.add_argument("--experiment", default=os.environ.get("HYDROLAB_EXPERIMENT", "smoke"))
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--model", default="smoke")
    parser.add_argument("--id", default="smoke-basin")
    args = parser.parse_args()

    root = output_root(args.output_dir) / "experiments" / args.experiment
    result_dir = root / "results" / "smoke"
    checkpoint_dir = root / "checkpoints"
    config_dir = root / "configs"
    for directory in (result_dir, checkpoint_dir, config_dir):
        directory.mkdir(parents=True, exist_ok=True)

    loss = 1.0
    for epoch in range(1, args.epochs + 1):
        loss *= 0.5
        print(f"Epoch {epoch}/{args.epochs} loss={loss:.4f}", flush=True)

    metrics = {"Avg": {"RMSE": loss, "MAE": loss / 2, "NSE": 1 - loss, "KGE": 1 - loss / 2}}
    (result_dir / "smoke.json").write_text(json.dumps(metrics), encoding="utf-8")
    (result_dir / "predictions.csv").write_text("time,observed,predicted\n0,1.0,0.9\n", encoding="utf-8")
    (result_dir / "training.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (checkpoint_dir / "smoke.pth").write_bytes(b"hydrolab-smoke-checkpoint")
    (config_dir / "run.json").write_text(
        json.dumps({"epochs": args.epochs, "experiment": args.experiment}),
        encoding="utf-8",
    )
    print(f"artifacts={root}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
