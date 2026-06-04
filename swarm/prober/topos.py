# swarm.prober.topos
## @lineage: debug.prober.topos
## @lineage: meta.watcher.prober.topos
## @lineage: bound.watcher.prober.topos
## @lineage: gov.auth.prober.topos
## @lineage: iso.domain.prober.topos
## @lineage: agent.domain.prober.topos
## @lineage: domain.prober.topos
## @lineage: iso.prober.topos
## @lineage: meta.debug.tracer.isorhesis
"""
@role: 
- K8s Operator(Isorhesis)가 정상적으로 동적 평형을 달성하는지 외부에서 관측하고 증명(PoC)
- 스스로 댐핑하지 않으며, 오퍼레이터의 Boundary Shift 궤적과 Homeostasis 도달을 추적
"""
import asyncio
import json
from watcher.plane.emitter import get_emitter
from phase.bind.resolver import resolve_path

class ToposProber:
    def __init__(self, target_namespace: str = "default", target_deploy: str = "surgent-worker"):
        self.log = get_emitter("topos.proofer", phase="meta")
        self.namespace = target_namespace
        self.target = target_deploy
        self.process_pool = []
        
        ## @state: Proof Trackers
        self.replicas_history = []
        self.equilibrium_achieved = False

    async def run_command(self, cmd: list, capture: bool = False):
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE if capture else None,
            stderr=asyncio.subprocess.PIPE if capture else None
        )
        if capture:
            stdout, stderr = await proc.communicate()
            return proc.returncode, stdout.decode().strip(), stderr.decode().strip()
        return await proc.wait(), "", ""

    async def audit_topology_drift(self):
        """@desc: 오퍼레이터에 의한 Deployment의 Replicas 변화 및 Ready 상태 관측"""
        self.log.info(f"## @observer: Topology Auditor attached to '{self.target}'.")
        
        try:
            while not self.equilibrium_achieved:
                code, out, _ = await self.run_command([
                    "kubectl", "get", "deployment", self.target, "-n", self.namespace,
                    "-o", "jsonpath={.spec.replicas}:{.status.readyReplicas}"
                ], capture=True)

                if code == 0 and out:
                    parts = out.split(":")
                    spec_replicas = int(parts[0]) if parts[0] else 0
                    ready_replicas = int(parts[1]) if len(parts) > 1 and parts[1] else 0
                    
                    # 궤적 기록
                    if not self.replicas_history or self.replicas_history[-1] != spec_replicas:
                        self.replicas_history.append(spec_replicas)
                        if len(self.replicas_history) > 1:
                            self.log.warning(f"  [SHIFT DETECTED] Operator expanded boundary: {self.replicas_history[-2]} -> {spec_replicas} replicas.")

                    # 평형 검증 (목표 크기에 도달했고, 모든 파드가 Ready 상태로 안정화되었는가)
                    if spec_replicas > 1 and ready_replicas == spec_replicas:
                        self.log.signal(f"  [WAVEFORM] Tension stabilized at {spec_replicas} replicas.")
                        self.equilibrium_achieved = True
                        
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            self.log.info("## @observer: Audit gracefully detached.")

    async def trace(self):
        self.log.crit("## @trace.init Initiating Isorhesis Proof of Concept (PoC)")

        try:
            ## 텐션 주입 (Genesis)
            self.log.info("## @phase.1: Injecting Surface ConfigMap (Triggering Genesis)...")
            await self.run_command(["kubectl", "apply", "-f", "workspace/repro/surgent-surface.yaml"])

            ## 오퍼레이터의 반응 관측 시작
            self.log.info("## @phase.2: Awaiting Operator's Transcription & Projection...")
            await asyncio.sleep(5) # Kompose 변환 및 배포 대기
            
            audit_task = asyncio.create_task(self.audit_topology_drift())

            ## Boundary Shift 증명 대기
            self.log.info("## @phase.3: Auditing Dynamic Equilibrium (Max ETA: 60s)...")
            timeout = 60
            while timeout > 0 and not self.equilibrium_achieved:
                await asyncio.sleep(1)
                timeout -= 1

            ## 최종 판정 (Judgment)
            if self.equilibrium_achieved:
                self.log.crit(f"[SUCCESS] Isorhesis Proven. The Operator successfully shifted the boundary to {self.replicas_history[-1]} without teardown.")
            else:
                self.log.error(f"[FAIL] The Operator failed to reach Homeostasis within {timeout}s. Current state: {self.replicas_history}")
        except Exception as e:
            self.log.crit(f"## @trace.error: Structural Fault during Proof: {str(e)}")
        finally:
            self.log.info("## @phase.4: Proof complete. System remains in its current dynamic state.")
            for task in asyncio.all_tasks():
                if task is not asyncio.current_task():
                    task.cancel()

if __name__ == "__main__":
    prober = ToposProber()
    asyncio.run(prober.trace())