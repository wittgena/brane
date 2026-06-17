# watcher.tracer.metrics
## @lineage: phase.watcher.tracer.metrics
## @lineage: meta.watcher.tracer.metrics
## @lineage: phase.receptor.tracer.metrics
## @lineage: cognitive.receptor.tracer.metrics
import numpy as np

## Kinematic (운동학)
def trend_slope(values: np.ndarray) -> float:
    """1차 속도 (Velocity)"""
    return float(np.polyfit(range(len(values)), values, 1)[0])

def acceleration(values: np.ndarray) -> float:
    """2차 가속도 (Momentum/Acceleration)"""
    return float(np.polyfit(range(len(values)), values, 2)[0])

def range_amplitude(values: np.ndarray) -> float:
    """최대 진폭 (절대적 공간 점유율)"""
    return float(np.ptp(values))

## Topological & Energy (위상 및 에너지)
def path_length(values: np.ndarray) -> float:
    """궤적의 실제 이동 거리 (마찰력)"""
    return float(np.sum(np.abs(np.diff(values))))

def mean_crossings(values: np.ndarray) -> float:
    """평균선 교차 횟수 (진동 주파수)"""
    mean_val = np.mean(values)
    centered = values - mean_val
    return float((centered[:-1] * centered[1:] < 0).sum())

def signal_energy(values: np.ndarray) -> float:
    """신호의 총 운동 에너지 (변동량의 제곱합)"""
    return float(np.sum(np.diff(values)**2))

## Distribution & Tail (분포 및 극단성)
def volatility(values: np.ndarray) -> float:
    """궤적의 산포도 (표준편차)"""
    r = np.diff(values) / values[:-1]
    return float(np.std(r))

def drawdown(values: np.ndarray) -> float:
    """고점 대비 최대 낙폭 (중력/붕괴성)"""
    return float((values.min() - values.max()) / values.max())

def skewness(values: np.ndarray) -> float:
    """분포의 비대칭도 (어느 방향으로 힘이 쏠려있는가)"""
    diffs = np.diff(values)
    mean_d = np.mean(diffs)
    std_d = np.std(diffs)
    if std_d == 0: return 0.0
    return float(np.mean(((diffs - mean_d) / std_d)**3))