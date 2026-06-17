# arch.topos.state.projection
## @lineage: phase.plane.projection
## @lineage: phase.runtime.surface.projection
"""
@internal: Zero-UI 인지 투영기 (Topological Projection Lens)
@desc: 고차원의 수학적 위상 붕괴 데이터를 인간의 시각적/의미론적 접점(3-Layers)으로 하향 투영
"""
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

class TopologicalState:
    """@model: 위상 공간의 현재 상태를 담는 수학적 아티팩트 (Mock/DTO)"""
    def __init__(self, node_id: str, phase: str, vectors: List[str], entropy: float, is_collapsed: bool):
        self.node_id = node_id
        self.timestamp = datetime.now()
        self.phase = phase            # 예: "IDLE", "DEADLOCK", "FRACTURE"
        self.vectors = vectors        # 붕괴가 발생한 모듈/위상 벡터
        self.entropy = entropy        # 엔트로피 압력 (0.0 ~ 1.0)
        self.is_collapsed = is_collapsed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "timestamp": self.timestamp.isoformat(),
            "phase": self.phase,
            "vectors": self.vectors,
            "entropy": round(self.entropy, 4),
            "is_collapsed": self.is_collapsed
        }

class ZeroCanvas:
    """
    @actor: 3중 비대칭 인터페이스 투영 엔진
    로컬 리소스를 활용하여 정적 파일과 스트림만으로 대시보드를 대체합니다.
    """
    def __init__(self, workspace_root: Path):
        self.root = workspace_root
        self.archive_dir = self.root / ".surgent" / "archives"
        self.static_dir = self.root / ".surgent" / "ui"
        
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.static_dir.mkdir(parents=True, exist_ok=True)

    def _project_semantic_alert(self, state: TopologicalState) -> None:
        """[Layer 1] 텍스트 기반 의미론적 알림 (Slack, Console, Telegram 호환)"""
        alert_icon = "⚠️" if state.is_collapsed else "🟢"
        action_msg = "항상성 복구 개입(Actuation) 승인 대기 중..." if state.is_collapsed else "안정적 위상장 유지 중."
        
        msg = (
            f"\n[Surgent Projection] {alert_icon} 위상 장내 변위 포착 (Φ={state.node_id})\n"
            f" ├─ 관측 시점: {state.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f" ├─ 상태 공간: {state.phase}\n"
            f" ├─ 엔트로피 압력: {state.entropy * 100:.2f}%\n"
            f" ├─ 붕괴 벡터: {', '.join(state.vectors)}\n"
            f" └─ [🛡️] {action_msg}\n"
        )
        ## 로컬 콘솔 방출 (이후 Slack Webhook 등으로 쉽게 파이프라이닝 가능)
        print(msg)

    def _project_markdown_archive(self, state: TopologicalState) -> Path:
        """[Layer 2] 마크다운 정적 아카이빙 (GitOps, Github UI 렌더링 무임승차용)"""
        file_name = f"topology_report_{state.timestamp.strftime('%Y%m%d_%H%M%S')}.md"
        file_path = self.archive_dir / file_name

        md_content = f"""# Surgent Topology Report: {state.node_id}
**Generated:** {state.timestamp.isoformat()} | **Phase:** `{state.phase}`

## 상태 공간 분석 (State Space Analysis)
| 지표 (Metric) | 관측값 (Value) | 임계 상태 (Status) |
|---|---|---|
| **엔트로피 압력** | {state.entropy * 100:.2f}% | {'🚨 붕괴' if state.is_collapsed else '✅ 정상'} |
| **변위 벡터 수** | {len(state.vectors)} | - |

## 관측된 붕괴 벡터 (Fractured Vectors)
"""
        for v in state.vectors:
            md_content += f"- `{v}`\n"

        md_content += "\n> *이 문서는 Surgent Membrane에 의해 자율적으로 투영된 정적 아티팩트입니다.*\n"
        
        file_path.write_text(md_content, encoding="utf-8")
        return file_path

    def _project_local_html(self, state: TopologicalState) -> Path:
        """[Layer 3] Client-Side Rendering 정적 UI (브라우저 GPU 무임승차용)"""
        file_path = self.static_dir / "latest_manifold.html"
        json_data = json.dumps(state.to_dict(), ensure_ascii=False)
        
        ## 외부 라이브러리(D3/Three.js)를 CDN으로 당겨와 로컬 브라우저에서 렌더링하도록 skeleton
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Surgent: Local Manifold Lens</title>
    <style>
        body {{ background-color: #0d1117; color: #c9d1d9; font-family: monospace; padding: 2rem; }}
        .hud {{ border-left: 4px solid {'#f85149' if state.is_collapsed else '#2ea043'}; padding-left: 1rem; }}
    </style>
</head>
<body>
    <h1>Surgent Manifold Lens</h1>
    <div class="hud">
        <h2>Phase: {state.phase}</h2>
        <p>Entropy: {state.entropy}</p>
        <p>Last Sync: {state.timestamp.isoformat()}</p>
    </div>
    
    <!-- 렌더링 엔진 (브라우저 자원 사용) -->
    <script>
        const manifoldData = {json_data};
        console.log("Loaded Mathematical Artifact:", manifoldData);
        // TODO: 여기에 D3.js나 Three.js 로직을 심어 로컬 GPU로 3D 렌더링
    </script>
</body>
</html>
"""
        file_path.write_text(html_content, encoding="utf-8")
        return file_path

    def project(self, state: TopologicalState):
        """@trigger: 붕괴가 관측되었을 때 세 가지 레이어에 동시 투영"""
        self._project_semantic_alert(state)
        md_path = self._project_markdown_archive(state)
        html_path = self._project_local_html(state)
        
        print(f"[Projection] 아티팩트 생성 완료: \n ├─ {md_path}\n └─ {html_path}\n")

if __name__ == "__main__":
    current_dir = Path.cwd()
    canvas = ZeroCanvas(current_dir)
    anomaly_state = TopologicalState(
        node_id="node-51146198060503040",
        phase="DIMENSIONAL_FRACTURE",
        vectors=["self/surgent/bridge/inter/protocol", "theoria/arch/flow/monitor"],
        entropy=0.9421,
        is_collapsed=True
    )
    
    ## 렌즈를 통해 3차원 투영 실행
    canvas.project(anomaly_state)