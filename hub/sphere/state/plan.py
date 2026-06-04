# hub.sphere.state.plan
## @lineage: sphere.state.manager.plan
## @lineage: meta.debug.manager.plan
## @lineage: foldbox.manager.tool.planner
## @lineage: loop.manager.tool.planner
## @lineage: foldbox.tool.planner
import _thread
import os
from pathlib import Path
from watcher.plane.emitter import get_emitter
from phase.bind.resolver import resolve_path
from gov.scope.manager import managed_scope

WORKSPACE_ROOT = resolve_path("workspace")
log = get_emitter("manager.plan")

class Planner:
    def __init__(self, engine_factory: callable):
        """
        engine_factory: (agent_usage: str) -> BaseEngine
        SurfaceManager.get_engine이 반환하는 팩토리 함수를 주입받음
        """
        self.engine_factory = engine_factory
        self.intercepted_text = ""
        self.response_count = 0

    def _rupture_callback(self, event):
        if event.source != "agent": return

        self.response_count += 1
        log.info(f"[@monitor] Response detected. Count: {self.response_count}")

        if self.response_count >= 4:
            log.error("[@fatal] Max response limit reached.")
            _thread.interrupt_main()
            return

        if len(event.content.strip()) > 5:
            self.intercepted_text = event.content
            log.warning("[@rupture] Content intercepted. Severing loop.")
            _thread.interrupt_main()

    def _clean_content(self, text: str) -> str:
        """결과물에서 서술형 찌꺼기 제거"""
        if not text: return ""
        garbage_prefixes = ["Okay", "Sure", "I will", "Thinking:", "Based on"]
        lines = text.split('\n')
        cleaned = [l for l in lines if not any(l.strip().startswith(p) for p in garbage_prefixes)]
        return "\n".join(cleaned).strip()

    def _manifest_phase(self, phase_name: str, agent_usage: str, prompt: str, target_file: Path, prefill_anchor: str = "") -> bool:
        log.info(f"\n{'='*50}\nPHASE: {phase_name} | Agent: {agent_usage}\n{'='*50}")
        
        self.intercepted_text = ""
        self.response_count = 0
        
        # 주입된 팩토리를 통해 위상에 맞는 엔진 획득
        engine = self.engine_factory(agent_usage)

        try:
            engine.ask(prompt, callback=self._rupture_callback)
        except KeyboardInterrupt:
            log.info(f"[+] Phase {phase_name} severed by Rupture.")
        
        # 정화 및 저장
        body = self._clean_content(self.intercepted_text)
        final_text = body if body.startswith(prefill_anchor.strip()) else (prefill_anchor + "\n" + body).strip()

        if len(final_text) > len(prefill_anchor) + 2:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            with open(target_file, "w") as f:
                f.write(final_text)
            log.info(f"[+] Manifested: {target_file}")
            return True
        return False

    def run(self):
        plan_file = WORKSPACE_ROOT / "PLAN.md"
        plan_anchor = "# Plan\n## @phase.1"
        if self._manifest_phase("THEORIA", "planner", "Create a plan.", plan_file, plan_anchor):
            with open(plan_file, "r") as f:
                content = f.read()
            self._manifest_phase("ACTION", "executor", f"Execute: {content}", WORKSPACE_ROOT / "main.py", "print('run')")

def main():
    with managed_scope(use_hands=False, show_logs=True) as server:
        engine_factory = server.get_engine() 
        Planner(engine_factory=engine_factory).run()

if __name__ == "__main__":
    main()