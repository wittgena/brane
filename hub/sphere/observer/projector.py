# hub.sphere.observer.projector
## @lineage: sphere.observer.projector
## @lineage: meta.sphere.observer.projector
"""
@desc: Theoria-Centric AWS adaptive control loop
@flow:
Ψ -> Φ′ (evaluation)
-> {Φ⁺ | ∂Φ}
-> RA (reentry / control)
"""
import time
from dataclasses import dataclass
from typing import Dict
from watcher.plane.emitter import get_emitter
from nexus.hub.sphere.observer.snapshot import MetricsSnapshot, CloudEnv

log = get_emitter("cloud.projector")

class CloudProjector:
    """
    @phase.role: Φ′ (Phase evaluation kernel)
    - Evaluates Ψ and detects ∂Φ
    """
    def __init__(self, semantic_baseline: Dict[str, str]):
        self.semantic_baseline = semantic_baseline
        self.collapse_threshold = 3.0

        ## @phase.field: Φᵗ (memory landscape of ∂Φ traces)
        self.memory = {
            "residues": [],
            "history": []
        }

    def project_and_eval(self, env: CloudEnv, max_ticks: int = 5):
        """@phase.loop: Φ′ observes Ψ → evaluates → delegates RA if needed"""
        log.info(f"[Theoria Projector] {env.state['resource_id']} 감시 체계 가동\n")

        for tick in range(1, max_ticks + 1):
            time.sleep(1)
            log.info(f"## Tick.{tick}")
            env.tick()
            snapshot = env.emit_snapshot()
            is_coherent = self._evaluate_phase(snapshot)
            if not is_coherent:
                self._trigger_reentry_action(env, snapshot.resource_id)
                break
            else:
                log.info(f"  [✔] 정상 유지 (Instances: {snapshot.running_instances})")

    def _evaluate_phase(self, metrics: MetricsSnapshot) -> bool:
        """@flow: Ψ → Φ′ → {Φ⁺ (coherent) | ∂Φ (drift)}"""
        log.info(f"  [Eval] Ψ 맵핑 분석 중...")
        drift_score = 0.0
        residue = []  

        if metrics.tags.get("Env") != self.semantic_baseline.get("Env"):
            log.info("    🚨 [M-Drift] Semantic Baseline 이탈 (태그 불일치)")
            drift_score += 2.0
            residue.append(("M", metrics.tags.copy()))

        if metrics.desired_capacity > 2 and metrics.failed_health_checks > metrics.desired_capacity:
            delta = metrics.desired_capacity * 0.5
            log.info(f"    🚨 [P-Saturation] 실행 루프 발산 감지 (+{delta:.1f} Tension)")
            drift_score += delta
            residue.append(("P", delta))

        log.info(f"    📊 누적 Drift: {drift_score:.1f} / {self.collapse_threshold}")

        if residue:
            self.memory["residues"].append({
                "timestamp": metrics.timestamp,
                "data": residue
            })

        return drift_score < self.collapse_threshold

    def _trigger_reentry_action(self, env: CloudEnv, resource_id: str):
        log.info(f"\n  [⚡ REENTRY] 임계점 돌파! {resource_id} 보호 루프 가동")
        intervention_payload = {}

        if self.memory["residues"]:
            recent = self.memory["residues"][-1]["data"]

            for r_type, value in recent:
                if r_type == "M":
                    log.info("  [♻️ Re-anchor] 환경 태그 강제 교정 (Env -> production)")
                    intervention_payload["tags"] = {"Env": "production"}
                
                if r_type == "P":
                    log.info("  [🛑 Re-anchor] 폭주 차단: Auto Scaling 일시 정지")
                    intervention_payload["scp_allows_scaling"] = False

        if intervention_payload:
            env.apply_intervention(intervention_payload)

        self.memory["history"].append(self.semantic_baseline.copy())
        log.info(f"  [🛡️ SYSTEM SECURED] 위상 안정화 완료\n")

if __name__ == "__main__":
    baseline = {"Env": "production"}
    projector = CloudProjector(semantic_baseline=baseline)
    target_env = CloudEnv("ASG-Frontend-Web")
    projector.project_and_eval(target_env, max_ticks=6)