# swarm.prober.field.evo
## @lineage: bound.closure.field.evo
## @lineage: scripts.phase.field.evo
## @lineage: spec.code.field.evo
## @lineage: spec.script.field.evo
## @lineage: theoria.arch.model.script.evo
import math
import time
from watcher.plane.surface import SurfacePlane

## @Bound: 시스템의 형태를 유지하기 위한 제약 조건(Constraints)의 밀도와 한계치를 정의하는 파라미터 텐서.
class Bound:
    def __init__(
        self,
        limit=0.5,             # 구조적 붕괴를 허용하는 최대 응력 임계치
        nu=0.2,                # 응력에 대항하는 시스템 내부의 복원력(점성) 계수
        dt=1.0,                # 시간 적분 단위
        advection_scale=0.1,   # 외부 부하(Load)가 시스템 내부로 이류(Advection)되는 스케일
        diffusion_scale=1.0    # 시스템 내부의 응집된 스트레스가 확산(Diffusion)되는 스케일
    ):
        self.limit = limit
        self.nu = nu
        self.dt = dt
        self.advection_scale = advection_scale
        self.diffusion_scale = diffusion_scale
        self.coherence_threshold = 0.15

## @Field: 시스템 경계 외부에 존재하는 연속적이고 비선형적인 환경 부하 생성기
class Field:
    def __init__(self):
        ## 두 개의 이질적인 주파수가 결합하여 예측하기 어려운 간섭 패턴(Interference)을 형성
        self.freq_a = (11 * math.pi) / 353
        self.freq_b = (4.0 * math.pi) / 353
        self.phase_a = self.freq_a * 14
        self.phase_b = 0.0
        self.threshold = math.cos(self.phase_a / 5)

    def evolve(self):
        ## 환경 위상의 연속적 진행
        self.phase_a += self.freq_a
        self.phase_b += self.freq_b

    def predict_future_load(self, steps_ahead):
        ## 선행(Feedforward) 관측을 통한 스칼라 변위량 추정
        future_a = self.phase_a + (self.freq_a * steps_ahead)
        future_b = self.phase_b + (self.freq_b * steps_ahead)
        interference = math.sin(future_a) * math.cos(future_b)
        return abs(interference)

    def emit(self):
        ## 현재 위상에서의 환경 에너지 방출 (임계점 돌파 시 비선형적 스파이크 발생)
        interference = math.sin(self.phase_a) * math.cos(self.phase_b)
        if abs(interference) > self.threshold:
            return math.pi
        return 1.1

class RhythmController:
    def __init__(
        self,
        base_interval=0.03,
        min_interval=0.01,
        max_interval=0.05,
        pressure_threshold=3,
        compression_rate=0.8,
        recovery_step=0.002
    ):
        self.interval = base_interval
        self.base_interval = base_interval
        self.min_interval = min_interval
        self.max_interval = max_interval

        self.pressure = 0
        self.pressure_threshold = pressure_threshold
        self.compression_rate = compression_rate
        self.recovery_step = recovery_step

    def adjust(self, load):
        # 감응 누적
        if load > 2.5:
            self.pressure += 1
        else:
            self.pressure = max(0, self.pressure - 0.5)

        # 압축
        if self.pressure > self.pressure_threshold:
            self.interval = max(
                self.min_interval,
                self.interval * self.compression_rate
            )
        # 회복
        else:
            self.interval = min(
                self.max_interval,
                self.interval + self.recovery_step
            )

        return self.interval


## @Loop
class BaseRhythm:
    def __init__(self, model):
        self.model = model
        self.rhythm = RhythmController()
        self.pending_model = None
        self.pressure = 0
        self.interval = 0.03

    def step_once(self, tick):
        future = self.model.field.predict_future_load(5)
        self.model.field.evolve()
        self.model.field2.evolve()

        load = self.model.field.emit() * 0.9 + self.model.field2.emit() * 0.1
        metrics = {
            "load": load,
            "future_load": future
        }

        self.current_interval = self.rhythm.adjust(load)
        return self.model.step(tick, metrics)

## @Watcher: 시스템 내부의 정합성(Coherence)과 이탈률(Drift)을 수치 해석
class Watcher:
    def __init__(self, bound, meta):
        self.bound = bound
        self.meta = meta
        self.load_coherence = 1.0     # 초기 상태의 완벽한 구조적 정합성
        self.drift_accumulator = 0.0  # 해소되지 못하고 누적된 상태 편차의 적분값
        self.version = 1
        self.mode = "STABLE"

    def compute_advection(self, load):
        ## 부하의 제곱에 비례하여 시스템 경계를 수축/압박하는 음(-)의 벡터 계산
        return - (load ** 2) * self.bound.advection_scale

    def compute_diffusion(self, tick):
        ## 시간 위상(math.sin)에 연동된 미세 진동을 통해 시스템을 지속적으로 이완
        phase_mod = 1 + 0.05 * math.sin(tick * 0.1)
        return (
            self.bound.nu *
            self.bound.diffusion_scale *
            phase_mod *
            (1.0 - self.load_coherence**1.05)
        )

    def step(self, tick, load, future_load):
        prediction_status = "SAFE"
        if future_load > 0.95:
            prediction_status = "!!!WARN!!!"
        elif future_load > 0.90:
            prediction_status = "CAUTION"

        contraction = self.compute_advection(load)
        relaxation = self.compute_diffusion(tick)

        predicted = self.load_coherence + self.bound.dt * (contraction + relaxation)
        delta = predicted - self.load_coherence

        tension_ratio = abs(delta) / self.bound.limit
        damping = min(1.0, tension_ratio)

        self.load_coherence += delta * (1 - damping)

        self.drift_accumulator = (
            0.9 * self.drift_accumulator + abs(delta)
        )

        if self.drift_accumulator > self.bound.coherence_threshold:
            self.mode = "RESYNTH"
            SurfacePlane.record(
                tick,
                "MESO_LOOP",
                f"Drift Saturated: {self.drift_accumulator:.3f}",
                "CRIT",
                prediction_status
            )

            self.re_synthesize(tick)
            self.drift_accumulator = 0.0
            return "RESYNTH"

        log_msg = (
            f"Disp={self.load_coherence:.3f} | "
            f"Relax={relaxation:.3f} | "
            f"Damp={damping:.2f} | "
            f"DriftΣ={self.drift_accumulator:.3f}"
        )

        SurfacePlane.record(tick, "MICRO_LOOP", log_msg, "INFO", prediction_status)
        return None

    def re_synthesize(self, tick):
        # 파편화된 시스템의 정합성을 1.0으로 강제 초기화하되, 복원력(nu)을 10% 증가시켜 다음 주기의 응력에 대비하는 내부 경계
        self.version += 1
        self.load_coherence = 1.0
        self.bound.nu *= 1.1 
        SurfacePlane.record(tick, "RE_SYNTH", f"Topology re-synthesis initiated. v{self.version}", "SYS", "REBOOT")

class Metaflow:
    """스스로를 재정의하며 진화하는 자기 참조적 시스템"""
    def __init__(self, seed):
        self.metalog = Metalog()
        self.watcher = Watcher()
        self.current_system = SystemField(0, seed)

    def tloop(self, max_iterations=4):
        print("## flow.loop 진동 시작\n")
        
        for n in range(max_iterations):
            print(f"cycle.{n}")
            
            ## PROJECTION (투사)
            print(f"[Phase: PROJECTION] 현재 대상에 몰입합니다. Target: {self.current_system}")
            time.sleep(1) # 존재의 호흡(pulse)을 위한 지연
            
            ## OBSERVATION (관찰)
            print("[Phase: OBSERVATION] 시스템 외부로 관찰 시점을 이동합니다.")
            meta_view = self.watcher.detach_and_observe(self.current_system)
            self.metalog.write(n, meta_view)
            time.sleep(1)
            
            ## REFRAMING (재정의)
            print("[Phase: REFRAMING] 이전 차원의 세계를 캡슐화합니다.")
            next_system = self.watcher.encapsulate(self.current_system, meta_view)
            time.sleep(1)
            
            ## ELEVATION (상승)
            self.current_system = next_system
            print(f"[Phase: ELEVATION] 위상이 상승했습니다. 새로운 좌표계: {self.current_system}\n")
            time.sleep(1)
            
        print("tloop 일시 정지")
        print(f"최종 위상 구조:\n{self.current_system}")
        print("\n저장된 Metalog 궤적:")
        for record in self.metalog.records:
            print(record)

# 실행 (초기 위상 T_0를 'startup_pattern'으로 부여)
if __name__ == "__main__":
    meta_system = Metaflow(seed="startup")
    meta_system.tloop()