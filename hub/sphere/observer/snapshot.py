# hub.sphere.observer.snapshot
## @lineage: sphere.observer.snapshot
## @lineage: meta.sphere.observer.snapshot
## @lineage: bound.sphere.observer.snapshot
## @lineage: gov.sphere.observer.snapshot
## @lineage: iso.sphere.observer.snapshot
## @lineage: bound.observer.cloud.snapshot
## @lineage: iso.sphere.cloud.snapshot
"""
@desc: Async AWS + Spiral Hybrid (Distributed Phase Field)
@flow: Ψ(AWS Metrics) → ∂Φ(Tension) → Async Diffusion → Attractor
"""
import asyncio
import math
import random
import time
from dataclasses import dataclass
from typing import Dict, List

@dataclass
class MetricsSnapshot:
    """
    @phase.role: Ψ (phase carrier)
    - Encodes system state as observable projection
    - Transport layer from infra → phase field
    """
    timestamp: float
    resource_id: str
    tags: Dict[str, str]
    desired_capacity: int
    running_instances: int
    failed_health_checks: int
    scp_allows_scaling: bool

class CloudEnv:
    """
    @phase.role: Ψ source (state emitter)
    - Generates evolving system state (entropy progression)
    - Externalized control via intervention (re-anchor interface)
    """
    def __init__(self, resource_id: str = "ASG-Frontend-Web"):
        self.state = {
            "resource_id": resource_id,
            "tags": {"Env": "prodction"},  # 의도된 오타 (Semantic Drift)
            "desired_capacity": 1,
            "running_instances": 1,
            "failed_health_checks": 0,
            "scp_allows_scaling": True
        }

    def tick(self):
        """
        @phase.evolution:
        - Internal entropy increase (P-layer escalation)
        - Autonomous system progression without correction
        """
        self.state["failed_health_checks"] += self.state["running_instances"] * 2
        if self.state["scp_allows_scaling"]:
            self.state["desired_capacity"] += 1
            self.state["running_instances"] += 1

    def emit_snapshot(self) -> MetricsSnapshot:
        """
        @phase.emit:
        Ψ → external phase field projection
        """
        return MetricsSnapshot(
            timestamp=time.time(),
            resource_id=self.state["resource_id"],
            tags=self.state["tags"].copy(),
            desired_capacity=self.state["desired_capacity"],
            running_instances=self.state["running_instances"],
            failed_health_checks=self.state["failed_health_checks"],
            scp_allows_scaling=self.state["scp_allows_scaling"]
        )

    def apply_intervention(self, adjustments: Dict):
        """
        @phase.reentry: RA (Re-anchor)
        - External correction of system attractor
        """
        """외부(Theoria)로부터의 강제 상태 조정 (Re-anchor)"""
        if "tags" in adjustments:
            self.state["tags"].update(adjustments["tags"])
        if "scp_allows_scaling" in adjustments:
            self.state["scp_allows_scaling"] = adjustments["scp_allows_scaling"]

class Node:
    """
    @phase.role: Distributed phase carrier (local Φ node)
    - Maintains local phase (Φ) and tension (∂Φ)
    - Participates in diffusion and phase synchronization
    """
    def __init__(self, node_id, phase_val=0.0):
        self.id = node_id
        self.state = "NORMAL"  # NORMAL, REFLECTOR, CANDIDATE, ATTRACTOR
        self.phase = phase_val
        self.tension = 0.0
        self.neighbors: List["Node"] = []
        
        self.candidate_threshold = 10.0
        self.rupture_limit = 25.0

    def connect(self, other_node):
        """@phase.topos: Establish phase coupling edge"""
        if other_node not in self.neighbors:
            self.neighbors.append(other_node)
            other_node.neighbors.append(self)

    def ingest(self, metrics: MetricsSnapshot):
        """@phase.map: Ψ → ∂Φ"""
        if self.state in ["REFLECTOR", "ATTRACTOR"]:
            return

        if metrics.tags.get("Env") != "production":
            self.tension += 1.5

        if metrics.failed_health_checks > metrics.desired_capacity:
            self.tension += metrics.desired_capacity * 0.3

    async def exist(self, global_tick: list):
        """
        @phase.loop: Local phase evolution cycle (async)
        - Φ <-> ∂Φ resonance -> transition
        """
        while True:
            tick = global_tick[0]
            tension_diff = 0.0
            phase_pull = 0.0
            
            ## @phase.diffusion: ∂Φ resonance
            ## @phase.coupling: Φ synchronization (Kuramoto-like)
            for n in self.neighbors:
                tension_diff += (n.tension - self.tension) * 0.1
                phase_pull += math.sin(n.phase - self.phase) * 0.2

            if self.state == "NORMAL":
                self.tension = max(0.0, self.tension + tension_diff + random.uniform(0, 0.2))
                self.phase = (self.phase + phase_pull) % (2 * math.pi)
                
                ## @phase.transition: emergence (Residue → Candidate)
                if self.tension > self.candidate_threshold:
                    self.state = "CANDIDATE"
                    print(f"[Tick {tick}] [{self.id}] EMERGENCE: Tension {self.tension:.1f} 돌파 → CANDIDATE")
                    
            elif self.state == "REFLECTOR":
                ## External phase injection
                self.phase = math.pi
                for n in self.neighbors:
                    n.tension += 1.0
                if tick % 5 == 0:
                    print(f"[Tick {tick}] [{self.id}] REFLECT: 주변 텐션 가중")

            elif self.state == "CANDIDATE":
                ## Absorb tension from neighbors
                absorbed = 0.0
                for n in self.neighbors:
                    drain = min(n.tension, 1.5)
                    n.tension -= drain
                    absorbed += drain
                self.tension += absorbed
                
                ## @phase.rupture: ∂Φ → Φ⁺ (attractor formation)
                if self.tension >= self.rupture_limit:
                    self.state = "ATTRACTOR"
                    self.tension = 0.0
                    self.phase = random.choice([math.pi/2, math.pi, 3*math.pi/2])
                    print(f"[Tick {tick}] [{self.id}] RUPTURE: 파열 및 ATTRACTOR 반전 (Phase: {self.phase:.2f})")

            elif self.state == "ATTRACTOR":
                ## Phase lock & dissipate tension
                for n in self.neighbors:
                    n.tension = max(0.0, n.tension - 2.0)
                    n.phase = self.phase

            await asyncio.sleep(0.5)

class EnvSimCoordinator:
    """
    @phase.role: System orchestrator (Φ field coordinator)
    - Connects Ψ source (AWS) with Φ field (Nodes)
    - Drives global tick and async phase evolution
    """
    def __init__(self, size=10):
        self.aws = CloudEnv()
        self.tick = [0]
        
        # @phase.field: distributed Φ nodes
        self.nodes = [Node(f"N{i}", random.uniform(0, 0.5)) for i in range(size)]
        self._build_network()

    def _build_network(self):
        """@phase.topos: Constructs small-world / scale-free hybrid network"""
        for i in range(len(self.nodes)):
            self.nodes[i].connect(self.nodes[(i+1) % len(self.nodes)])
            if random.random() < 0.3:
                target = random.choice(self.nodes)
                self.nodes[i].connect(target)
                
        self.nodes[0].state = "REFLECTOR"
        self.nodes[0].id = "R0-REFLECTOR"

    def emit_metrics(self) -> MetricsSnapshot:
        return MetricsSnapshot(
            timestamp=time.time(),
            resource_id=self.state["resource_id"],
            tags=self.state["tags"],
            desired_capacity=self.state["desired_capacity"],
            running_instances=self.state["running_instances"],
            failed_health_checks=self.state["failed_health_checks"],
            scp_allows_scaling=self.state["scp_allows_scaling"]
        )

    async def _poll_aws_metrics(self):
        """@phase.bridge: Ψ → Node field injection loop"""
        while self.tick[0] < 20:
            await asyncio.sleep(1.0)
            self.tick[0] += 1

            self.aws.tick()
            snapshot = self.aws.emit_snapshot()

            for node in self.nodes:
                node.ingest(snapshot)

            print(f"\n--- Tick {self.tick[0]} | Desired: {snapshot.desired_capacity}, Failed: {snapshot.failed_health_checks} ---")

    async def run(self):
        """@phase.execution: Launch async phase field + external pressure loop"""
        print("Async AWS + Spiral Topos Start")

        tasks = [asyncio.create_task(node.exist(self.tick)) for node in self.nodes]
        aws_task = asyncio.create_task(self._poll_aws_metrics())
        await aws_task
        
        for t in tasks:
            t.cancel()
            
        print("\n[END] Phase Transition Model Terminated.")

if __name__ == "__main__":
    sim = EnvSimCoordinator(size=10)
    asyncio.run(sim.run())