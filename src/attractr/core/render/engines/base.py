"""Engine interface.  An engine turns :class:`RenderSettings` into a :class:`RenderResult`
(accumulation only — development is a separate stage)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.jobs.cancel import NEVER, CancelToken
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.checkpoint import Checkpoint
from attractr.core.render.result import Framing, RenderResult
from attractr.core.render.settings import RenderSettings

PassSink = Callable[[RenderResult, float], None]
SEED_SEGMENT_STRIDE = 1_000_003  # trajectory-seed offset per resumed segment


@dataclass
class ResumePlan:
    """What an engine must do differently when continuing from a checkpoint."""

    budget: int  # iterations still to accumulate (per tile for tiled renders)
    seed: int  # trajectory seed for this segment
    framing: Framing | None = None  # forced framing (None → compute as usual)
    skip_tiles: int = 0
    checkpoint: Checkpoint | None = None

    def finish(self, result: RenderResult) -> RenderResult:
        """Fold the checkpoint's buffers into a freshly accumulated (partial or final) result."""
        if self.checkpoint is not None:
            self.checkpoint.merge_into(result, final=result.complete)
        return result


def resume_plan(budget: int, seed: int, resume: Checkpoint | None) -> ResumePlan:
    if resume is None:
        return ResumePlan(budget, seed)
    seg_seed = (seed + SEED_SEGMENT_STRIDE * resume.segment) & 0x7FFFFFFF
    if resume.uniform:
        return ResumePlan(max(0, budget - resume.iterations_done), seg_seed, resume.framing, 0, resume)
    return ResumePlan(budget, seg_seed, resume.framing, resume.tiles_done, resume)


@dataclass
class EngineCaps:
    id: str
    name: str
    device: str = ""
    available: bool = True
    fp64: bool = True
    compute: bool = False
    max_size: int = 32768
    mpts_per_second: float = 0.0  # micro-benchmark result
    notes: list[str] = field(default_factory=list)


class Engine(ABC):
    id: str = "base"
    name: str = "Base"

    @abstractmethod
    def probe(self) -> EngineCaps: ...

    @abstractmethod
    def accumulate(
        self,
        settings: RenderSettings,
        spec: AttractorSpec,
        *,
        sink: PassSink | None = None,
        cancel: CancelToken = NEVER,
        tracker: ProgressTracker | None = None,
        resume: Checkpoint | None = None,
    ) -> RenderResult: ...

    def supports(self, spec: AttractorSpec) -> bool:
        """False when this engine cannot run the program (the selector then skips it)."""
        return True

    def close(self) -> None:  # release GPU contexts etc.
        return None
