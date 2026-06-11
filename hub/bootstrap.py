# hub.bootstrap
import json
import sys
import time
import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Union
from pathlib import Path
from phase.bind.resolver import find_current_self, resolve_path
from watcher.plane.emitter import get_emitter
from arch.contract.exp.atomic import parse_iso
from arch.contract.registry.static import static_registry
from channel.gov.policy.check.lineage import LineageManager
from channel.gov.policy.check.iso import (
    SystemVersion, RibosValidator, NEXUS_OUTPUT_SCHEMA,
    receive_adapter, transcribe, self_check
)
from meta.xor.residue.harvester import ResidueHarvester

log = get_emitter('hub.bootstrap')

# ==========================================
# 1. Context & Interface (환경 및 규약)
# ==========================================

@dataclass
class BootstrapContext:
    """기존의 전역 변수(PATHS)를 캡슐화하여 의존성 주입(DI)을 가능하게 합니다."""
    root: Path = field(default_factory=find_current_self)
    io_root: Path = field(default_factory=lambda: resolve_path("io"))
    template_root: Path = field(default_factory=lambda: resolve_path("template"))
    
    # 런타임에 결정되는 세부 경로들을 Property로 관리
    @property
    def nexus_script(self) -> Path: return Path(__file__).resolve()
    @property
    def messenger_script(self) -> Path: return self.root / "messenger.py"
    @property
    def ribos_canon(self) -> Path: return self.template_root / "ribos.py"
    @property
    def ribos_backup(self) -> Path: return self.template_root / ".backup"
    @property
    def io_state(self) -> Path: return self.io_root / "state"
    @property
    def harvest_cursor(self) -> Path: return self.io_state / "harvest_cursor.json"
    @property
    def corpus_dir(self) -> Path: return self.io_root / "export"
    @property
    def quarantine(self) -> Path: return self.io_root / "quarantine"
    @property
    def adapters(self) -> Path: return self.root / "adapters"
    @property
    def latest_link(self) -> Path: return self.adapters / "latest"
    @property
    def packets(self) -> Path: return self.root / "packets"
    
    def get_system_version(self) -> SystemVersion:
        return SystemVersion.load(
            nexus_script=self.nexus_script,
            messenger_script=self.messenger_script,
            ribos_canon=self.ribos_canon
        )

    def bootstrap_environment(self) -> None:
        static_registry.register_contract(
            name="ribos_canon",
            path=self.ribos_canon,
            requires=["def main", "def run_genesis"],
            schema_symbol="ribos_OUTPUT_SCHEMA",
            expected_schema=NEXUS_OUTPUT_SCHEMA,
            backup_dir=self.ribos_backup,
            validator_cls=RibosValidator
        )


class BootstrapCommand(Protocol):
    """모든 Bootstrap 커맨드가 준수해야 하는 표준 인터페이스"""
    def execute(self, context: BootstrapContext) -> Any:
        ...


# ==========================================
# 2. Concrete Commands (순수 비즈니스 로직)
# ==========================================

@dataclass
class HarvestCommand(BootstrapCommand):
    """extract residue from local store"""
    store: Optional[Path] = None
    out: Optional[Path] = None
    min_reward: float = 0.5
    max_per_prompt: int = 3
    full: bool = False

    def execute(self, context: BootstrapContext) -> Dict[str, Any]:
        store_path = self.store or (context.io_state.parent / "metadata" / "native_storage")
        out_path = self.out or (context.corpus_dir / f"corpus-{int(time.time())}.jsonl")
        
        h = ResidueHarvester(store_path=store_path, cursor_path=context.harvest_cursor)
        manifest = h.harvest(
            out_path=out_path,
            min_reward=self.min_reward,
            since_cursor=not self.full,
            max_per_prompt=self.max_per_prompt,
        )
        return {"out": str(out_path), **manifest}


@dataclass
class TranscribeCommand(BootstrapCommand):
    """build an messenger packet for the ribos"""
    corpus: Path
    config: Path
    out: Optional[Path] = None
    prev_adapter: Optional[Path] = None

    def execute(self, context: BootstrapContext) -> Dict[str, Any]:
        packet = transcribe(
            corpus_path=self.corpus,
            config_path=self.config,
            out_dir=self.out or context.packets,
            sys_version=context.get_system_version(),
            messenger_script=context.messenger_script,
            ribos_canon=context.ribos_canon,
            prev_adapter=self.prev_adapter,
        )
        return {"packet": str(packet)}


@dataclass
class ReceiveCommand(BootstrapCommand):
    """ingest a freshly-trained adapter directory"""
    path: Path
    auto_promote: Optional[float] = None

    def execute(self, context: BootstrapContext) -> Dict[str, Any]:
        lineage = LineageManager(context.adapters)
        report = receive_adapter(
            incoming_path=self.path,
            lineage=lineage,
            corpus_dir=context.corpus_dir,
            quarantine_dir=context.quarantine,
            sys_version=context.get_system_version(),
            promote_threshold=self.auto_promote,
        )
        result = {
            "gen_id": report.gen_id, "ok": report.ok, 
            "issues": report.issues, "details": report.details
        }
        if not report.ok:
            raise RuntimeError(f"Receive validation failed: {result}")
        return result


@dataclass
class VerifyRibosCommand(BootstrapCommand):
    """check or install canonical ribos"""
    candidate: Optional[Path] = None

    def execute(self, context: BootstrapContext) -> Dict[str, Any]:
        context.bootstrap_environment()
        if self.candidate:
            result = static_registry.install_asset("ribos_canon", self.candidate)
        else:
            result = static_registry.static_check("ribos_canon")
        
        if not result.get("ok"):
            raise RuntimeError(f"Ribos verification failed: {result}")
        return result


# --- Lineage Lifecycle Commands ---

@dataclass
class LineageListCommand(BootstrapCommand):
    def execute(self, context: BootstrapContext) -> List[Dict[str, Any]]:
        lineage = LineageManager(context.adapters)
        return [{
            "gen_id": r.gen_id, "created_at": r.created_at, "promoted": r.promoted,
            "eval_score": r.eval_score, "parent_adapter": r.parent_adapter,
        } for r in lineage.list()]


@dataclass
class LineageShowCommand(BootstrapCommand):
    gen_id: str
    def execute(self, context: BootstrapContext) -> Dict[str, Any]:
        lineage = LineageManager(context.adapters)
        return lineage.get(self.gen_id).manifest


@dataclass
class PromoteCommand(BootstrapCommand):
    """mark adapter as promoted and update latest symlink"""
    gen_id: str
    def execute(self, context: BootstrapContext) -> Dict[str, str]:
        lineage = LineageManager(context.adapters)
        lineage.set_promoted(self.gen_id, True)
        lineage.update_latest_symlink(self.gen_id, context.latest_link)
        return {"promoted": self.gen_id}


@dataclass
class RollbackCommand(BootstrapCommand):
    """revert latest to the previous promoted adapter"""
    def execute(self, context: BootstrapContext) -> Dict[str, str]:
        lineage = LineageManager(context.adapters)
        prev = lineage.previous_promoted(context.latest_link)
        if prev is None:
            raise RuntimeError("no previous promoted adapter to roll back to")
        
        lineage.update_latest_symlink(prev.gen_id, context.latest_link)
        return {"rolled_back_to": prev.gen_id}


@dataclass
class GcCommand(BootstrapCommand):
    """remove old non-promoted adapters"""
    older_than_days: int = 30
    keep_promoted: bool = True

    def execute(self, context: BootstrapContext) -> Dict[str, List[str]]:
        lineage = LineageManager(context.adapters)
        cutoff = time.time() - self.older_than_days * 86400
        removed = []
        for r in lineage.list():
            if r.promoted and self.keep_promoted: continue
            ts = parse_iso(r.created_at)
            if ts is None or ts >= cutoff: continue
            shutil.rmtree(r.path)
            removed.append(r.gen_id)
        return {"removed": removed}


@dataclass
class SelfCheckCommand(BootstrapCommand):
    """verify 3-way system integrity"""
    def execute(self, context: BootstrapContext) -> Dict[str, Any]:
        lineage = LineageManager(context.adapters)
        
        # self_check 함수가 Dictionary를 기대하므로 호환성을 위해 매핑
        paths_dict = {
            "messenger_script": context.messenger_script,
            "ribos_canon": context.ribos_canon,
            # 기타 self_check가 필요로 하는 경로 추가
        }
        
        report = self_check(
            sys_version=context.get_system_version(), 
            paths=paths_dict, 
            lineage=lineage
        )
        if not report.get("ok"):
            raise RuntimeError(f"Self-check failed: {report}")
        return report


# ==========================================
# 3. Invoker (명령 제어 및 스케줄링)
# ==========================================

class BootstrapManager:
    """Bootstrap 명령들을 실행하고 결과를 처리하는 중앙 제어기"""
    def __init__(self, context: BootstrapContext):
        self.context = context
        self.context.bootstrap_environment() # 초기 구동 시 필수 환경 등록

    def submit_command(self, command: BootstrapCommand) -> Optional[Any]:
        cmd_name = command.__class__.__name__
        log.info(f"[BootstrapManager] Executing {cmd_name}...")
        try:
            result = command.execute(self.context)
            # 성공 시 결과는 Manager가 결정하여 출력(또는 로깅)
            if result:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            log.info(f"[BootstrapManager] {cmd_name} completed successfully.")
            return result
        except Exception as e:
            log.error(f"[BootstrapManager] {cmd_name} failed: {e}")
            # 시스템 강제 종료(sys.exit) 대신 Invoker 단에서 유연하게 예외 처리
            return None

if __name__ == "__main__":
    context = BootstrapContext()
    manager = BootstrapManager(context)

    # 예시: GcCommand 실행
    # manager.submit_command(GcCommand(older_than_days=14))
    
    # 예시: LineageListCommand 실행
    # manager.submit_command(LineageListCommand())