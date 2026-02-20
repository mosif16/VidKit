#!/usr/bin/env python3
"""Run baseline local generation + benchmarks for CogVideoX-2B."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.video_generation import generate_cogvideox, result_to_dict


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default="/Users/homer1/.openclaw/workspace/outbox")
    p.add_argument("--report", default="/Users/homer1/.openclaw/workspace/memory/autonomous/cogvideox-benchmark-baseline.json")
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    prompt = "Cinematic short vertical video: sunrise over Manhattan skyline, smooth camera motion, realistic lighting, high detail."

    configs = [
        {"name": "quick", "steps": 6, "frames": 12, "width": 320, "height": 240, "fps": 8},
        {"name": "quality", "steps": 10, "frames": 16, "width": 384, "height": 256, "fps": 8},
    ]

    runs = []
    for cfg in configs:
        out_path = out_dir / f"cogvideox2b_{cfg['name']}.mp4"
        res = generate_cogvideox(
            prompt=prompt,
            output_path=out_path,
            num_inference_steps=cfg["steps"],
            num_frames=cfg["frames"],
            width=cfg["width"],
            height=cfg["height"],
            fps=cfg["fps"],
        )
        data = result_to_dict(res)
        data["name"] = cfg["name"]
        data["sec_per_step"] = round(res.inference_seconds / cfg["steps"], 3)
        data["sec_per_frame"] = round(res.inference_seconds / max(1, res.frames), 3)
        runs.append(data)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model": "THUDM/CogVideoX-2b",
        "runs": runs,
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
