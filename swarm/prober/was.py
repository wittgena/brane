# swarm.prober.was
## @lineage: debug.prober.was
## @lineage: meta.watcher.prober.was
## @lineage: bound.watcher.prober.was
## @lineage: gov.auth.prober.was
## @lineage: iso.domain.prober.was
## @lineage: agent.domain.prober.was
import sys
import json
import httpx
from typing import List, Dict, Any
from watcher.plane.emitter import get_emitter
from phase.bind.resolver import find_current_self, resolve_path
from meta.ops.was.launcher import api
from gov.scope.manager import managed_scope

SPEC_ROOT = resolve_path("spec")
log = get_emitter("was.prober")

class WASProber:
    """Zero-Touch: 사용자의 개입 없이 라이브 OpenAPI를 완벽히 해석하여 페이로드를 자동 합성합니다."""
    def __init__(self, base_url: str = "http://0.0.0.0:8000"):
        self.base_url = base_url
        self.client = httpx.Client(base_url=base_url, timeout=15.0)
        self.is_healthy: bool = True
        self.context: Dict[str, Any] = {}
        
        log.info("[-] Extracting Live OpenAPI Spec from Launcher...")
        self.openapi_spec: dict = api.openapi()

    def _resolve_schema(self, schema: dict) -> dict:
        """[핵심] 다형성 구조에서 문자열(str) 함정을 피하고 객체(object)를 똑똑하게 찾아냅니다."""
        if not isinstance(schema, dict): return {}
        
        if "$ref" in schema:
            parts = schema["$ref"].split("/")[1:]
            resolved = self.openapi_spec
            for part in parts: resolved = resolved.get(part, {})
            return self._resolve_schema(resolved)
            
        # 다형성 처리: oneOf / anyOf가 있을 때 무지성으로 0번째를 고르지 않음
        for poly_key in ["oneOf", "anyOf"]:
            if poly_key in schema:
                candidates = [self._resolve_schema(s) for s in schema[poly_key]]
                # 1순위: 백엔드 pop() 에러를 방지하기 위해 'properties'를 가진 객체(dict) 타입을 최우선 채택
                for cand in candidates:
                    if cand.get("type") == "object" or "properties" in cand:
                        return cand
                return candidates[0] # 객체가 정 없으면 첫 번째 값으로 폴백

        if "allOf" in schema:
            merged = {}
            for s in schema["allOf"]:
                merged.update(self._resolve_schema(s))
            return merged
            
        return schema

    def _generate_auto_payload(self, schema: dict) -> Any:
        """OpenAPI를 기반으로 100% 자동 더미 데이터를 생성합니다."""
        if not isinstance(schema, dict): return None
        schema = self._resolve_schema(schema)
        
        # 명시된 예시/기본값이 있다면 최우선 신뢰
        if "default" in schema: return schema["default"]
        if "example" in schema: return schema["example"]

        schema_type = schema.get("type", "object")

        if schema_type == "object" or "properties" in schema:
            dummy = {}
            properties = schema.get("properties", {})
            required_fields = schema.get("required", list(properties.keys())) 
            
            for prop_name, prop_schema in properties.items():
                if prop_name in required_fields:
                    dummy[prop_name] = self._generate_auto_payload(prop_schema)
            return dummy
            
        elif schema_type == "string":
            if "enum" in schema and schema["enum"]: return schema["enum"][0]
            return "dummy_string"
        elif schema_type in ("integer", "number"): return 1
        elif schema_type == "boolean": return True
        elif schema_type == "array": return [self._generate_auto_payload(schema.get("items", {}))]
        return None

    def execute_step(self, step: dict):
        if not self.is_healthy: return

        name = step.get("name", "Unknown")
        method = step.get("method", "GET").lower()
        api_path_template = step.get("path", "")
        extract_keys = step.get("extract", {})
        
        log.info(f"[{name}] Engaging topology at {api_path_template}...")

        try:
            actual_url = api_path_template.format(**self.context)
        except KeyError as e:
            log.error(f"  └ [∂Φ:error] Missing context variable: {e}")
            self.is_healthy = False
            return

        payload = None
        if method in ["post", "put", "patch"]:
            route_spec = self.openapi_spec.get("paths", {}).get(api_path_template, {}).get(method, {})
            body_schema = route_spec.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
            
            # 사람의 개입 없이 100% 스키마 기반 페이로드 자동 생성
            payload = self._generate_auto_payload(body_schema)
            if not isinstance(payload, dict): payload = {}
            
            log.info(f"  └ [Φ:payload] Auto-Generated: {json.dumps(payload, ensure_ascii=False)[:100]}...")

        try:
            response = self.client.request(method, actual_url, json=payload)
            response.raise_for_status()
            log.info(f"  └ [Φ:bound] {method.upper()} request successful.")
            
            if response.headers.get("content-type", "").startswith("application/json"):
                data = response.json()
                for ctx_key, response_fields in extract_keys.items():
                    extracted_val = next((data[f] for f in response_fields if f in data), None) if isinstance(data, dict) else None
                    if extracted_val:
                        self.context[ctx_key] = extracted_val
                        log.info(f"  └ [Φ:context] Extracted {ctx_key} -> {extracted_val}")
                    else:
                        log.error(f"  └ [∂Φ:error] Failed to extract {ctx_key}.")
                        self.is_healthy = False

        except httpx.HTTPStatusError as e:
            detail = e.response.text
            try: detail = e.response.json()
            except Exception: pass
            log.error(f"  └ [∂Φ:error] Rejected ({e.response.status_code}): {detail}")
            self.is_healthy = False
        except Exception as e:
            log.error(f"  └ [∂Φ:error] Exception: {e}")
            self.is_healthy = False

    def run_sequence(self, sequence: List[Dict[str, Any]]):
        for step in sequence:
            self.execute_step(step)
            if not self.is_healthy:
                log.info(f"\n[FAIL] Sequence halted at step: {step.get('name')}")
                return
        log.info("\n[SUCCESS] Autopoietic execution loop fully functional.")

def is_server_running(base_url: str) -> bool:
    try:
        return httpx.get(f"{base_url}/ready", timeout=0.5).status_code < 500
    except httpx.RequestError:
        return False

if __name__ == "__main__":
    TARGET_URL = "http://0.0.0.0:8000"

    def run_probe():
        PROBE_SPEC = "" ## SPEC_ROOT에서 spec py를 찾아서 SPEC = {} 를 import
        prober = WASProber(TARGET_URL)
        prober.run_sequence(PROBE_SPEC)

    if is_server_running(TARGET_URL):
        log.info(f"[*] Pre-existing server detected at {TARGET_URL}. Engaging directly...\n")
        run_probe()
    else:
        log.info(f"[*] No server detected at {TARGET_URL}. Bootstrapping local instance...\n")
        with managed_scope():
            run_probe()