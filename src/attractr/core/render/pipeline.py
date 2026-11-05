"""High-level render entry points used by the CLI, the GUI and the animator."""

from __future__ import annotations

import logging
from dataclasses import replace

from attractr.core.attractors.registry import registry
from attractr.core.attractors.spec import AttractorSpec, spec_from_source
from attractr.core.color.palettes import palettes
from attractr.core.jobs.cancel import NEVER, Cancelled, CancelToken
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.camera import Camera
from attractr.core.render.checkpoint import Checkpoint
from attractr.core.render.develop.developer import Developed, develop
from attractr.core.render.engines import selector
from attractr.core.render.engines.base import Engine, PassSink
from attractr.core.render.result import RenderResult
from attractr.core.render.settings import Look, Quality, RenderSettings

log = logging.getLogger(__name__)


def resolve_spec(settings: RenderSettings) -> AttractorSpec:
    """Inline DSL source wins over the registry id."""
    if settings.source:
        return spec_from_source(settings.source, id=settings.attractor or None)
    return registry.get(settings.attractor)


def default_settings(spec: AttractorSpec, quality: Quality | None = None, look: Look | None = None) -> RenderSettings:
    """Sensible starting settings for an attractor: its default camera, palette and style."""
    yaw, pitch, roll, zoom = spec.camera
    cam = Camera.from_euler(yaw, pitch, roll, zoom=zoom)
    if look is None:
        look = Look(style=spec.style if spec.style in ("gas", "dust", "light", "liquid", "solid", "plasma") else "gas")
        if spec.palette in palettes:
            look = replace(look, gradient=palettes.get(spec.palette))
    return RenderSettings(
        attractor=spec.id,
        source=None if spec.builtin else spec.source,
        params=tuple(spec.default_params().items()),
        camera=cam,
        quality=quality or Quality(),
        look=look,
    )


def accumulate(
    settings: RenderSettings,
    *,
    engine: Engine | str | None = None,
    purpose: str = "final",
    cancel: CancelToken = NEVER,
    tracker: ProgressTracker | None = None,
    sink: PassSink | None = None,
    resume: Checkpoint | None = None,
) -> RenderResult:
    """``resume``: continue from a saved checkpoint (see :mod:`attractr.core.render.checkpoint`);
    ``cancel.finish()`` stops accumulation early but still returns a complete result."""
    spec = resolve_spec(settings)
    if isinstance(engine, str):
        eng = selector.select(engine, purpose, spec)
    elif engine is None:
        eng = selector.select(settings.quality.engine, purpose, spec)
    else:
        eng = engine
    q = settings.quality
    log.info("render %s: %d×%d ss%d, %.3g M points, engine %s, resume %s", spec.id, q.width, q.height, q.supersample,
             spec.iteration_budget(q.iterations) / 1e6, eng.id, f"{resume.fraction:.0%}" if resume else "no")
    last_partial: list[RenderResult] = []

    def remember(result: RenderResult, fraction: float) -> None:
        """Forward partials to the caller's sink and keep the last uniform one for a CPU continuation."""
        if not result.complete and result.stats.tiles_done == 0:
            last_partial[:] = [result]  # a uniform partial: what a CPU fallback can continue from
        if sink is not None:
            sink(result, fraction)

    try:
        return eng.accumulate(settings, spec, sink=remember, cancel=cancel, tracker=tracker, resume=resume)
    except Cancelled:
        raise
    except MemoryError:
        raise
    except Exception as exc:  # noqa: BLE001 — a GPU failure must never lose the render
        if eng.id == "cpu" or (resume is not None and not resume.uniform):
            raise
        log.warning("engine %s failed (%s: %s); continuing on the CPU engine", eng.id, type(exc).__name__, exc)
        cont = resume
        done_note = ""
        if last_partial:  # keep what the GPU accumulated: continue from it instead of starting over
            cont = Checkpoint.from_result(last_partial[0], segment=(resume.segment + 1) if resume else 1)
            done_note = f" {cont.fraction:.0%} of the budget was kept from the GPU partial."
        if tracker is not None:
            tracker.update(None, f"{eng.id} failed — continuing on CPU", force=True)
        cpu = selector.get_engine("cpu")
        result = cpu.accumulate(settings, spec, sink=sink, cancel=cancel, tracker=tracker, resume=cont)
        result.stats.notes.append(f"GPU engine {eng.id} failed ({type(exc).__name__}: {exc}); rendered on CPU instead.{done_note}")
        return result


def render(
    settings: RenderSettings,
    *,
    engine: Engine | str | None = None,
    purpose: str = "final",
    cancel: CancelToken = NEVER,
    tracker: ProgressTracker | None = None,
    sink: PassSink | None = None,
) -> tuple[RenderResult, Developed]:
    """Accumulate and develop in one call: ``(result, developed image)``."""
    result = accumulate(settings, engine=engine, purpose=purpose, cancel=cancel, tracker=tracker, sink=sink)
    return result, develop(result, settings.look)
