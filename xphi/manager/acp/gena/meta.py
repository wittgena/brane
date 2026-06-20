# xphi.manager.acp.gena.meta
from __future__ import annotations
import json
from pathlib import Path
import anchor.spec.acp.bound as target_pkg
from phase.bind.resolver import resolve_path
from watcher.plane.emitter import get_emitter

log = get_emitter("gena.meta")

ACP_ROOT = resolve_path("workspace") / "acp"
VERSION_FILE = ACP_ROOT / "VERSION"

def get_target_file_path() -> Path:
    """
    import된 패키지의 실제 물리적 경로를 기반으로 meta.py의 최종 저장 위치를 동적으로 추론합니다.
    """
    # target_pkg.__file__ 은 보통 '.../xphi/spec/acp/bound/__init__.py'를 가리킵니다.
    pkg_dir = Path(target_pkg.__file__).resolve().parent
    return pkg_dir / "meta.py"

def main() -> None:
    generate_meta()

def generate_meta() -> None:
    meta_json = ACP_ROOT / "meta.json"
    out_py = get_target_file_path()
    if not meta_json.exists():
        raise SystemExit("schema/meta.json not found. Run gen_schema.py first.")

    data = json.loads(meta_json.read_text("utf-8"))
    agent_methods = data.get("agentMethods", {})
    client_methods = data.get("clientMethods", {})
    version = data.get("version", 1)
    
    header_lines = ["# Generated from schema/meta.json. Do not edit by hand."]
    if VERSION_FILE.exists():
        ref = VERSION_FILE.read_text("utf-8").strip()
        if ref:
            header_lines.append(f"# Schema ref: {ref}")

    out_py.write_text(
        "\n".join(header_lines)
        + "\n"
        + f"AGENT_METHODS = {agent_methods!r}\n"
        + f"CLIENT_METHODS = {client_methods!r}\n"
        + f"PROTOCOL_VERSION = {int(version)}\n",
        encoding="utf-8",
    )
    
    log.info(f"[SUCCESS] Meta file dynamically generated at: {out_py}")

if __name__ == "__main__":
    main()