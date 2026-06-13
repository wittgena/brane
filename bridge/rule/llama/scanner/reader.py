# bridge.rule.llama.scanner.reader
## @lineage: bridge.router.scanner.reader
## @lineage: channel.llama.workflow.scanner
import os
import ast
from pathlib import Path
from typing import Dict, Protocol, runtime_checkable

# 1. 느슨한 규격 (Protocol) 정의
# - 시스템 내에서 'scan' 행위를 하는 객체들을 묶어주는 역할만 수행합니다.
# - 강한 결합(상속) 없이, 이 규격을 만족하면 모두 Scannable로 취급(Duck Typing)됩니다.
@runtime_checkable
class Scannable(Protocol):
    def scan(self, *args, **kwargs) -> Dict:
        ...

class ReaderScanner:
    """
    AST를 이용해 import 없이 'load_data'가 있는 클래스를 정적으로 식별하는 스캐너.
    어떤 추상 클래스도 상속받지 않으며, 스스로의 목적에 맞는 scan() 행위만 가집니다.
    """
    def __init__(self, base_path: str | Path):
        self.base_path = Path(base_path)

    def _get_module_path(self, file_path: Path) -> str:
        """파일 경로를 모듈 FQN으로 변환하는 내부 유틸리티"""
        rel_path = file_path.relative_to(Path.cwd())
        return str(rel_path.with_suffix("")).replace(os.sep, ".")

    def scan(self) -> Dict[str, Dict[str, str]]:
        """
        Scannable 프로토콜을 자연스럽게 충족하는 핵심 메서드.
        """
        registry = {}
        
        # readers 하위의 모든 파이썬 파일 탐색
        for file_path in self.base_path.rglob("*.py"):
            if file_path.name == "__init__.py":
                continue
                
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    file_content = f.read()
                    
                # 코드를 실행하지 않고 AST(구문 트리)로 파싱
                tree = ast.parse(file_content)
                
                for node in ast.walk(tree):
                    # 클래스 정의 노드 찾기
                    if isinstance(node, ast.ClassDef):
                        # 클래스 내부에 load_data 메서드가 있는지 확인
                        has_load_data = any(
                            isinstance(n, ast.FunctionDef) and n.name == "load_data"
                            for n in node.body
                        )
                        
                        if has_load_data:
                            # 디렉토리 이름을 포맷(식별자)으로 추정 (예: pymu_pdf, html)
                            format_key = file_path.parent.name 
                            
                            registry[format_key] = {
                                "module": self._get_module_path(file_path),
                                "class": node.name
                            }
            except Exception as e:
                print(f"[Warning] Failed to parse {file_path}: {e}")
                
        return registry

# ==========================================
# 실행 및 검증
# ==========================================
if __name__ == "__main__":
    # 인스턴스화
    scanner = ReaderScanner("brane/channel/llama/readers")
    
    # 구조적 서브타이핑(Protocol) 검증
    # 상속을 하지 않았음에도 시스템은 이를 완벽한 Scannable 객체로 인식합니다.
    if isinstance(scanner, Scannable):
        print("[System] ReaderScanner가 유효한 Scannable 객체로 인식되었습니다.")
        
    # 실제 스캔 실행
    result = scanner.scan()
    print(f"Scanned {len(result)} components.")