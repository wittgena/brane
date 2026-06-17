# arch.topos.gov.node.anchor
## @lineage: gov.state.node.anchor
## @lineage: gov.state.system.node.anchor
## @lineage: gov.repo.node.anchor
"""
@align.commit: lineage inscription over execution results
@node: execution-capable self (not tied to repo)
@anchor: synchronization boundary across nodes (era frame)
@commit: parent linkage under anchor-constrained selection
@state.partition: aligned vs lag (no non-existence)
"""
import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Callable
from arch.proto.event.next import next_id
from arch.topos.gov.repo.schema import RepoCommit, AnchorCommit
from phase.bind.resolver import resolve_path

DEFAULT_ID = "0000000"
LINEAGE_ROOT = resolve_path('contract') / 'lineage'

class ActorNode:
    """@role: execution unit + lineage inscription node"""
    def __init__(self, name: str, path: str, runner: Callable):
        self.name = name
        self.path = Path(path).expanduser().resolve()
        self.lineage_dir = LINEAGE_ROOT
        self.runner = runner
        self.lineage_file = self.lineage_dir / f"{self.name}.lineage.json"

    def inscribe(self, anchor_id: str, parent_anchor_id: Optional[str], parent_commit_id: str, message: str, apply: bool = False) -> str:
        """현재 세대의 계보를 모델링하여 각인함"""
        model = RepoCommit(
            anchor_id=anchor_id,
            parent_anchor_id=parent_anchor_id or DEFAULT_ID,
            parent_commit_id=parent_commit_id
        )

        self.lineage_dir.mkdir(parents=True, exist_ok=True)
        with open(self.lineage_file, "w") as f:
            f.write(model.to_json())

        full_message = f"{message}\n\n{model.to_json()}"
        new_commit_id = self.runner(self.path, full_message, apply)
        print(f"  └─ [{self.name}] Inscribed. State: {new_commit_id}")
        return new_commit_id

class EpochManager(ActorNode):
    """@role: boundary (synchronization frame) + era manager"""
    ERA_DEPTH = 3

    def __init__(self, name: str, path: str, runner: Callable):
        super().__init__(name, path, runner)
        self.registry_file = self.lineage_dir / f"{self.name}.registry.json"

    def load_history(self) -> List[Dict]:
        """registry에서 히스토리 추출"""
        if not self.registry_file.exists(): return []
        with open(self.registry_file, "r") as f:
            try: return json.load(f).get("history", [])
            except: return []

    def resolve(self, repo_name: str) -> str:
        history = self.load_history()
        # 최근 3대 시대(Era) 내 탐색
        for snapshot in reversed(history[-3:]):
            # repos와 cached_states 모두에서 마지막 상태를 찾음
            if repo_name in snapshot.get("repos", {}):
                return snapshot["repos"][repo_name]
            if repo_name in snapshot.get("cached_states", {}):
                return snapshot["cached_states"][repo_name]
        return DEFAULT_ID

    def project(self, states: Dict[str, str]) -> Dict[str, str]:
        return states

    def anchoring(self, anchor_id: str, parent_anchor_id: Optional[str], 
                      repos: Dict[str, str], cached_states: Dict[str, str], 
                      message: str, apply: bool = False) -> str:
        history = self.load_history()
        self_parent_state = self.resolve(self.name)
        model = AnchorCommit(
            anchor_id=anchor_id,
            parent_anchor_id=parent_anchor_id or DEFAULT_ID,
            parent_commit_id=self_parent_state,
            repos=repos,
            cached_states=cached_states
        )

        ## Apply 시점에만 전역 레지스트리 업데이트
        if apply:
            full_history = history + [json.loads(model.to_json())]
            with open(self.registry_file, "w") as f:
                json.dump({"history": full_history}, f, indent=2)
        return super().inscribe(anchor_id, parent_anchor_id, self_parent_state, message, apply)
