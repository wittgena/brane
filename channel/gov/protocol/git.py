# channel.gov.protocol.git
## @lineage: gov.gateway.protocol.git
## @lineage: gov.medium.protocol.git
## @lineage: gov.network.protocol.git
## @lineage: gov.bridge.protocol.git
## @lineage: meta.ops.protocol.git
## @lineage: gov.consensus.protocol.git
## @lineage: gov.comm.protocol.git
## @lineage: gov.state.sync.protocol
"""
@anchor: synchronization boundary across nodes (era frame)
@commit: parent linkage under anchor-constrained selection
@state.partition: aligned vs lag (no non-existence)
"""
import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Callable
from arch.proto.event.next import next_id
from arch.topos.gov.node.anchor import ActorNode, EpochManager
from phase.bind.resolver import resolve_path
from watcher.plane.emitter import get_emitter

log = get_emitter("protocol.git")

DEFAULT_ID = "0000000"

def anchor_git_commit(repos: List[ActorNode], anchor: EpochManager, message: str, apply: bool = False):
    """@protocol: era-based alignment cycle over execution results"""
    log.info(f"## Era-based Alignment Cycle Initiated ({'APPLY' if apply else 'DRY-RUN'})")
    
    ## 히스토리에서 부모 앵커 식별
    history = anchor.load_history()
    last_snapshot = history[-1] if history else None
    parent_anchor_id = last_snapshot["anchor_id"] if last_snapshot else DEFAULT_ID

    new_anchor_id = next_id()

    ## 이번 정렬에 참여한 노드들 실행
    current_aligned_states = {}
    for r in repos:
        parent_state = anchor.resolve(r.name)
        ## Runner를 통해 실제 해시 획득
        current_aligned_states[r.name] = r.inscribe(new_anchor_id, parent_anchor_id, parent_state, message, apply)

    ## cached_states 계산
    cached_states = {}
    if last_snapshot:
        prev_total = {**last_snapshot.get("repos", {}), **last_snapshot.get("cached_states", {})}
        for name, last_hash in prev_total.items():
            if name not in current_aligned_states and name != anchor.name:
                cached_states[name] = last_hash

    ## 앵커 고정 (Self 포함)
    final_anchor_hash = anchor.anchoring(
        new_anchor_id, parent_anchor_id, current_aligned_states, cached_states, message, apply
    )
    log.info(f"## Era Fixed: {new_anchor_id} (Aligned: {len(current_aligned_states)}, Lagged: {len(cached_states)})")
