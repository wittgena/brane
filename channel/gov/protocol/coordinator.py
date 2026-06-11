# channel.gov.protocol.coordinator
## @lineage: gov.gateway.protocol.coordinator
## @lineage: gov.medium.protocol.coordinator
## @lineage: gov.network.protocol.coordinator
## @lineage: gov.bridge.protocol.coordinator
## @lineage: meta.ops.protocol.coordinator
## @lineage: gov.consensus.protocol.coordinator
## @lineage: gov.comm.protocol.coordinator
## @lineage: gov.state.sync.protocol.coordinator
import asyncio
from typing import List
from arch.proto.event.next import next_id
from watcher.plane.emitter import get_emitter
from arch.topos.gov.node.anchor import ActorNode, EpochManager
from channel.gov.protocol.handshake import HandshakeNode, AlignmentState

log = get_emitter("protocol.coordinator")
DEFAULT_ID = "0000000"

class StateSyncCoordinator:
    """
    @role: Orchestrator integrating Cognitive Alignment (Handshake) and Physical Era-fixing (Anchor)
    """
    def __init__(self, orchestrator_name: str, anchor: EpochManager, actors: List[ActorNode]):
        self.name = orchestrator_name
        self.anchor = anchor       # 동기화 경계 관리자
        self.actors = actors       # 실행을 담당하는 노드들
        self.handshake = HandshakeNode(f"{orchestrator_name}_Cognitive_Gateway")
        
    async def align_and_commit(self, message: str, apply: bool = False) -> str:
        """@protocol: 1) Handshake 평가 -> 2) 실패 시 Lag 처리 / 성공 시 State Commit"""
        log.info(f"## Era-based Alignment Cycle Initiated ({'APPLY' if apply else 'DRY-RUN'})")
        
        ## 게이트웨이 검사: 인지적 공명 상태인가?
        if self.handshake.alignment_state != AlignmentState.RESONANCE:
            log.warning(f"[{self.name}] Cognitive alignment is strictly required. Current state: {self.handshake.alignment_state}")
            log.info("Transitioning all actors to cached (lag) states due to cognitive friction.")
            return self._force_lag_commit(message, apply)

        ## 공명 상태 도달: 정상적인 물리적 동기화 수행
        history = self.anchor.load_history()
        last_snapshot = history[-1] if history else None
        parent_anchor_id = last_snapshot["anchor_id"] if last_snapshot else DEFAULT_ID
        new_anchor_id = next_id()

        current_aligned_states = {}
        for actor in self.actors:
            parent_state = self.anchor.resolve(actor.name)
            ## 상태 내재화: Actor 스스로가 aligned 상태임을 기록 (선택적 구현)
            actor.is_lagged = False 
            current_aligned_states[actor.name] = actor.inscribe(
                new_anchor_id, parent_anchor_id, parent_state, message, apply
            )

        ## cached_states 계산
        cached_states = {}
        if last_snapshot:
            prev_total = {**last_snapshot.get("repos", {}), **last_snapshot.get("cached_states", {})}
            for name, last_hash in prev_total.items():
                if name not in current_aligned_states and name != self.anchor.name:
                    cached_states[name] = last_hash

        ## Era 확정
        final_anchor_hash = self.anchor.anchoring(
            new_anchor_id, parent_anchor_id, current_aligned_states, cached_states, message, apply
        )
        log.info(f"## Era Fixed: {new_anchor_id} (Aligned: {len(current_aligned_states)}, Lagged: {len(cached_states)})")
        return final_anchor_hash

    def _force_lag_commit(self, message: str, apply: bool) -> str:
        """인지적 합의 실패 시, 현재 Era의 상태를 유보하고 모두 이전 상태로 래핑"""
        # (기존 history를 복사하여 새로운 Era ID만 부여하는 로직 구현)
        pass