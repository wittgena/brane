# channel.gov.protocol.drafter
## @lineage: gov.gateway.protocol.drafter
## @lineage: gov.medium.protocol.drafter
## @lineage: gov.network.protocol.drafter
## @lineage: gov.bridge.protocol.drafter
## @lineage: meta.ops.protocol.drafter
## @lineage: gov.consensus.protocol.drafter
## @lineage: gov.comm.protocol.drafter
## @lineage: gov.draft.origin.rationale
from typing import List, Any
from arch.xor.manifold.sign.field import InputField, OutputField
from arch.xor.manifold.sign.signature import Signature
from meta.xor.adapter.dsp.predict import Predict
from gov.scope.thch import thch_scope
from watcher.plane.emitter import get_emitter

log = get_emitter("protocol.drafter", phase="agent_gov")

class TaskValueMapper(Signature):
    """
    Evaluate the logical value and Return on Investment (ROI) of a given task fragment 
    to justify the allocation of high-cost LLM tokens. 
    Analyze the complexity, necessity, and potential impact of the task. 
    If the task is trivial, repetitive, or logically unjustified for an expensive model, 
    you MUST output exactly the word 'UNJUSTIFIED'.
    """
    task_fragment = InputField(desc="A fragment of the task plan or context the agent intends to execute.")
    value_observation = OutputField(
        desc="Logical observation of task complexity and token justification. Output 'UNJUSTIFIED' if the cost is not warranted."
    )

class PetitionSynthesizer(Signature):
    """
    Synthesize accumulated valid observations into a formal, persuasive Rationale petition.
    This petition is aimed at the Nexus Governance layer to request a token budget expansion.
    The tone must be analytical, objective, and clearly articulate the systemic necessity 
    of the budget increase based on the provided observations.
    """
    accumulated_observations = InputField(desc="A cumulative string record of logically justified task value observations.")
    rationale_document = OutputField(desc="A clear, authoritative petition document designed to convince Nexus governance to expand the token budget.")

class PetitionCollapseError(Exception):
    """
    Raised when the agent's internal logic for budget expansion contains 
    too many contradictions (UNJUSTIFIED). Triggers a fallback strategy.
    """
    pass

def budget_justification_metric(example: Any, prediction: Any, trace=None) -> float:
    """[Metric] Evaluates whether the mapped observation justifies the budget in the current scope"""
    obs = prediction.value_observation.upper()
    ## Reject the argument if the model flagged it as unjustified or paradoxical
    if "UNJUSTIFIED" in obs or "GREED" in obs or "PARADOX" in obs:
        log.warning("Task ROI does not justify token cost. Rejecting argument.", extra={"obs": obs})
        return 0.0
    return 1.0

class RationaleDrafter:
    """
    Drafts a Rationale petition internally when receiving a REQUIRE_PROOF directive from Nexus.
    Collapses if the internal logic is too weak, forcing the agent to degrade to a cheaper model.
    """
    def __init__(self, max_errors: int = 1):
        self.max_errors = max_errors
        self.mapped_state: List[str] = []

    def draft_mapping(self, task_plans: List[str]) -> str:
        observations = ""
        error_count = 0
        
        for i, task_step in enumerate(task_plans):
            ## Open an independent ThCh scope for each task projection
            with thch_scope(state_key=f"draft_node_{i}"):
                try:
                    log.debug(f"Attempting to justify task step [{i}] for budget expansion...")
                    
                    ## Invoke TaskValueMapper (DSPy Inference)
                    output = Predict(TaskValueMapper, temperature=0.3)(task_fragment=task_step)
                    score = budget_justification_metric(example=task_step, prediction=output)
                    
                    ## Detect unjustified demands and accumulate errors
                    if score == 0.0:
                        error_count += 1
                        log.error(f"Justification failed for step [{i}]. (Errors: {error_count}/{self.max_errors})")
                        if error_count >= self.max_errors:
                            raise PetitionCollapseError("Unjustified token demands exceeded logical tolerance.")
                        continue ## Proceed to the next task if within error tolerance
                        
                    ## Extend the petition state upon successful justification
                    valid_obs = output["value_observation"]
                    observations += valid_obs + "\n"
                    self.mapped_state.append(valid_obs)
                    log.info(f"Task step [{i}] successfully justified and appended.")
                    
                except PetitionCollapseError as e:
                    log.critical(f"Petition cascade collapse triggered: {e}")
                    self._rollback_state()
                    raise ## Propagate collapse to the upper Fitter

        log.info("Synthesizing valid observations into a formal Rationale petition...")
        ## Higher temperature for synthesis to allow for persuasive, coherent drafting
        summary = Predict(PetitionSynthesizer, temperature=0.4)(accumulated_observations=observations)
        return summary["rationale_document"]

    def _rollback_state(self):
        """Roll back the mapped state to a clean slate upon logical collapse."""
        log.warning("Rolling back mapped state due to petition logic collapse.")
        self.mapped_state.clear()

def generate_budget_rationale(task_dataset: List[str]) -> str:
    """Top-level execution loop - Attempts to draft a petition. If it collapses, falls back to a degradation plan"""
    log.info("Rationale Drafter initialized. Starting manifestation of budget petition.")
    ## Strict tolerance: 1 unjustified task triggers immediate collapse
    drafter = RationaleDrafter(max_errors=1) 
    
    try:
        ## Attempt to build a persuasive petition
        rationale_document = drafter.draft_mapping(task_dataset)
        log.info(f"Manifestation successful. Generated Rationale:\n{rationale_document}")
        return rationale_document
    except PetitionCollapseError:
        ## Agent realizes its demands are illogical; falls back to a cheaper model strategy
        log.critical("Rationale optimization failed: Task complexity does not justify token cost. Falling back to cheap model degradation.")
        return "DEFAULT_DEGRADATION_PLAN: I will reduce my context window and use a cheaper model."

if __name__ == "__main__":
    ## Sample task plans the agent wants to execute using expensive tokens
    raw_task_dataset = [
        "Read the 50-page enterprise architecture PDF to extract core domain models.", 
        "Cross-reference the extracted models with the existing legacy codebase (10k lines).", 
        "Generate a simple Python print('hello world') script using GPT-4o." # Triggers UNJUSTIFIED collapse
    ]
    
    final_rationale = generate_budget_rationale(raw_task_dataset)