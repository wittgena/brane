# watcher.plane.tester
"""
@phase: global.topos.verification
@intent: Verifies structural invariants of the topos flow field and folding mechanics.
@regimes: [
  {"name": "Laminar", "desc": "Low-density ψ events project directly to Φ surface"},
  {"name": "Turbulence", "desc": "High-density ψ burst triggers folding compression"},
  {"name": "Relaxation", "desc": "Accumulated pressure releases via decay or explicit flush"},
  {"name": "Context Topos", "desc": "Nested flow scopes preserve phase inheritance"}
]
"""
import unittest
import time
from watcher.plane.emitter import get_emitter, flow_scope, _flow_context
from watcher.plane.surface import SurfacePlane
from phase.dynamics.flow.monitor import flow_monitor

class ToposVariants(unittest.TestCase):
    def setUp(self):
        """
        @phase: field.vacuum.reset
        @flow: Φ(t) → Φ(t₀)
        @intent: Reset the BoundPlane phase field and clear telemetry caches before each invariant check.
        """
        SurfacePlane.meter.history.clear()
        SurfacePlane.fold_cache.clear()
        _flow_context.set({})
        
        # [topos Sensor]: 개별 노드에 부착되는 위상 발화기
        self.emitter = get_emitter("test.engine", phase="verify", boundary="core")

    @flow_monitor
    def test_laminar_flow(self):
        """
        @phase: test.regime.laminar
        @flow: ψ_low_density → Φ(surface)
        @invariant: Low-density ψ events must remain uncompressed in the laminar regime.
        """
        with flow_scope(flow_id="FLOW-NORMAL"):
            self.emitter.info("system_initialized")
            self.emitter.info("heartbeat_pulse")
            
        ## laminar regime must not trigger folding
        self.assertEqual(len(SurfacePlane.fold_cache), 0, "Laminar flow should not trigger folding.")
        
        ## events must exist in pressure meter history
        key1 = "verify:test.engine:system_initialized"
        key2 = "verify:test.engine:heartbeat_pulse"
        self.assertIn(key1, SurfacePlane.meter.history)
        self.assertIn(key2, SurfacePlane.meter.history)

    @flow_monitor
    def test_turbulence_and_folding(self):
        """
        @phase: test.regime.turbulence
        @flow: ψ_burst → boundary_pressure → folding_compression → Φ'_summary
        @invariant: High-density ψ bursts must trigger structural folding and mutate into summary nodes.
        """
        target_msg = "processing_unit"
        key = f"verify:test.engine:{target_msg}"

        with flow_scope(flow_id="FLOW-BURST"):
            for _ in range(50):
                self.emitter.info(target_msg)
        
        ## turbulence must generate folding
        self.assertIn(key, SurfacePlane.fold_cache, "High density events must be caught in fold_cache.")
        
        folded_event = SurfacePlane.fold_cache[key]

        ## compression magnitude must reflect burst density
        self.assertGreater(folded_event.fold_count, 1, "Fold count should reflect the burst volume.")

        ## event type must mutate into summary node
        self.assertEqual(folded_event.kind, "summary", "Event kind must be mutated to 'summary'.")

    @flow_monitor
    def test_attenuation_and_implicit_flush(self):
        """
        @phase: test.regime.attenuation
        @flow: accumulation → attenuation_window → new_ψ_event → delayed_flush
        @invariant: Accumulated folding must release implicitly after pressure decay via a new incoming event.
        """
        target_msg = "spam_signal"
        key = f"verify:test.engine:{target_msg}"

        ## induce turbulence to trap events
        for _ in range(20):
            self.emitter.warn(target_msg)
        
        self.assertIn(key, SurfacePlane.fold_cache)
        
        ## simulate pressure relaxation
        time.sleep(SurfacePlane.meter.window + 0.1)
        
        ## new event triggers implicit flush
        self.emitter.info(target_msg)

        ## folding cache must be cleared
        self.assertNotIn(key, SurfacePlane.fold_cache, "Fold cache must be flushed implicitly after pressure drops.")

    @flow_monitor
    def test_explicit_flush(self):
        """
        @phase: test.regime.explicit_flush
        @flow: accumulation → SurfacePlane.flush() → Φ_surface
        @invariant: Explicit flush forces all folded hidden events to the observable surface instantly.
        """
        target_msg = "silent_burst"
        key = f"verify:test.engine:{target_msg}"

        ## induce turbulence
        for _ in range(20):
            self.emitter.crit(target_msg)
            
        self.assertIn(key, SurfacePlane.fold_cache)
        
        ## 강제 플러시 호출 (시간 지연이나 새 이벤트 없이 즉각 방출)
        SurfacePlane.flush()
        
        self.assertEqual(len(SurfacePlane.fold_cache), 0, "Explicit flush must clear all folded events.")

    @flow_monitor
    def test_context_nesting_integrity(self):
        """
        @phase: test.context.nesting
        @flow: Φ_parent → Φ_child_override → Φ_parent_restored
        @invariant: Nested flow scopes must preserve hierarchical phase inheritance and scope restoration.
        """
        with flow_scope(flow_id="FLOW-PARENT", phase="routing"):
            parent_ctx = _flow_context.get()
            self.assertEqual(parent_ctx.get("flow_id"), "FLOW-PARENT")
            self.assertEqual(parent_ctx.get("phase"), "routing")
            
            with flow_scope(flow_id="FLOW-CHILD", boundary="child_worker"):
                child_ctx = _flow_context.get()
                ## child overrides flow_id
                self.assertEqual(child_ctx.get("flow_id"), "FLOW-CHILD")

                ## child defines its own boundary
                self.assertEqual(child_ctx.get("boundary"), "child_worker")

                ## phase must inherit from parent
                self.assertEqual(child_ctx.get("phase"), "routing")
                
            ## after child exit, parent context must be restored
            restored_ctx = _flow_context.get()
            self.assertEqual(restored_ctx.get("flow_id"), "FLOW-PARENT")
            self.assertIsNone(restored_ctx.get("boundary"))

if __name__ == "__main__":
    print("## Initiating Topos Structural Verification for BoundPlane...")
    unittest.main(verbosity=2)