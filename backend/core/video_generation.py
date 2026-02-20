"""Local video generation helpers (CogVideoX baseline)."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import time
import torch

from diffusers import CogVideoXPipeline
from diffusers.utils import export_to_video


@dataclass
class CogVideoXResult:
    model: str
    device: str
    dtype: str
    load_seconds: float
    inference_seconds: float
    total_seconds: float
    frames: int
    fps: int
    width: int
    height: int
    output_path: str
    output_size_bytes: int


def _pick_device_and_dtype() -> tuple[str, torch.dtype]:
    # MPS is available on Apple Silicon but CogVideoX path is typically most stable on float32.
    if torch.backends.mps.is_available():
        return "mps", torch.float32
    if torch.cuda.is_available():
        return "cuda", torch.float16
    return "cpu", torch.float32


def generate_cogvideox(
    *,
    prompt: str,
    output_path: str | Path,
    model_id: str = "THUDM/CogVideoX-2b",
    negative_prompt: str = "blurry, low quality, watermark, text artifacts",
    num_inference_steps: int = 12,
    num_frames: int = 24,
    width: int = 720,
    height: int = 480,
    fps: int = 8,
    guidance_scale: float = 6.0,
    use_dynamic_cfg: bool = True,
) -> CogVideoXResult:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    device, dtype = _pick_device_and_dtype()

    load_t0 = time.time()
    pipe = CogVideoXPipeline.from_pretrained(model_id, torch_dtype=dtype)
    load_seconds = time.time() - load_t0

    pipe = pipe.to(device=device, dtype=dtype)
    try:
        pipe.enable_attention_slicing()
    except Exception:
        pass

    if device == "mps":
        try:
            torch.mps.empty_cache()
        except Exception:
            pass

    inf_t0 = time.time()
    out = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        num_inference_steps=num_inference_steps,
        num_frames=num_frames,
        guidance_scale=guidance_scale,
        use_dynamic_cfg=use_dynamic_cfg,
        width=width,
        height=height,
    )
    inference_seconds = time.time() - inf_t0

    frames = out.frames[0]
    export_to_video(frames, str(output), fps=fps)

    if device == "mps":
        try:
            torch.mps.empty_cache()
        except Exception:
            pass

    total_seconds = time.time() - t0

    return CogVideoXResult(
        model=model_id,
        device=device,
        dtype=str(dtype).replace("torch.", ""),
        load_seconds=round(load_seconds, 3),
        inference_seconds=round(inference_seconds, 3),
        total_seconds=round(total_seconds, 3),
        frames=len(frames),
        fps=fps,
        width=width,
        height=height,
        output_path=str(output),
        output_size_bytes=output.stat().st_size,
    )


def result_to_dict(result: CogVideoXResult) -> dict:
    return asdict(result)
