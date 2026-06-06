# bound.context.closer
import sys
from pathlib import Path
from arch.proto.context.signature import ProtoSignature, In, Out
from gov.scope.manager import managed_scope
from gov.scope.thch import ThCh
from gov.sandbox.executor.terminal.executor import TerminalExecutor
from gov.sandbox.executor.terminal.definition import TerminalAction
from watcher.plane.emitter import get_logger

log = get_logger("context.closer")

class CrystallizeScript(ProtoSignature):
    """@phase: convergence - 불안정한 텍스트 파동(Markdown)에서 순수한 실행 의도(Bash)만 추출"""
    noisy_text: str = In(desc="LLM이 뱉어낸 설명과 마크다운 찌꺼기가 포함된 원본 응답")
    pure_bash_script: str = Out(desc="백틱(```)이나 부가 설명이 전혀 없는, 터미널에서 즉시 실행 가능한 순수 bash 명령어들")

class ResolveExecutionRupture(ProtoSignature):
    """@phase: oscillating - 실행 중 파열(에러)이 발생했을 때, 관측 결과를 바탕으로 스크립트 위상 반전(수정)"""
    failed_script: str = In(desc="에러를 발생시킨 기존 스크립트")
    error_observation: str = In(desc="터미널에서 반사된 에러 로그 (관측 결과)")
    topological_inversion_script: str = Out(desc="에러 원인이 해소(의존성 반전 등)되어 재타격 가능한 새로운 bash 스크립트")

class LoopClosure:
    def __init__(self, workdir: str = "."):
        self.terminal = TerminalExecutor(working_dir=workdir, terminal_type="subprocess")
        self.extractor = ThCh(CrystallizeScript)
        self.inverter = ThCh(ResolveExecutionRupture)

    def run(self, markdown_path: str, max_retries: int = 3):
        try:
            raw_text = Path(markdown_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            log.error(f"응답 파일을 찾을 수 없습니다: {markdown_path}")
            return

        with managed_scope(use_dphi=True, use_thch=True, dphi_model="local-gemma-3"):
            log.info("[Phase 1: Cognition] 텍스트 찌꺼기 붕괴 및 순수 스크립트 결정화 중...")
            extracted = self.extractor(noisy_text=raw_text)
            current_script = extracted.pure_bash_script

            for attempt in range(1, max_retries + 1):
                log.info(f"\n=== [Attempt {attempt}/{max_retries}] 격리 구역 물리적 타격 준비 ===")
                log.info(f"[주입될 의도(Script)]\n{'-'*40}\n{current_script}\n{'-'*40}")

                ## 다중 줄 스크립트 안전 주입을 위한 임시 응집(Cohesion) 파일
                temp_file = Path("/tmp/surgent_remediation.sh")
                temp_file.write_text(current_script, encoding="utf-8")

                try:
                    ## 격리 터미널 타격 (Action)
                    action = TerminalAction(command=f"bash {temp_file.resolve()}")
                    obs = self.terminal(action=action)
                    
                    log.info("\n[Phase 2: Observation] 타격 결과 반사:")
                    log.info(obs.text)

                    ## [Actuation 연동] 관측 결과에 따른 동적 위상 제어
                    is_rupture = "error" in obs.text.lower() or "no such file" in obs.text.lower()
                    
                    if is_rupture:
                        log.warning("파열(Rupture) 감지. 스크립트 실행 중 에러가 발생했습니다.")
                        
                        if attempt < max_retries:
                            log.info("[Phase 3: Actuation] 관측 결과를 바탕으로 스크립트 위상 반전(Inversion) 시작...")
                            # 에러 로그를 다시 인지 엔진에 던져 스스로 스크립트를 고치도록 유도
                            fixed = self.inverter(
                                failed_script=current_script,
                                error_observation=obs.text
                            )
                            current_script = fixed.topological_inversion_script
                            continue  # 수정된 스크립트로 재타격 루프 진입
                        else:
                            log.error("치유 임계점 도달(Max Retries). 시스템 붕괴를 막기 위해 루프를 종료합니다.")
                            break
                    else:
                        log.info("치유 스크립트가 Attractor에 수렴했습니다. 위상 안정화 완료.")
                        break

                finally:
                    if temp_file.exists():
                        temp_file.unlink()

        # [Phase 4: Closure]
        log.info("[Phase 4: Closure] 터미널 격리 구역 붕괴 및 프로세스 회수")
        self.terminal.close()

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m foldbox.flow.loop.closure <llm_response.md>")
        sys.exit(1)
        
    target_md = sys.argv[1]
    healer = LoopClosure()
    healer.run(target_md)

if __name__ == "__main__":
    main()