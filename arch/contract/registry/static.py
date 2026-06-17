# arch.contract.registry.static
import ast
import shutil
import time
import hashlib
from typing import Any, Dict, Type, Protocol, runtime_checkable, FrozenSet, Optional, Mapping
from pathlib import Path
from dataclasses import dataclass

@runtime_checkable
class AssetValidator(Protocol):
    """정적 자산 검증을 위한 커스텀 로직 프로토콜"""
    def analyze(self, source: str, tree: ast.AST) -> Dict[str, Any]: ...

@dataclass(frozen=True)
class StaticSpec:
    """정적 파일이 반드시 지켜야 할 규약 (계약)"""
    requires: FrozenSet[str]
    schema_symbol: Optional[str] = None
    expected_schema: Optional[int] = None

@dataclass(frozen=True)
class AssetMeta:
    validator_class: Type[AssetValidator]
    spec: StaticSpec
    target_path: Path
    backup_dir: Optional[Path] = None

class StaticAssetRegistry:
    """클라우드로 전송되는 정적 스크립트들을 통제하는 단일 진실 공급원"""
    def __init__(self):
        self._assets: Dict[str, AssetMeta] = {}

    @property
    def registered_assets(self) -> Mapping[str, AssetMeta]:
        return self._assets

    def register_asset(self, name: str, path: Path, requires: list, 
                       schema_symbol: Optional[str] = None, expected_schema: Optional[int] = None,
                       backup_dir: Optional[Path] = None):
        spec = StaticSpec(
            requires=frozenset(requires),
            schema_symbol=schema_symbol,
            expected_schema=expected_schema
        )
        def decorator(cls: Type[AssetValidator]):
            cls.__static_spec__ = spec
            self._assets[name] = AssetMeta(
                validator_class=cls, 
                spec=spec, 
                target_path=path,
                backup_dir=backup_dir
            )
            return cls
        return decorator

    def get_asset_hash(self, name: str) -> Optional[str]:
        """자산의 현재 SHA256 해시를 반환"""
        if name not in self._assets:
            return None
        path = self._assets[name].target_path
        if not path.exists():
            return None
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def static_check(self, name: str) -> dict:
        """자산의 정적 무결성을 검증"""
        if name not in self._assets:
            return {"ok": False, "reason": "unregistered_asset", "name": name}

        meta = self._assets[name]
        if not meta.target_path.exists():
            return {"ok": False, "reason": "missing", "path": str(meta.target_path)}

        try:
            source = meta.target_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except SyntaxError as e:
            return {"ok": False, "reason": f"syntax_error: {e}"}
        except Exception as e:
            return {"ok": False, "reason": f"read_error: {e}"}

        # 1. Base Contract Validation
        base_report = self._verify_contract(source, tree, meta.spec)
        if not base_report["ok"]:
            return base_report

        # 2. Custom Validation
        validator = meta.validator_class()
        custom_report = validator.analyze(source, tree)
        if not custom_report.get("ok", True):
            return custom_report

        return {
            "ok": True,
            "path": str(meta.target_path),
            "declared_schema": base_report.get("declared_schema")
        }

    def _verify_contract(self, source: str, tree: ast.AST, spec: StaticSpec) -> dict:
        missing = [s for s in spec.requires if s not in source]
        if missing:
            return {"ok": False, "reason": "missing_symbols", "missing": missing}

        declared_schema = None
        if spec.schema_symbol:
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Name) and t.id == spec.schema_symbol:
                            if isinstance(node.value, ast.Constant):
                                declared_schema = node.value.value
            
            if declared_schema is not None and declared_schema != spec.expected_schema:
                return {
                    "ok": False,
                    "reason": "schema_mismatch",
                    "declared": declared_schema,
                    "expected": spec.expected_schema,
                }

        return {"ok": True, "declared_schema": declared_schema}

    def install_asset(self, name: str, candidate_path: Path) -> dict:
        """후보 파일을 검증 후 정본으로 교체하며, 실패 시 롤백 수행"""
        if name not in self._assets:
            raise ValueError(f"Unregistered asset: {name}")

        if not candidate_path.exists():
            raise FileNotFoundError(f"Candidate not found: {candidate_path}")

        meta = self._assets[name]
        canon_path = meta.target_path
        backup_dir = meta.backup_dir

        # 1. Backup existing file
        backup_path = None
        if canon_path.exists() and backup_dir:
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"{canon_path.name}.{int(time.time())}.bak"
            shutil.copy2(canon_path, backup_path)

        try:
            # 2. Overwrite with candidate
            canon_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate_path, canon_path)

            # 3. Verify the newly installed file
            check = self.static_check(name)
            if not check["ok"]:
                # Revert if checks fail
                if backup_path:
                    shutil.copy2(backup_path, canon_path)
                else:
                    canon_path.unlink(missing_ok=True)
                return {"ok": False, "reason": "candidate_rejected", "details": check}

            return {
                "ok": True, 
                "sha256": self.get_asset_hash(name), 
                "backed_up_to": str(backup_path) if backup_path else None
            }

        except Exception as e:
            # Revert on critical failure (e.g., IO Error)
            if backup_path:
                shutil.copy2(backup_path, canon_path)
            raise RuntimeError(f"Installation failed and reverted. Error: {e}")

static_registry = StaticAssetRegistry()

def asset_contract(
    name: str, path: Path, requires: list = None, 
    schema_symbol: str = None, expected_schema: int = None,
    backup_dir: Path = None
):
    return static_registry.register_asset(name, path, requires or [], schema_symbol, expected_schema, backup_dir)