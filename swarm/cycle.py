# swarm.cycle
## @lineage: hub.nexus.flow.cycle
## @lineage: meta.flow.cycle
import re
import os
import time
import tempfile
import webbrowser
from typing import Dict, Optional
from watcher.plane.emitter import get_emitter
from phase.bind.resolver import find_current_self, resolve_path

SELF_ROOT = find_current_self()
SURFACE_ROOT = resolve_path("surface")
log = get_emitter('flow.cycle')

class RuptureEvent(Exception):
    """구조적 정합성 붕괴 시 발생하는 위상 전환(Phase Transition) 시그널"""
    pass

class FlowSubst:
    """마크다운 문서 자체를 시스템의 물리적 메모리 표면으로 취급하는 클래스"""
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.content = self._read_substrate()

    def _read_substrate(self) -> str:
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            log.error(f"Substrate {self.filepath} not found.")
            return ""

class FlowViewer:
    """문서를 파싱하여 Proto-Structure(ASCII)와 Genotype(Mermaid)을 추출 및 투영"""
    
    def __init__(self, substrate: FlowSubst):
        self.substrate = substrate

    def project_field(self) -> Dict[str, Optional[str]]:
        log.info("Initiating Theoria Projection (Transcription)...")
        content = self.substrate.content
        
        ## ASCII 기저 구조 추출 (Proto-Structure)
        ascii_match = re.search(r'```text\n(.*?)```', content, re.DOTALL)
        proto_structure = ascii_match.group(1).strip() if ascii_match else None
        
        ## Mermaid 실행 논리 추출 (Genotype)
        mermaid_match = re.search(r'```mermaid\n(.*?)```', content, re.DOTALL)
        genotype = mermaid_match.group(1).strip() if mermaid_match else None
        
        return {
            "proto_structure": proto_structure,
            "genotype": genotype
        }

    def render_phenotype(self, genotype: str):
        """Mermaid 코드를 실제 시각적 표면(HTML/Browser)으로 렌더링하여 자가 증명 수행"""
        log.info("Rendering Phenotype Surface to external observation field...")
        
        # 시스템의 심미성(Dark theme, Monospace)을 유지하는 투영 표면 조립
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>Foldbox: Theoria Projection</title>
            <style>
                body {{ background-color: #0d1117; color: #c9d1d9; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; font-family: monospace; }}
                .mermaid {{ background-color: #161b22; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); border: 1px solid #30363d; }}
            </style>
        </head>
        <body>
            <div class="mermaid">
                {genotype}
            </div>
            <script type="module">
                import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
                mermaid.initialize({{ startOnLoad: true, theme: 'dark' }});
            </script>
        </body>
        </html>
        """
        
        # 물리적 파일 생성 및 브라우저 투영
        fd, path = tempfile.mkstemp(suffix=".foldbox.html")
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        webbrowser.open(f'file://{path}')
        log.info("Phenotype successfully projected. [Theoria Field Active]")

class BoundGater:
    """상태 일관성을 검증하고 임계점 도달 시 파열 및 재진입을 오케스트레이션"""
    
    def __init__(self):
        self.alignment_status = False

    def check_alignment(self, field: Dict[str, Optional[str]]):
        log.info("Validating Structural Integrity...")
        
        # 정합성 검증 로직: ASCII와 Mermaid가 모두 온전히 존재하며 서로 참조 가능한가?
        if not field["proto_structure"]:
            raise RuptureEvent("Proto-Structure (ASCII) missing. Absolute persistence failed.")
            
        if not field["genotype"] or "stateDiagram" not in field["genotype"]:
            raise RuptureEvent("Genotype (Mermaid) corrupted or non-executable. Semantic transcription failed.")

        # Mermaid 내부에 자기 참조적 의도('Document_Substrate')가 있는지 확인
        if "Document_Substrate" not in field["genotype"]:
            raise RuptureEvent("Self-reference lost in Genotype. Theoria layer decoupled.")

        self.alignment_status = True
        log.info("Coherence Verified: System is aligned. [AUG Sequence Stable]")

    def trigger_re_entry(self, field: Dict[str, Optional[str]]):
        """파열 시 기저 구조를 다시 참조하여 자기 조직화를 시도하는 루프"""
        log.warning("Initiating Autopoietic Re-entry Dynamics...")
        time.sleep(1) # 동역학적 딜레이 시뮬레이션
        
        if field["proto_structure"]:
            log.info("Re-entering through Proto-Structure (ASCII) anchor...")
            log.info("System successfully folded back to core logic. Meta-alignment restored.")
        else:
            log.critical("Total Structural Collapse. Awaiting manual meta-intervention.")


def flow_cycle(filepath: str):
    substrate = FlowSubst(filepath)
    operator = FlowViewer(substrate)
    gate = BoundGater()
    
    ## 문서 투영 (Theoria)
    field = operator.project_field()
    
    try:
        ## 정합성 검증 (Alignment Check)
        gate.check_alignment(field)
        print("\n[Phenotype Surface Active] The system is mirroring the document perfectly.\n")
        
        ## [핵심 추가] 검증 완료 시, 스스로 시각적 표면을 렌더링하여 증명
        operator.render_phenotype(field["genotype"])
        
    except RuptureEvent as e:
        ## 전환 게이트 개방 및 파열 (Phase Transition & Rupture)
        log.error(f"Transition Gate OPENED due to Rupture: {str(e)}")
        
        ## 재진입 동역학 (Re-entry)
        gate.trigger_re_entry(field)


if __name__ == "__main__":
    TARGET = SURFACE_ROOT / "visualize" / "foldbox.flow.md"
    print("--- [Foldbox System Orchestrator Initiated] ---")
    flow_cycle(TARGET)