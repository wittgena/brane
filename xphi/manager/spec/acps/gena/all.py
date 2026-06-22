# xphi.manager.spec.acps.gena.all
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from xphi.manager.spec.acps.gena import meta, schema, signature
from phase.bind.resolver import resolve_path
from watcher.plane.emitter import get_emitter

log = get_emitter("gena.all")

ACP_ROOT = resolve_path("acp")
SCHEMA_JSON = ACP_ROOT / "schema.json"
META_JSON = ACP_ROOT / "meta.json"
VERSION_FILE = ACP_ROOT / "VERSION"

DEFAULT_REPO = "agentclientprotocol/agent-client-protocol"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Regenerate schema.py and meta.py from the ACP schema.")
    parser.add_argument(
        "--version",
        "-v",
        help=(
            "Git ref (tag/branch) of agentclientprotocol/agent-client-protocol to fetch the schema from. "
            "If omitted, uses the cached schema files or falls back to 'main' when missing."
        ),
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("ACP_SCHEMA_REPO", DEFAULT_REPO),
        help="Source repository providing schema.json/meta.json (default: %(default)s)",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Skip downloading schema files even when a version is provided.",
    )
    parser.set_defaults(format_output=True)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force schema download even if the requested ref is already cached locally.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    version = args.version or os.environ.get("ACP_SCHEMA_VERSION")
    repo = args.repo
    should_download = _should_download(args, version)

    if should_download:
        ref = resolve_ref(version)
        download_schema(repo, ref)
    else:
        ref = resolve_ref(version) if version else _cached_ref()

    if not (SCHEMA_JSON.exists() and META_JSON.exists()):
        log.info("schema/schema.json or schema/meta.json missing; run with --version to fetch them.", file=sys.stderr)
        sys.exit(1)

    schema.generate_schema()
    meta.generate_meta()
    signature.gen_signature(ACP_ROOT)

    if ref:
        log.info(f"Generated schema using ref: {ref}")
    else:
        log.info("Generated schema using local schema files")


def _should_download(args: argparse.Namespace, version: str | None) -> bool:
    env_override = os.environ.get("ACP_SCHEMA_DOWNLOAD")
    if env_override is not None:
        return env_override.lower() in {"1", "true", "yes"}
    if args.no_download:
        return False
    if version:
        if not SCHEMA_JSON.exists() or not META_JSON.exists():
            return True
        cached = _cached_ref()
        if args.force:
            return True
        return cached != resolve_ref(version)
    return not (SCHEMA_JSON.exists() and META_JSON.exists())


def resolve_ref(version: str | None) -> str:
    if not version:
        return "refs/heads/main"
    if version.startswith("refs/"):
        return version
    if re.fullmatch(r"v?\d+\.\d+\.\d+", version):
        value = version if version.startswith("v") else f"v{version}"
        return f"refs/tags/{value}"
    return f"refs/heads/{version}"


def download_schema(repo: str, ref: str) -> None:
    schema_url = f"https://raw.githubusercontent.com/{repo}/{ref}/schema/schema.unstable.json"
    meta_url = f"https://raw.githubusercontent.com/{repo}/{ref}/schema/meta.unstable.json"
    try:
        schema_data = fetch_json(schema_url)
        meta_data = fetch_json(meta_url)
    except RuntimeError as exc:  # pragma: no cover - network error path
        log.info(exc, file=sys.stderr)
        sys.exit(1)

    SCHEMA_JSON.write_text(json.dumps(schema_data, indent=2), encoding="utf-8")
    META_JSON.write_text(json.dumps(meta_data, indent=2), encoding="utf-8")
    VERSION_FILE.write_text(ref + "\n", encoding="utf-8")
    log.info(f"Fetched schema and meta from {repo}@{ref}")


def fetch_json(url: str) -> dict:
    try:
        with urllib.request.urlopen(url) as response:  # noqa: S310 - trusted source configured by repo
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc


def _cached_ref() -> str | None:
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text(encoding="utf-8").strip() or None
    return None


if __name__ == "__main__":
    main()
