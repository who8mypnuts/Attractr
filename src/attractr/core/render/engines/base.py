"""Engine interface.  An engine turns :class:`RenderSettings` into a :class:`RenderResult`
(accumulation only — development is a separate stage)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.jobs.cancel import NEVER, CancelToken
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.result import RenderResult
from attractr.core.render.settings import RenderSettings

PassSink = Callable[[RenderResult, float], None]


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
    ) -> RenderResult: ...

    def close(self) -> None:  # release GPU contexts etc.
        return None
