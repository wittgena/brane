# anchor.bootstrap.ignite
## @lineage: anchor.switch.bootstrap.ignite
## @lineage: anchor.switch.bootstrap
## @lineage: anchor.router.switch.bootstrap
"""
- 모듈이 import 됨과 동시에 즉각적으로 실행되도록 처리할 수도 있고,
- 엔트리 포인트(main.py)에서 명시적으로 ignite()을 호출가능
"""
import sys
from watcher.plane.emitter import get_emitter
from phase.bind.redirector import PhaseAirlock, ModuleRedirector
from phase.bind.resolver import find_current_self

log = get_emitter("bootstrap.ignite", phase="anchor")

_MEMBRANE_ESTABLISHED = False

def ignite():
    """@desc: 시스템 부트스트랩 시퀀스 - 의존성을 bound.router.model)으로 우회"""
    global _MEMBRANE_ESTABLISHED
    if _MEMBRANE_ESTABLISHED:
        log.debug("[Bootstrap] Phase membrane already active. Skipping.")
        return

    log.info("[Bootstrap] Igniting Phase Membrane. Hijacking external dependencies...")
    try:
        canonical_root = find_current_self() / "bound" / "router" / "model"
        redirector = ModuleRedirector(target_package="litellm", local_dir=canonical_root)
        redirector.install()

        PhaseAirlock.establish_resonance(legacy_path="litellm", canonical_path="bound.router.model")
        PhaseAirlock.establish_resonance(
            legacy_path="litellm.types.utils",
            canonical_path="bound.router.model.types.utils",
            submodules=[
                "ModelResponse", 
                "ModelResponseStream", 
                "Usage", 
                "Message",
                "Choices", 
                "StreamingChoices", 
                "Delta",
                "ImageResponse", 
                "EmbeddingResponse", 
                "TextCompletionResponse",
                "ChatCompletionMessageToolCall"
            ]
        )

        PhaseAirlock.establish_resonance(
            legacy_path="litellm.types.completion",
            canonical_path="bound.router.model.types.completion",
            submodules=[
                "ChatCompletionMessageParam", 
                "ChatCompletionUserMessageParam",
                "ChatCompletionAssistantMessageParam", 
                "ChatCompletionSystemMessageParam",
                "ChatCompletionToolMessageParam", 
                "ChatCompletionFunctionMessageParam",
                "ChatCompletionMessageToolCallParam",
                "ChatCompletionContentPartParam"
            ]
        )

        PhaseAirlock.establish_resonance(
            legacy_path="litellm.types.llms.openai",
            canonical_path="bound.router.model.types.llms.openai",
            submodules=[
                "ResponseAPIUsage", 
                "ResponsesAPIResponse",
                "ChatCompletionToolParam",
                "OutputFunctionToolCall"
            ]
        )
        _MEMBRANE_ESTABLISHED = True
        log.info("[Bootstrap] Membrane fully established. External ecosystem successfully assimilated.")
    except Exception as e:
        log.critical(f"[Bootstrap] Failed to establish phase membrane: {e}")
        raise RuntimeError("System assimilation failed. Halting startup to prevent state corruption.") from e