"""ffmpeg discovery and frame-sequence encoding with progress."""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

PRESETS = {
    "h264": {"label": "H.264 MP4 (compatible)", "ext": ".mp4", "args": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "{crf}", "-preset", "slow", "-movflags", "+faststart"]},
    "h265": {"label": "H.265 / HEVC MP4 (smaller)", "ext": ".mp4", "args": ["-c:v", "libx265", "-pix_fmt", "yuv420p", "-crf", "{crf}", "-preset", "medium", "-tag:v", "hvc1"]},
    "prores": {"label": "ProRes 422 HQ MOV (editing)", "ext": ".mov", "args": ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"]},
    "vp9": {"label": "VP9 WebM (web)", "ext": ".webm", "args": ["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-crf", "{crf}", "-b:v", "0"]},
    "gif": {"label": "GIF (palette-optimised)", "ext": ".gif", "args": []},
    "png_only": {"label": "PNG frames only (no video)", "ext": "", "args": []},
}


def find_ffmpeg(preferred: str | None = None) -> str | None:
    for cand in ([preferred] if preferred else []) + ["ffmpeg"]:
        if cand and shutil.which(cand):
            return shutil.which(cand)
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


@dataclass
class EncodeResult:
    path: Path
    command: list[str]
    log: str


def encode(frames_pattern: str, fps: int, out: Path, preset: str = "h264", crf: int = 18, ffmpeg: str | None = None,
           frame_count: int | None = None, on_progress: Callable[[int], None] | None = None, extra_args: list[str] | None = None) -> EncodeResult:
    """``frames_pattern`` is an ffmpeg image pattern such as ``frames/anim_%04d.png``."""
    exe = find_ffmpeg(ffmpeg)
    if exe is None:
        raise FileNotFoundError("ffmpeg not found — install it or set its path in Preferences")
    spec = PRESETS[preset]
    if preset == "gif":
        filt = f"fps={fps},split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4"
        cmd = [exe, "-y", "-framerate", str(fps), "-i", frames_pattern, "-vf", filt, "-loop", "0", str(out)]
    else:
        args = [a.replace("{crf}", str(crf)) for a in spec["args"]]
        cmd = [exe, "-y", "-framerate", str(fps), "-i", frames_pattern, *args, *(extra_args or []), "-r", str(fps), str(out)]
    log_lines: list[str] = []
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    assert proc.stdout is not None
    for line in proc.stdout:
        log_lines.append(line.rstrip())
        m = re.search(r"frame=\s*(\d+)", line)
        if m and on_progress:
            on_progress(int(m.group(1)))
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n" + "\n".join(log_lines[-15:]))
    return EncodeResult(out, cmd, "\n".join(log_lines))
