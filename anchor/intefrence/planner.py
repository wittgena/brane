# anchor.intefrence.planner
## @lineage: bound.intefrence.planner
## @lineage: bound.debug.planner
## @lineage: debug.planner
## @lineage: gov.exam.planner
## @lineage: meta.debug.planner
## @lineage: meta.debug.executor.planner
import _thread
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path
from watcher.plane.emitter import get_emitter
from phase.bind.resolver import resolve_path
from gov.scope.manager import managed_scope

WORKSPACE = resolve_path("workspace")
log = get_emitter("debug.planner")

@dataclass
class PlanAction:
    id: str
    instruction: str
    target: str = "main"        # 대상 파일 혹은 모듈
    agent_usage: str = "worker" # 사용할 에이전트 위상
    meta: Dict[str, Any] = field(default_factory=dict) # 추가 제어 플래그

class WorkActor:
    def __init__(self, engine_factory: callable, workspace_root: Path):
        self.engine_factory = engine_factory
        self.workspace_root = workspace_root
        self.mem: Dict[str, Any] = {}     # 세션 영구 지식
        self.xe: Dict[str, Any] = {}      # 실행 환경 상태 (Paths, Ports, etc)
        self.residue: str = ""             # 직전 실행의 미완성분 혹은 찌꺼기
        self.intercepted_text = ""
        self.response_count = 0

    def _rupture_callback(self, event):
        """이벤트 스트림을 감시하며 루처(Rupture) 발생 여부 판단"""
        if event.source != "agent": return
        self.response_count += 1
        if len(event.content.strip()) > 5:
            self.intercepted_text = event.content
            ## 정합성이 확인되면 즉시 루프 절단
            _thread.interrupt_main()

    def _assemble_context(self, action: PlanAction) -> str:
        """mem, xe, residue를 결합하여 에이전트가 인지할 '표면' 생성"""
        ctx = [
            f"### CONTEXT_XE: Working at {self.workspace_root}",
            f"### PREVIOUS_RESIDUE: {self.residue if self.residue else 'None'}",
            f"### MEMORY_SNAPSHOT: {list(self.mem.keys())}",
            f"\nINSTRUCTION: {action.instruction}"
        ]
        return "\n".join(ctx)

    def dispatch(self, action: PlanAction):
        """단일 액션을 엔진에 투사"""
        log.info(f"[*] Dispatching Action: {action.id} ({action.agent_usage})")
        
        self.intercepted_text = ""
        self.response_count = 0
        prompt = self._assemble_context(action)
        engine = self.engine_factory(action.agent_usage)
        try:
            engine.ask(prompt, callback=self._rupture_callback)
        except KeyboardInterrupt:
            log.info(f"[+] Action {action.id} ruptured and captured.")

        ## 실행 결과 처리 (Residue 업데이트)
        self.residue = self.intercepted_text.strip()
        self._sync_state(action)

    def _sync_state(self, action: PlanAction):
        """실행 후 mem과 xe를 동기화하는 로직 (모델링의 핵심)"""
        ## 예: 특정 파일이 생성되었다면 xe에 경로 추가
        target_path = self.workspace_root / action.target
        if target_path.exists():
            self.xe[action.id] = str(target_path)
            log.info(f"[+] XE Updated: {action.id} -> {target_path}")

    def run_sequence(self, actions: List[PlanAction]):
        """액션 시퀀스를 순차적으로 공명시킴"""
        for action in actions:
            self.dispatch(action)
            ## 여기서 residue 분석 후 sequence를 동적으로 수정하는 로직 삽입 가능

def main():
    with managed_scope(use_hands=False) as server:
        runner = WorkActor(server.get_engine, WORKSPACE)
        ## 동적인 액션 시퀀스 정의
        actions = [
            PlanAction("logic_design", "Create a core logic for data processing.", "core.py", "planner"),
            PlanAction("test_gen", "Write a pytest for the core logic.", "test_core.py", "executor"),
        ]
        runner.run_sequence(actions)