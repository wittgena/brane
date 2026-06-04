# swarm.prober.field.entropy
## @lineage: bound.closure.field.entropy
## @lineage: scripts.phase.field.entropy
## @lineage: spec.code.field.entropy
## @lineage: spec.script.field.entropy
## @lineage: topos.watcher.field.entropy
"""
@phase: Friction -> Decay -> Residue Accumulation -> Perturbation Feedback
@flow: The Arrow of Time coupling abstract dynamics with physical degradation
@scale: Macro-field friction surface (Independent SSOT)
"""
import random
from typing import List, Optional
from enum import Enum
from dataclasses import dataclass, field

## Pure Topological State Definitions (기존 의존성 완전 대체)
class PhaseRegime(Enum):
    SINGULARITY = "singularity"
    EMERGENCE = "emergence"      
    OSCILLATION = "oscillation"
    RESONANCE = "resonance"
    SATURATION = "saturation"
    DISSIPATION = "dissipation"
    COLLAPSE = "collapse"

class AttractorType(Enum):
    VOID = "void"
    HARMONIC = "harmonic"
    STOCHASTIC = "stochastic"
    FRACTURED = "fractured"

@dataclass
class ToposState:
    """@scale: The physical embodiment of the cognitive field"""
    regime: PhaseRegime = PhaseRegime.SINGULARITY
    attractor: AttractorType = AttractorType.VOID
    is_active: bool = True
    
    # Tick-based temporal metrics
    age_ticks: float = 0.0
    last_tick_at: int = 0
    
    # Topological Integrity Metrics (0~10)
    coherence: int = 10     # Ex-Hunger: Requires 'Inject' to maintain
    stability: int = 10     # Ex-Happy: Requires harmonious oscillation
    
    # Entropy & Residue
    residue_count: int = 0  # Ex-Poop: Accumulated $xe$
    is_fibrillating: bool = False # Ex-Sick: Systemic instability
    accumulated_errors: int = 0   # Ex-CareMistakes
    
    # Boundary Signals
    needs_attention: bool = False
    attention_reason: str = ""

    # Internal Trackers
    _last_coherence_tick: int = 0
    _last_stability_tick: int = 0
    _next_residue_tick: int = 0

## Entropy Field Mechanics

# Thresholds scaled to Topological Ticks
COHERENCE_DECAY_TICKS = 100
STABILITY_DECAY_TICKS = 80
RESIDUE_DROP_TICKS = 300
FIBRILLATION_CHANCE = 0.005

class FieldEntropy:
    """@scale: The dissipative medium that degrades ToposState over ticks"""

    def __init__(self, base_tension: float = 1.0):
        self.base_tension = base_tension

    def project_entropy(self, state: ToposState, current_tick: int) -> List[str]:
        ## @phase: Ingress of causal time (global_tick) into physical state
        if state.regime == PhaseRegime.COLLAPSE or not state.is_active:
            return []

        tick_delta = current_tick - state.last_tick_at
        state.last_tick_at = current_tick

        if tick_delta <= 0:
            return []

        ## @point: Tension-weighted cognitive wear (인지적 마찰열 적용)
        effective_wear = tick_delta * self.base_tension
        state.age_ticks += effective_wear
        events: List[str] = []

        ## @regime.change: Irreversible phase transitions
        regime_event = self._check_phase_shift(state)
        if regime_event:
            events.append(regime_event)

        if state.regime == PhaseRegime.SINGULARITY:
            return events

        ## @point: Friction execution (위상 붕괴에 따른 자원 소산)
        self._apply_friction(state, current_tick, events)

        ## @point: Residue ($xe$) accumulation
        self._apply_residue(state, current_tick, events)

        return events

    def _apply_friction(self, state: ToposState, current_tick: int, events: List[str]):
        ## @phase: Dissipation of structural integrity
        
        if current_tick - state._last_coherence_tick >= (COHERENCE_DECAY_TICKS / self.base_tension):
            state._last_coherence_tick = current_tick
            if state.coherence > 0: state.coherence -= 1
            if state.coherence <= 1:
                self._trigger_boundary_signal(state, "low_coherence")
                events.append("event:coherence_warning")

        if current_tick - state._last_stability_tick >= (STABILITY_DECAY_TICKS / self.base_tension):
            state._last_stability_tick = current_tick
            if state.stability > 0: state.stability -= 1
            if state.stability <= 1:
                self._trigger_boundary_signal(state, "low_stability")
                events.append("event:stability_warning")

    def _apply_residue(self, state: ToposState, current_tick: int, events: List[str]):
        ## @phase: Accumulation of unhandled topological residue ($xe$)
        
        next_residue = state._next_residue_tick if state._next_residue_tick > 0 else (current_tick + RESIDUE_DROP_TICKS)
        
        if current_tick >= next_residue:
            state.residue_count = min(4, state.residue_count + 1)
            state._next_residue_tick = current_tick + (RESIDUE_DROP_TICKS / self.base_tension) + random.randint(-50, 50)
            events.append("event:residue_dropped")

            if state.residue_count >= 3:
                self._trigger_boundary_signal(state, "residue_overflow")
            
            if state.residue_count >= 4 and not state.is_fibrillating:
                ## @regime.change: Systemic infection triggered by residue overflow
                state.is_fibrillating = True
                events.append("event:fibrillation_start")

        ## 무작위 위상 결함 (Random Fibrillation)
        if not state.is_fibrillating and random.random() < (FIBRILLATION_CHANCE * self.base_tension):
            state.is_fibrillating = True
            self._trigger_boundary_signal(state, "random_fibrillation")
            events.append("event:fibrillation_start")

    def _check_phase_shift(self, state: ToposState) -> Optional[str]:
        """@regime.change: Collapse of current phase and transition to next attractor"""
        thresholds = {
            PhaseRegime.SINGULARITY: 1000,
            PhaseRegime.EMERGENCE: 3000,
            PhaseRegime.OSCILLATION: 10000,
            PhaseRegime.RESONANCE: 25000,
            PhaseRegime.SATURATION: 60000,
            PhaseRegime.DISSIPATION: float("inf"),
        }
        
        next_regime_map = {
            PhaseRegime.SINGULARITY: PhaseRegime.EMERGENCE, 
            PhaseRegime.EMERGENCE: PhaseRegime.OSCILLATION,
            PhaseRegime.OSCILLATION: PhaseRegime.RESONANCE, 
            PhaseRegime.RESONANCE: PhaseRegime.SATURATION,
            PhaseRegime.SATURATION: PhaseRegime.DISSIPATION,
        }

        if state.regime == PhaseRegime.DISSIPATION and state.age_ticks > 100000:
            ## @point: Absolute thermodynamic death
            state.regime = PhaseRegime.COLLAPSE
            state.needs_attention = False
            return "event:total_collapse"

        threshold = thresholds.get(state.regime)
        if threshold and state.age_ticks >= threshold:
            next_regime = next_regime_map[state.regime]
            state.regime = next_regime
            state.attractor = self._resolve_attractor(state, next_regime)
            return f"event:phase_shift:{next_regime.value}"
            
        return None

    def _resolve_attractor(self, state: ToposState, regime: PhaseRegime) -> AttractorType:
        """@point: Causality projection based on accumulated errors"""
        err = state.accumulated_errors
        if regime == PhaseRegime.EMERGENCE: return AttractorType.VOID
        
        if err < 2: return AttractorType.HARMONIC
        elif err < 5: return AttractorType.STOCHASTIC
        else: return AttractorType.FRACTURED

    def _trigger_boundary_signal(self, state: ToposState, reason: str) -> None:
        if not state.needs_attention:
            state.needs_attention = True
            state.attention_reason = reason