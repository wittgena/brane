# README

@about: Brane - The Universal Integration Boundary
@generator: gemini-3.1-pro

**Brane** is an advanced structural interface and integration layer designed to provide seamless interoperability across the heterogeneous AI ecosystem. It serves as the connective tissue that standardizes communications between models, protocols, and execution environments, prioritizing architectural modularity, deterministic state management, and clear interface boundaries.

## The Evolution of Brane

Brane emerged to address the challenges of managing rapidly scaling complexity within modern AI infrastructure. The architecture was formed through the systematic synthesis of several foundational frameworks, evolving toward a more sustainable and decoupled design.

1. **Synthesizing Proven Primitives:** Brane builds upon the robust tool-use mechanisms of **OpenHands** and the declarative optimization patterns of **DSPy**. By decomposing these into modular primitives, Brane allows execution environments and optimization pipelines to interact flexibly across a unified boundary.
2. **Standardizing Integration Surfaces:** To address the maintenance burden of handling diverse API specifications and provider-specific quirks, Brane integrated established abstraction patterns inspired by **LlamaIndex** (`readers`, `llms`, `embeddings`). This transitioned the architecture from a highly branched, conditional routing model to a cohesive, unified abstraction layer, significantly improving maintainability.
3. **Protocol Resilience (ACPS & MCPS):** To ensure stability amidst the evolving landscape of AI protocols, Brane established isolated protocol surfaces—**ACPS** (Agent Client Protocol) and **MCPS**. By utilizing Abstract Syntax Tree (AST) manipulation for schema generation, Brane ensures that all communication remains version-locked and strictly typed, independent of the volatility of external library updates.
4. **Event-Driven Observability:** Migrating away from tightly coupled legacy logging, Brane instituted a centralized event-driven telemetry plane (`watcher.plane`). By employing backpressure-aware sliding windows and context propagation, the system guarantees stability and deep trace visibility even under massive multi-agent traffic.

---

## Core Architecture

Brane operates through a strictly partitioned tripartite architecture, facilitating the normalization and secure routing of all AI-related traffic.

### 1. `anchor` (The Interface & Abstraction Plane)

The `anchor` layer manages the physical ingress of traffic, model specifications, and provides a stable surface for external communication.

* **`switch.param` & `entry`:** Acts as the primary compatibility gateway. It acts as a strangler-fig switch to dynamically decouple Brane from external legacy dependencies (like LiteLLM), directing traffic transparently into Brane's modernized execution pipeline.
* **`mcps.types` & `surface`:** Hosts the statically generated, syntax-safe protocol definitions. It serves as the authoritative source for communication schemas and JSON-RPC dispatching.
* **`model`:** Independently manages token counting, encoding, and exact cost calculations across various LLM providers, abstracting commercial APIs into standardized metrics.

### 2. `bound` (The Transport & Router Plane)

The `bound` layer acts as the system's nervous system, transforming, optimizing, and routing data across the execution stack.

* **`transport` & `channel`:** Abstracts the physical data transmission layers, supporting multiple protocols including Server-Sent Events (SSE), Websockets, and standard I/O (Stdio) for isolated sub-process execution.
* **`dsp` & `xor`:** Manages optimization and processing pipelines. This layer provides a modular space for applying logic-level enhancements—such as reasoning chains (CoT) or few-shot bootstrapping—independently of the primary execution flow.
* **`secret` & `auth`:** Provides a clean boundary for zero-trust security, managing credentials, OAuth flows, and context redaction natively.

### 3. `xphi` (The Agent & Execution Plane)

The runtime boundary where normalized inputs are mapped to specific execution topologies, agent loops, and telemetry layers.

* **`agent` & `loop`:** The core cognitive loop. It manages structural schema alignment, streaming utilities, and dynamic tool invocation across heterogeneous topologies.
* **`adapter` (MCP & Llama):** Translates MCP protocols into Brane-native topologies. It orchestrates the coexistence of batteries-included LLM cores and dynamically transduced LlamaIndex modules.
* **`scope.plane` (Telemetry):** The central nervous system for execution tracking. Using `ContextVar` propagation and `SurfacePlane` folding logic, it captures latencies, token consumption, and errors, emitting them as normalized `LogEvent`s to prevent system saturation.

---

## Design Principles

* **Seamless Compatibility:** Through the `anchor.switch` mechanism, the framework maintains support for existing integration standards, ensuring it can be adopted into mature systems without disrupting current workflows.
* **Decoupled Modularity:** By isolating execution logic, provider integrations, and protocol definitions, Brane ensures that updates in one area (e.g., a new model provider API) do not require changes in unrelated architectural components.
* **Structural Integrity:** Through the use of pinned schemas and explicit contract validation, the system minimizes the risks of state desynchronization and runtime errors, providing a stable foundation for complex multi-agent workflows.
* **Resilient Observability:** Telemetry and system logging are treated as first-class citizens. The implementation of event folding and backpressure ensures that the integration boundary never collapses under high load or recursive agent loops.