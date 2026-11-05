"""Host-memory estimate for a render (used by the render dialog and the job pre-flight)."""

from __future__ import annotations

from attractr.core.render.accumulators import needs_for
from attractr.core.render.settings import RenderSettings


def estimate_host_bytes(settings: RenderSettings) -> int:
    """Rough peak host memory of accumulating + developing ``settings``: the full-size
    accumulation copies (supersampled, one float32 plane per needed buffer), one output-
    resolution snapshot (partials / checkpoints) and the float RGBA develop buffers."""
    q = settings.quality
    ss = max(1, int(q.supersample))
    planes = needs_for(settings.look).buffer_count
    full = q.width * q.height * ss * ss * 4 * planes
    snapshot = q.width * q.height * 4 * planes * 2
    develop = q.width * q.height * 4 * 4 * 3
    return full + snapshot + develop


def available_host_bytes() -> int | None:
    """Free host RAM in bytes, or ``None`` when psutil is unavailable."""
    try:
        import psutil

        return int(psutil.virtual_memory().available)
    except Exception:  # noqa: BLE001
        return None


def memory_warning(settings: RenderSettings) -> str:
    """Empty string when the render fits comfortably, else a human-readable warning."""
    need = estimate_host_bytes(settings)
    avail = available_host_bytes()
    if avail is None or need < 0.6 * avail:
        return ""
    return (f"⚠ this render needs ≈ {need / 2**30:.1f} GB of RAM for its buffers, {avail / 2**30:.1f} GB is free — "
            "lower the supersampling or size, or close other programs")
