# README

@about: Brane - The Universal Integration Boundary
@generator: gemini-3.1-pro

**Brane** is an advanced structural interface and integration layer designed to provide seamless interoperability across the heterogeneous AI ecosystem. It serves as the connective tissue that standardizes communications between models, protocols, and execution environments, prioritizing architectural modularity, deterministic state management, and clear interface boundaries.

## The Evolution of Brane

Brane emerged to address the challenges of managing rapidly scaling complexity within modern AI infrastructure. The architecture was formed through the systematic synthesis of several foundational frameworks, evolving toward a more sustainable and decoupled design.

1. **Synthesizing Proven Primitives:** Brane builds upon the robust tool-use mechanisms of **OpenHands** and the declarative optimization patterns of **DSPy**. By decomposing these into modular primitives, Brane allows execution environments and optimization pipelines to interact flexibly across a unified boundary.
2. **Standardizing Integration Surfaces:** To address the maintenance burden of handling diverse API specifications and provider-specific quirks, Brane integrated established abstraction patterns inspired by **LlamaIndex** (`readers`, `llms`, `embeddings`). This transitioned the architecture from a highly branched, conditional routing model to a cohesive, unified abstraction layer, significantly improving maintainability.
3. **Protocol Resilience (ACPS & MCPS):** To ensure stability amidst the evolving landscape of AI protocols, Brane established isolated protocol surfaces—**ACPS** (Agent Client Protocol) and **MCPS**. By utilizing Abstract Syntax Tree (AST) manipulation for schema generation, Brane ensures that all communication remains version-locked and strictly typed, independent of the volatility of external library updates.

---

## Core Architecture

Brane operates through a strictly partitioned tripartite architecture, facilitating the normalization and secure routing of all AI-related traffic.

### 1. `anchor` (The Entrypoint & Interface)

The `anchor` layer manages the physical ingress of traffic and provides a stable surface for external communication.

* **`switch.param`:** Acts as the primary compatibility gateway. It preserves existing integration patterns, allowing external systems to communicate with Brane without requiring modification to their legacy routing logic. It transparently directs traffic into Brane's modernized execution pipeline.
* **`surface`:** Hosts the statically generated, syntax-safe protocol definitions. It serves as the authoritative source for communication schemas, ensuring consistent interactions across different protocol versions.

### 2. `bound` (The Adapter & Normalization Layer)

The `bound` layer transforms diverse external inputs into Brane’s internal standardized formats, ensuring consistency across the entire execution stack.

* **`adapter.llama`:** Standardizes model interactions, data ingestion, and embedding logic. By providing a unified interface, it allows developers to swap model providers and data sources with minimal impact on the business logic.
* **`xor` & `dsp`:** Manages optimization and processing pipelines. This layer provides a modular space for applying logic-level enhancements—such as reasoning chains or few-shot bootstrapping—independently of the primary execution flow.
* **`inter` (Provider Isolation):** Provides a clean boundary for external provider integrations. It isolates vendor-specific behaviors, ensuring that the core architecture remains agnostic to individual model provider idiosyncrasies.

### 3. `xphi` (The Execution & Protocol Engine)

The runtime boundary where normalized inputs are mapped to specific execution protocols and physical tool calls.

* **`mcps.client`:** A robust client implementation for the Model Context Protocol. It abstracts transport-level complexity (`stdio`, `sse`, `streamable_http`) and provides reliable session management, ensuring that interactions with concurrent tools remain deterministic.
* **`manager.gateway`:** Ensures that interactions adhere to established system contracts. By verifying incoming contexts and managing state transitions explicitly, it provides a predictable and secure environment for tool actuation.
* **`invoker` & `flow`:** Manages the lifecycle of execution events. It orchestrates the flow from request ingestion and security evaluation to physical tool actuation, maintaining a clear separation between the logic of "what to do" and the mechanism of "how to do it."

---

## Design Principles

* **Seamless Compatibility:** Through the `anchor.switch` mechanism, the framework maintains support for existing integration standards, ensuring it can be adopted into mature systems without disrupting current workflows.
* **Decoupled Modularity:** By isolating execution logic, provider integrations, and protocol definitions, Brane ensures that updates in one area (e.g., a new model provider API) do not require changes in unrelated architectural components.
* **Structural Integrity:** Through the use of pinned schemas and explicit contract validation, the system minimizes the risks of state desynchronization and runtime errors, providing a stable foundation for complex multi-agent workflows.