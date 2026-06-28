# README

@about: Brane - The Universal Integration Boundary

**Brane** is an advanced structural interface and integration layer designed to provide seamless interoperability across the heterogeneous AI ecosystem. It serves as the connective tissue that standardizes communications between models, protocols, and execution environments, prioritizing architectural modularity, deterministic state management, and clear interface boundaries.

## The Evolution of Brane

Brane emerged to address the challenges of managing rapidly scaling complexity within modern AI infrastructure. The architecture was formed through the systematic synthesis of several foundational frameworks, evolving toward a more sustainable and decoupled design.

1. **Synthesizing Proven Primitives:** Brane builds upon the robust tool-use mechanisms of established frameworks and the declarative optimization patterns of DSPy. By decomposing these into modular primitives, Brane allows execution environments and optimization pipelines to interact flexibly across a unified boundary.
2. **Standardizing Integration Surfaces:** To address the maintenance burden of handling diverse API specifications and provider-specific quirks, Brane integrated established abstraction patterns (`readers`, `llms`, `embeddings`). This transitioned the architecture from a highly branched, conditional routing model to a cohesive, unified abstraction layer, significantly improving maintainability.
3. **Protocol Resilience (ACP & MCP):** To ensure stability amidst the evolving landscape of AI protocols, Brane established isolated protocol surfaces—**ACP** (Agent Client Protocol) and **MCP** (Model Context Protocol). By utilizing structural schema alignment, Brane ensures that all communication remains version-locked and strictly typed, independent of the volatility of external library updates.
4. **Event-Driven Observability:** Migrating away from tightly coupled legacy logging, Brane instituted a centralized event-driven telemetry plane. By employing context propagation, the system guarantees stability and deep trace visibility even under massive multi-agent traffic.

---

## Core Architecture

Brane operates through a strictly partitioned tripartite architecture, facilitating the normalization and secure routing of all AI-related traffic.

### 1. `xphi` (The Core Engine & Runtime Plane)

The runtime boundary where normalized inputs are mapped to specific execution topologies, agent loops, and telemetry layers. It serves as the system's cognitive and optimization engine.

* **`dsp` & `opt`:** Provides a modular space for applying logic-level enhancements—such as reasoning chains (CoT), few-shot bootstrapping, and parameter optimization—independently of the primary execution flow.
* **`loop` & `manifold`:** Manages the core cognitive loop. It handles streaming utilities, dynamic programmatic execution, and maintains REPL-based execution history and contextual scope.
* **`xor` & `scope.plane` (Telemetry):** Manages zero-trust security boundaries (ciphers, KMS, redaction) and operates the central nervous system for execution tracking. It captures latencies, tool calls, and token consumption, emitting them as normalized traces.

### 2. `anchor` (The Surface & Integration Plane)

The `anchor` layer manages the physical ingress of traffic and provides a stable, normalized surface for external communication, external providers, and diverse data ingestion.

* **`channel.compat` & `switch`:** Acts as the primary compatibility gateway. Utilizing a strangler-fig pattern, it dynamically decouples Brane from external legacy dependencies (like LiteLLM), seamlessly routing traffic to Brane's internal pipelines with zero circular dependencies.
* **`provider` & `inter`:** Abstracts various external LLM providers (OpenAI, Anthropic, Gemini, Ollama) into standardized models, independently managing token encoding, exact cost calculation, and capability resolution.
* **`surface`, `cli` & `readers`:** Hosts static, syntax-safe exception mappings and protocol definitions. It serves as the gateway for external client requests, terminal environments, and extensive document parsing (GitHub, PDF, HTML, Media).

### 3. `bound` (The Transport & Orchestration Plane)

The `bound` layer acts as the system's nervous system, translating external protocols, managing connection states, and dynamically routing data across the execution stack.

* **`adapter` (MCP & Llama):** The core translation boundary. It orchestrates the coexistence of batteries-included LLM cores and dynamically transduced modules (e.g., LlamaIndex), translating MCP (Model Context Protocol) interactions directly into Brane-native topologies.
* **`transport` & `session`:** Abstracts physical data transmission layers, supporting Server-Sent Events (SSE), standard I/O (Stdio), and HTTP wrappers, while managing stateful client connections and asynchronous stream chunking.
* **`agent`, `router` & `auth`:** Utilizes a hybrid microkernel router for lazy-loaded component resolution. It provides a clean boundary for zero-trust security, managing credentials, OAuth flows, and execution risk limits.

---

## Design Principles

* **Seamless Compatibility:** Through the `anchor.channel.switch` mechanism, the framework maintains support for existing integration standards, ensuring it can be adopted into mature systems without disrupting current workflows.
* **Decoupled Modularity:** By isolating execution logic (`xphi`), provider integrations (`anchor`), and protocol translations (`bound`), Brane ensures that updates in one area (e.g., a new model provider API) do not require changes in unrelated architectural components.
* **Structural Integrity & Deterministic Simulation:** Through the use of pinned schemas and explicit contract validation, the system minimizes state desynchronization. Furthermore, the `anchor.tester.simulation` module provides an "Absolute Closed System" sandbox, allowing test intents and execution graphs to be deterministically validated without external API dependencies.
* **Resilient Observability:** Telemetry and system logging are treated as first-class citizens. The implementation of trace tracking and telemetry handlers ensures that the integration boundary never collapses under high load or recursive agent loops, providing total visibility into the execution manifold.