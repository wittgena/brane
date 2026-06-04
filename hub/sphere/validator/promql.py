# hub.sphere.validator.promql
## @lineage: sphere.validator.promql
## @lineage: debugger.sphere.validator.promql
## @lineage: debug.sphere.validator.promql
## @lineage: bound.sphere.validator.promql
## @lineage: gov.sphere.validator.promql
## @lineage: iso.sphere.validator.promql
## @lineage: iso.validator.promql
## @lineage: iso.domain.validator.promql
## @lineage: topos.sphere.validator.promql
## @lineage: foldbox.sphere.validator.promql
## @lineage: surface.sustain.validator.promql
## @lineage: loop.sustain.validator.promql
## @lineage: meta.ops.kube.validator.promql
## @lineage: surface.sphere.kube.validator.promql
"""
@flow: Ψ(document) → Φ(config surface) → Φ′(validation kernel) → Ψ′(log projection)
@topos: parsing → projection → validation → loop-check (closure detection)
@focus: dependency closure, stability, inversion/re-entry integrity
"""
import sys
import yaml
import re
from pathlib import Path
from typing import Dict, Tuple, List, Any
from arch.xor.block.parser.md import MdAstParser
from arch.xor.block.extractor import BlockExtractor
from watcher.plane.emitter import get_emitter

log = get_emitter("validator.promql")

class MarkdownConfigExtractor:
    """@phase: Φ(surface) extraction → path-bound projection"""

    @staticmethod
    def extract(blocks: List[dict]) -> Dict[str, str]:
        configs = {}
        prev_content = ""
        for b in blocks:
            b_type = b.get("block_type")
            content = b.get("content", "")
            if b_type == "paragraph":
                prev_content = content
            elif b_type in ("yaml", "json", "python"):
                if "@path:" in prev_content:
                    match = re.search(r'@path:\s*`?([^`\s]+)`?', prev_content)
                    if match:
                        path = match.group(1)
                        configs[path] = content
                prev_content = ""
            else:
                prev_content = ""

        return configs

class PromQLValidator:
    """@phase: Φ′ kernel (stability + dependency closure)"""
    METRIC_PATTERN = re.compile(r'[a-zA-Z_:][a-zA-Z0-9_:]*')

    @classmethod
    def validate(cls, rule_yaml: str) -> Tuple[List[str], dict, list]:
        try:
            data = yaml.safe_load(rule_yaml)
        except yaml.YAMLError as e:
            return ([f"[YAML Error] {str(e)}"], {}, [])

        records = {}
        alerts = []
        errors = []

        for group in data.get("groups", []):
            for rule in group.get("rules", []):
                if "record" in rule:
                    records[rule["record"]] = rule["expr"]
                elif "alert" in rule:
                    alerts.append(rule)

        for record_name, expr in records.items():
            used_metrics = set(cls.METRIC_PATTERN.findall(expr))
            for metric in used_metrics:
                if metric.endswith("_total") or metric in ["sum", "rate", "increase"]:
                    continue
                if metric.startswith("xphi:") and metric not in records:
                    errors.append(
                        f"[의존성 누락] '{record_name}' → '{metric}'"
                    )

        for alert in alerts:
            used_metrics = set(cls.METRIC_PATTERN.findall(alert["expr"]))
            for metric in used_metrics:
                if metric.startswith("xphi:") and metric not in records:
                    errors.append(
                        f"[알람 오류] '{alert['alert']}' → '{metric}'"
                    )

        for record_name, expr in records.items():
            if "/" in expr and "> 0" not in expr:
                errors.append(
                    f"[연산 불안정] '{record_name}' division guard missing"
                )

        return errors, records, alerts


class LoopTopologyValidator:
    """@phase: Φ′ kernel (Ψ → Φ → Ψ′ closure detection)"""

    @staticmethod
    def validate(configs: Dict[str, str]) -> Dict[str, bool]:
        topology = {
            "sensor_layer": any("otel" in k for k in configs.keys()),
            "memory_layer": any("prometheus.yml" in k for k in configs.keys()),
            "alert_router": any("alertmanager" in k for k in configs.keys()),
            "mutation_surface": any("watcher" in k for k in configs.keys()),
        }

        has_inversion = False
        has_reentry = False
        for path, code in configs.items():
            if "watcher" in path and ("r.set(" in code or "r.publish(" in code):
                has_inversion = True
            if ("runtime" in path or "cli" in path) and (
                "r.get(" in code or "r.subscribe(" in code
            ):
                has_reentry = True

        topology["loop_closure (Ψ -> Φ -> Ψ')"] = has_inversion and has_reentry
        return topology

class PromValidator:
    """
    @role: Φ′ validation kernel

    Ψ(document)
      → Φ(surface extraction)
      → Φ′(kernel validation)
      → Ψ′(log + closure result)
    """
    def __init__(self):
        self.parser_cls = MdAstParser
        self.extractor = BlockExtractor()

    def validate(self, md_path_str: str) -> bool:
        md_path = Path(md_path_str)
        if not md_path.exists():
            log.info(f"[Ψ:error] file not found → {md_path}")
            return False

        log.info(f"[Ψ:init] parsing start → {md_path}\n")
        doc = self._parse(md_path)
        blocks = self._extract_blocks(doc)
        configs = self._extract_configs(blocks)

        self._log_surface(configs)
        self._validate_kernel(configs)
        topology = self._validate_topology(configs)

        return topology.get("loop_closure (Ψ -> Φ -> Ψ')", False)

    def _parse(self, md_path: Path):
        parser = self.parser_cls(md_path)
        return parser.parse()

    def _extract_blocks(self, doc):
        return self.extractor.extract(doc).to_dict()

    def _extract_configs(self, blocks):
        return MarkdownConfigExtractor.extract(blocks)

    def _log_surface(self, configs):
        log.info("[Φ:surface] extracted config paths")
        for path in configs.keys():
            log.info(f"  - {path}")

    def _validate_kernel(self, configs):
        rule_path = next((k for k in configs.keys() if "rules" in k), None)

        if not rule_path:
            log.info("\n[Φ:kernel] no Prometheus rules found")
            return

        log.info("\n[Φ:kernel] validation start")

        errors, records, alerts = PromQLValidator.validate(
            configs[rule_path]
        )

        if errors:
            for err in errors:
                log.info(f"  [∂Φ:error] {err}")
        else:
            log.info(
                f"  [Φ:stable] records={len(records)}, alerts={len(alerts)}"
            )

    def _validate_topology(self, configs):
        log.info("\n[Ψ→Φ→Ψ′] topology check")

        topology = LoopTopologyValidator.validate(configs)

        for layer, is_valid in topology.items():
            status = "ok" if is_valid else "missing"
            log.info(f"  - {layer}: {status}")

        if topology["loop_closure (Ψ -> Φ -> Ψ')"]:
            log.info("\n[closure] autopoietic loop formed")
        else:
            log.info("\n[closure] loop broken → check inversion / re-entry")
        return topology

if __name__ == "__main__":
    if len(sys.argv) < 2:
        log.info("[Ψ:usage] python -m validator.prom <md_path>")
    else:
        PromValidator().validate(sys.argv[1])