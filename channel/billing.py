# channel.billing
## @lineage: channel.gov.billing
## @lineage: gov.gateway.billing
## @lineage: gov.gateway.service.billing
from typing import List, Any
import subprocess
import json
from arch.xor.manifold.sign.field import InputField, OutputField
from arch.xor.manifold.sign.signature import Signature
from meta.xor.adapter.dsp.predict import Predict
from frame.scope.thch import thch_scope
from frame.hypo.verifier import HypoCollapseError, HypoVerifier
from watcher.plane.emitter import get_emitter

log = get_emitter("service.billing", phase="gov.gateway")

class BillingObservationParser(Signature):
    """
    Parse the raw JSON output from the gcloud CLI tool.
    Evaluate if the output proves that the AI Studio project is linked to the expected GCP Billing ID.
    If the linkage is invalid, permission is denied, or it does not match, output exactly 'UNVERIFIED' or 'MISMATCH'.
    """
    raw_cli_output = InputField(desc="Raw JSON output string obtained from the gcloud CLI tool.")
    target_billing_id = InputField(desc="The expected GCP Billing Account ID.")
    verification_status = OutputField(
        desc="Logical evaluation of the billing linkage. Output 'UNVERIFIED' or 'MISMATCH' if the hypothesis fails."
    )

class VerificationSynthesizer(Signature):
    """
    Synthesize accumulated valid billing observations into a formal verification report.
    This report is aimed at the Nexus Governance layer to confirm infrastructure integrity.
    """
    accumulated_observations = InputField(desc="A cumulative string record of logically verified billing states.")
    verification_document = OutputField(desc="A clear, authoritative report confirming the billing alignment hypothesis.")

def billing_verification_metric(node_id: str, prediction: Any) -> tuple[float, str]:
    obs = prediction.verification_status
    if "UNVERIFIED" in obs.upper() or "MISMATCH" in obs.upper() or "ERROR" in obs.upper():
        log.warning(f"Linkage mismatch for {node_id}.", extra={"obs": obs})
        return 0.0, obs
    return 1.0, obs

def execute_gcloud_tool(project_id: str) -> str:
    """[Tool] 에이전트가 UI 대신 터미널을 통해 물리적으로 데이터를 수집하는 훅(Hook)"""
    try:
        cmd = ["gcloud", "alpha", "billing", "projects", "describe", project_id, "--format=json"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f'{{"error": "CLI Execution Failed", "details": "{e.stderr.strip()}"}}'
    except FileNotFoundError:
        return '{"error": "gcloud CLI tool not found in agent environment."}'

def execute_billing_verification(project_dataset: List[str], target_billing_id: str) -> str:
    log.info("Starting manifestation of billing verification.")
    
    ## Parser Adapter: Verifier가 주는 범용 인자(raw, ctx)를 매핑
    def billing_parser_adapter(raw: str, ctx: str):
        return Predict(BillingObservationParser, temperature=0.1)(
            raw_cli_output=raw,
            target_billing_id=ctx
        )

    ## Synthesizer Adapter
    def billing_synthesizer_adapter(observations: str):
        result = Predict(VerificationSynthesizer, temperature=0.3)(
            accumulated_observations=observations
        )
        return result.verification_document # 출력 필드 추출까지 도메인에서 책임짐

    verifier = HypoVerifier(
        target_context=target_billing_id,
        tool_func=execute_gcloud_tool,
        parser_func=billing_parser_adapter,
        metric_func=billing_verification_metric,
        synthesizer_func=billing_synthesizer_adapter,
        max_errors=1
    ) 
    
    try:
        return verifier.verify_mapping(project_dataset)
    except HypoCollapseError:
        log.critical("Falling back to cheap model degradation.")
        return "DEFAULT_DEGRADATION_PLAN"

if __name__ == "__main__":
    ## Sample AI Studio projects the agent needs to verify before executing high-cost tasks
    raw_project_dataset = [
        "generative-language-client-1234",
        "generative-language-client-5678"
    ]
    EXPECTED_BILLING_ID = "01XXXX-EXXXXX-XXXXXX"
    
    final_report = execute_billing_verification(raw_project_dataset, EXPECTED_BILLING_ID)