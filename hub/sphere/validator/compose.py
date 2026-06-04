# hub.sphere.validator.compose
## @lineage: sphere.validator.compose
## @lineage: debugger.sphere.validator.compose
"""
@flow: Ψ(document) → Φ(orchestration surface) → Φ′(compose kernel) → Ψ′(k8s projection)
@topos: metadata_check → compose_validation → dependency_graph → transform_readiness
@focus: service integrity, image visibility, dependency cycles
"""
import sys
import yaml
import re
from pathlib import Path
from typing import Dict, Tuple, List, Any

from arch.xor.block.parser.md import MdAstParser 
from arch.xor.block.extractor import BlockExtractor, Block
from watcher.plane.emitter import get_emitter

log = get_emitter("validator.compose")

class SelfExtractor:
    """@phase: Φ(surface) - MD 문서에서 메타데이터와 Orchestration 블록을 추출"""

    @staticmethod
    def extract(blocks: List[Block]) -> Dict[str, Any]:
        result = {
            "metadata": {},
            "orchestration": None,
            "raw_yaml": ""
        }
        
        for b in blocks:
            # dict의 b.get("content", "") 대신 Block 데이터 클래스의 속성 접근
            content = b.content or ""
            
            # 1. 메타데이터 추출 (@desc, @version 등)
            if b.block_type == "paragraph":
                meta_matches = re.findall(r'@(\w+):\s*(.*)', content)
                for key, val in meta_matches:
                    result["metadata"][key] = val.strip()

            # 2. Orchestration 블록(YAML) 추출
            elif b.block_type == "yaml":
                # 이전 블록이나 현재 컨텍스트가 ORCHESTRATION인 경우
                result["raw_yaml"] = content
                try:
                    result["orchestration"] = yaml.safe_load(content)
                except yaml.YAMLError as e:
                    log.error(f"[Φ:error] YAML 파싱 실패: {e}")

        return result

class ComposeValidator:
    """@phase: Φ′ kernel - Docker Compose 규격 및 배포 안정성 검증"""
    @classmethod
    def validate(cls, data: dict) -> List[str]:
        errors = []
        if not data or "services" not in data:
            return ["[구조 오류] 'services' 정의를 찾을 수 없습니다."]

        services = data.get("services", {})
        all_service_names = set(services.keys())

        for name, spec in services.items():
            # 1. 이미지 및 빌드 컨텍스트 검증
            if "image" not in spec and "build" not in spec:
                errors.append(f"[정의 누락] '{name}': image 또는 build 정의가 필요합니다.")

            # 2. 의존성(depends_on) 정합성 및 순환 참조 검증
            depends_on = spec.get("depends_on", [])
            # list 혹은 dict 형태 대응
            deps = depends_on if isinstance(depends_on, list) else list(depends_on.keys())
            
            for dep in deps:
                if dep not in all_service_names:
                    errors.append(f"[의존성 오류] '{name}'이(가) 존재하지 않는 서비스 '{dep}'에 의존합니다.")
                if dep == name:
                    errors.append(f"[순환 오류] '{name}'이(가) 자기 자신을 참조합니다.")

            # 3. 네트워크 격리 검증 (정의되지 않은 네트워크 사용 여부)
            networks = spec.get("networks", [])
            defined_networks = data.get("networks", {}).keys()
            for net in networks:
                if net not in defined_networks and net != "default":
                    errors.append(f"[네트워크 오류] '{name}'이(가) 미정의 네트워크 '{net}'를 사용합니다.")

        return errors

class FlowValidator:
    """
    @role: Φ′ validation kernel for Kube-Self
    Ψ(document) → Φ(SelfExtractor) → Φ′(ComposeValidator) → Ψ′(Log)
    """
    def __init__(self):
        self.parser_cls = MdAstParser
        self.extractor = BlockExtractor()

    def validate(self, md_path_str: str) -> bool:
        md_path = Path(md_path_str)
        if not md_path.exists():
            log.error(f"[Ψ:error] 파일을 찾을 수 없음: {md_path}")
            return False

        log.info(f"[Ψ:init] '{md_path.name}' 검증 시작")
        
        # 1. Parsing & Extraction (이제 blocks는 List[Block] 타입입니다)
        doc = self.parser_cls(md_path).parse()
        blocks = self.extractor.extract(doc)
        surface = SelfExtractor.extract(blocks)

        # 2. Metadata Logging
        meta = surface["metadata"]
        log.info(f"[Φ:meta] Desc: {meta.get('desc', 'N/A')}")
        log.info(f"[Φ:meta] Version: {meta.get('version', 'N/A')}")

        # 3. Kernel Validation
        if not surface["orchestration"]:
            log.error("[Φ:error] 유효한 Orchestration YAML이 없습니다.")
            return False

        errors = ComposeValidator.validate(surface["orchestration"])

        # 4. Result Projection (Ψ′)
        if errors:
            for err in errors:
                log.info(f"  [∂Φ:fail] {err}")
            log.error("\n[Ψ'] 검증 실패: 안정성 경계(Stability Boundary)를 벗어났습니다.")
            return False
        
        log.info(f"  [Φ:stable] 서비스 구성({len(surface['orchestration'].get('services', {}))}개) 정합성 확인 완료")
        log.info("\n[Ψ'] 검증 통과: 'kompose' 변환 및 K8s 투영 가능 상태입니다.")
        return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m flow.validator <md_path>")
    else:
        FlowValidator().validate(sys.argv[1])