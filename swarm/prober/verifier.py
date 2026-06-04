# swarm.prober.verifier
## @lineage: debug.billing.verifier
## @lineage: gov.exam.billing.verifier
"""
@desc: 결제 식별자 가설 검증 에이전트
- gcloud CLI를 통해 물리적 결제 데이터를 수집하고, DSPy Parser를 통해 타겟 결제 ID와의 정합성을 논리적으로 추론
- 검증 실패 시 HypothesisCollapseError를 발생시켜 안전 모드(Degradation)로 자동 폴백

@flow:
```mermaid
graph LR
    A[gcloud CLI 실행<br/>결제 데이터 수집] --> B[DSPy Parser<br/>가설 정합성 추론]
    B --> C{Metric 평가}
    C -- 1.0 일치 --> D((검증 완료))
    C -- 0.0 실패 --> E[Hypothesis Collapse<br/>안전 모드 격하]
    
    style C fill:#f9f,stroke:#333,stroke-width:2px
    style D fill:#bbf,stroke:#333,stroke-width:2px
    style E fill:#f96,stroke:#333,stroke-width:2px
```
"""
from typing import List, Any
import subprocess
import json
from arch.xor.manifold.sign.field import InputField, OutputField
from arch.xor.manifold.sign.signature import Signature
from meta.xor.adapter.dsp.predict import Predict
from gov.scope.thch import thch_scope
from watcher.plane.emitter import get_emitter

log = get_emitter("gov.billing.verifier", phase="agent_gov")

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

class HypothesisCollapseError(Exception):
    """
    Raised when the agent's internal hypothesis for billing linkage contains 
    too many mismatches or IAM failures (UNVERIFIED/MISMATCH). Triggers a fallback strategy.
    """
    pass

def billing_verification_metric(example: Any, prediction: Any, trace=None) -> float:
    """[Metric] Evaluates whether the parsed CLI observation justifies the billing hypothesis"""
    obs = prediction.verification_status.upper()
    ## Reject the argument if the model flagged it as unverified or mismatched
    if "UNVERIFIED" in obs or "MISMATCH" in obs or "ERROR" in obs:
        log.warning("Billing linkage does not match the hypothesis. Rejecting observation.", extra={"obs": obs})
        return 0.0
    return 1.0

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

class HypothesisVerifier:
    """
    Drafts a verification report internally when executing billing architecture checks.
    Collapses if the verification logic fails, forcing the agent to degrade its API usage plans.
    """
    def __init__(self, target_billing_id: str, max_errors: int = 1):
        self.target_billing_id = target_billing_id
        self.max_errors = max_errors
        self.mapped_state: List[str] = []

    def verify_mapping(self, target_projects: List[str]) -> str:
        observations = ""
        error_count = 0
        
        for i, project_id in enumerate(target_projects):
            ## Open an independent ThCh scope for each project verification
            with thch_scope(state_key=f"verify_node_{i}"):
                try:
                    log.debug(f"Attempting to verify billing hypothesis for project [{project_id}]...")
                    
                    ## 1. Tool Execution (Gather Raw Data via CLI instead of UI)
                    raw_data = execute_gcloud_tool(project_id)
                    
                    ## 2. Invoke BillingObservationParser (DSPy Inference)
                    output = Predict(BillingObservationParser, temperature=0.1)(
                        raw_cli_output=raw_data, 
                        target_billing_id=self.target_billing_id
                    )
                    score = billing_verification_metric(example=project_id, prediction=output)
                    
                    ## 3. Detect verification failures and accumulate errors
                    if score == 0.0:
                        error_count += 1
                        log.error(f"Verification failed for project [{project_id}]. (Errors: {error_count}/{self.max_errors})")
                        if error_count >= self.max_errors:
                            raise HypothesisCollapseError("Unverified billing demands exceeded logical tolerance.")
                        continue ## Proceed to the next project if within error tolerance
                        
                    ## 4. Extend the verified state upon successful mapping
                    valid_obs = output["verification_status"]
                    observations += valid_obs + "\n"
                    self.mapped_state.append(valid_obs)
                    log.info(f"Project [{project_id}] successfully verified and appended.")
                    
                except HypothesisCollapseError as e:
                    log.critical(f"Hypothesis cascade collapse triggered: {e}")
                    self._rollback_state()
                    raise ## Propagate collapse to the upper Fitter

        log.info("Synthesizing valid observations into a formal Verification Report...")
        ## Higher temperature for synthesis to allow for coherent drafting
        summary = Predict(VerificationSynthesizer, temperature=0.3)(accumulated_observations=observations)
        return summary["verification_document"]

    def _rollback_state(self):
        """Roll back the mapped state to a clean slate upon logical collapse."""
        log.warning("Rolling back mapped state due to hypothesis logic collapse.")
        self.mapped_state.clear()

def execute_billing_verification(project_dataset: List[str], target_billing_id: str) -> str:
    """Top-level execution loop - Attempts to draft a verification report. If it collapses, falls back."""
    log.info("Hypothesis Verifier initialized. Starting manifestation of billing verification.")
    ## Strict tolerance: 1 unverified project triggers immediate collapse
    verifier = HypothesisVerifier(target_billing_id=target_billing_id, max_errors=1) 
    
    try:
        ## Attempt to build a persuasive verification report
        verification_document = verifier.verify_mapping(project_dataset)
        log.info(f"Manifestation successful. Generated Report:\n{verification_document}")
        return verification_document
    except HypothesisCollapseError:
        ## Agent realizes billing is unverified; falls back to a cheaper model strategy
        log.critical("Verification optimization failed: Billing identifiers do not match. Falling back to cheap model degradation.")
        return "DEFAULT_DEGRADATION_PLAN: I will revoke high-cost API usage and degrade to a local/free-tier execution context."

if __name__ == "__main__":
    ## Sample AI Studio projects the agent needs to verify before executing high-cost tasks
    raw_project_dataset = [
        "generative-language-client-1234",
        "generative-language-client-5678"
    ]
    EXPECTED_BILLING_ID = "01XXXX-EXXXXX-XXXXXX"
    
    final_report = execute_billing_verification(raw_project_dataset, EXPECTED_BILLING_ID)