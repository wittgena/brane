# arch.contract.exp.atomic
## @lineage: arch.code.exp.atomic
## @lineage: nexus.exp.atomic
## @lineage: arch.code.frag.jsonl
## @lineage: xor.block.frag.jsonl
import calendar
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from rich.text import Text
from pydantic import Field
from typing import Annotated
from uuid import UUID
from arch.proto.event.next import next_id

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)

def atomic_write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    n = 0
    with open(tmp, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    tmp.replace(path)
    return n

def atomic_write_text(path: Path, text: str, mode: Optional[int] = None) -> None:
    """문자열 데이터를 원자적(Atomic)으로 파일 write"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        
    if mode is not None:
        os.chmod(tmp, mode)
    tmp.replace(path)

def read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")

def parse_iso(s: str) -> Optional[float]:
    """Return epoch seconds for an ISO-8601 UTC timestamp, or None if unparseable."""
    if not s:
        return None
    try:
        dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return calendar.timegm(dt.timetuple())
    except Exception:
        return None

def utc_now() -> datetime:
    """Return the current time in UTC (``datetime.utcnow`` is deprecated)."""
    return datetime.now(UTC)

def _uuid_to_hex(uuid_obj: UUID) -> str:
    return uuid_obj.hex

ToposId = Annotated[
    str, 
    Field(
        default_factory=next_id, 
        description="Topological Snowflake ID containing Manifold & Vertex context"
    )
]


def display_dict(data) -> Text:
    content = Text()
    if isinstance(data, dict):
        for field_name, field_value in data.items():
            if field_value is None:
                continue  # skip None fields
            content.append(f"\n  {field_name}: ", style="bold")
            if isinstance(field_value, str):
                # Handle multiline strings with proper indentation
                if "\n" in field_value:
                    content.append("\n")
                    for line in field_value.split("\n"):
                        content.append(f"    {line}\n")
                else:
                    content.append(f'"{field_value}"')
            elif isinstance(field_value, (list, dict)):
                content.append(str(field_value))
            else:
                content.append(str(field_value))
    elif isinstance(data, list):
        content.append(f"[List with {len(data)} items]\n")
        for i, item in enumerate(data):
            content.append(f"  [{i}]: ", style="bold")
            if isinstance(item, str):
                content.append(f'"{item}"\n')
            else:
                content.append(f"{item}\n")
    elif isinstance(data, str):
        if "\n" in data:
            content.append("String:\n")
            for line in data.split("\n"):
                content.append(f"  {line}\n")
        else:
            content.append(f'"{data}"')
    elif data is None:
        content.append("null")
    else:
        content.append(str(data))
    return content
