# watcher.tracer.trajectory
## @lineage: phase.watcher.tracer.trajectory
## @lineage: meta.watcher.tracer.trajectory
## @lineage: phase.receptor.tracer.trajectory
## @lineage: cognitive.receptor.tracer.trajectory
import numpy as np
import datetime
import uuid
from typing import List, Dict, Any, Callable
from dataclasses import dataclass
from abc import ABC, abstractmethod
from watcher.tracer.metrics import (
    trend_slope,
    acceleration,
    range_amplitude,
    path_length,
    mean_crossings,
    signal_energy,
    volatility,
    drawdown,
    skewness
)

@dataclass
class Point:
    timestamp: datetime.datetime
    value: float


@dataclass
class ContinuousTrajectory:
    """Ψ(t): continuous temporal trajectory"""
    identity: str
    points: List[Point]


@dataclass
class WindowedTrajectory:
    """∂Φ: window-projected trajectory"""
    identity: str
    start_time: datetime.datetime
    end_time: datetime.datetime
    points: List[Point]

class BaseBoundLensStrategy(ABC):
    @abstractmethod
    def scan(self, window: WindowedTrajectory) -> Dict[str, Any]:
        pass

class DefaultBoundLensStrategy(BaseBoundLensStrategy):
    """Φ′ evaluator"""

    METRICS_REGISTRY: Dict[str, Callable[[np.ndarray], float]] = {
        "trend": trend_slope,
        "acceleration": acceleration,
        "range": range_amplitude,
        "path_length": path_length,
        "crossings": mean_crossings,
        "energy": signal_energy,
        "volatility": volatility,
        "drawdown": drawdown,
        "skewness": skewness
    }

    PRESETS = {
        "kinematic": ["trend", "acceleration", "range", "volatility"],
        "topology": ["path_length", "crossings", "energy", "volatility"],
        "tail_risk": ["drawdown", "skewness", "volatility", "range"]
    }

    def __init__(self, preset_name: str = "tail_risk"):
        if preset_name not in self.PRESETS:
            raise ValueError(f"Unknown preset: {preset_name}")
        self.preset_name = preset_name
        self.active_metrics = self.PRESETS[preset_name]

    def scan(self, window: WindowedTrajectory) -> Dict[str, Any]:
        values = np.array([p.value for p in window.points])
        if values.size < 3:
            return {
                "status": "insufficient_data",
                "preset": self.preset_name
            }

        computed = {}
        for name in self.active_metrics:
            func = self.METRICS_REGISTRY[name]
            computed[name] = func(values)

        return {
            "status": "valid",
            "preset": self.preset_name,
            "metrics": computed
        }

class WindowStrategy(ABC):
    @abstractmethod
    def generate(self, trajectory: ContinuousTrajectory) -> List[WindowedTrajectory]:
        pass

class SlidingWindowStrategy(WindowStrategy):
    def __init__(self, window_days: int, step_days: int):
        self.window_delta = datetime.timedelta(days=window_days)
        self.step_delta = datetime.timedelta(days=step_days)

    def generate(
        self,
        trajectory: ContinuousTrajectory
    ) -> List[WindowedTrajectory]:

        points = trajectory.points
        if not points:
            return []

        start = points[0].timestamp
        end = points[-1].timestamp
        windows = []
        current = start
        while current + self.window_delta <= end:
            next_time = current + self.window_delta
            segment = [p for p in points if current <= p.timestamp < next_time]
            windows.append(
                WindowedTrajectory(
                    identity=trajectory.identity,
                    start_time=current,
                    end_time=next_time,
                    points=segment
                )
            )
            current += self.step_delta

        return windows


class WindowProjector:
    """Ψ → ∂Φ"""
    def __init__(self, strategy: WindowStrategy):
        self.strategy = strategy

    def project(self, trajectory: ContinuousTrajectory) -> List[WindowedTrajectory]:
        return self.strategy.generate(trajectory)
