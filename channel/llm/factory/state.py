# channel.llm.factory.state
## @lineage: agent.llm.factory.state
## @lineage: gov.lango.llm.factory.state
## @lineage: gov.langos.llm.factory.state
## @lineage: langos.actor.factory.state
## @lineage: bound.reflect.state.factory
## @lineage: bound.reflector.state.factory
from abc import ABC, abstractmethod
import os
from pathlib import Path
from pydantic import SecretStr
from channel.llm.driver import Driver
from agent.llm.actor import Agent
from gov.sandbox.field.tool import Tool
from agent.disc.context import AgentContext
from arch.proto.schema.resonance import BridgeEvent
from phase.bind.client.engine.local import SERVER_PORT, MODEL_NAME
from phase.bind.resolver import resolve_path
from phase.bind.client.engine.base import BaseEngine

RES_ROOT = resolve_path("res")

class ClosureWorkspaceProxy:
    """얇은 점막(Proxy) 객체 - SpaceNode가 직접 띄운 컨테이너와의 순수 통신만을 담당"""
    def __init__(self, host_url: str, workspace_ref: str = None, working_dir: str = "."):
        self.host_url = host_url
        self.workspace_ref = workspace_ref  # SpaceNode의 container.id
        self.working_dir = working_dir
        self.default_conversation_tags = {"env": "proxy_docker"}

    async def execute_action(self, action):
        """
        물리적 작용부: 향후 docker-py나 HTTP 통신을 통해
        self.workspace_ref 또는 self.host_url 로 직접 명령을 하달하는 로직 구현
        """
        pass

class GraphEngine(BaseEngine):
    def __init__(self, host_url: str, agent_usage: str, workspace_ref: str = None):
        self.workspace = ClosureWorkspaceProxy(host=host_url, workspace_ref=workspace_ref)
        self.agent = create_shell_agent(usage_id=agent_usage)

    def ask(self, prompt, callback):
        from agent.loop.conv.local import LocalConversation
        from channel.llm.driver import content_to_str

        def _internal_callback(event):
            """
            Topological Duck-typing: 
            SDK의 특정 이벤트 타입(MessageAction 등)에 종속되지 않고,
            들어오는 파동(Event)의 형태에 맞춰 능동적으로 메시지를 추출합니다.
            """
            content = ""
            source = ""

            if isinstance(event, str):
                content = event
            elif isinstance(event, dict):
                content = str(event.get("content", ""))
                source = event.get("source", "")
            else:
                if hasattr(event, "content") and event.content:
                    content = str(event.content)
                elif hasattr(event, "llm_message") and event.llm_message:
                    content = "".join(content_to_str(event.llm_message.content))
                source = getattr(event, "source", "")

            if content:
                callback(BridgeEvent(content=content, source=source))

        conv = LocalConversation(agent=self.agent, workspace=self.workspace, callbacks=[_internal_callback])
        try:
            conv.send_message(prompt)
            conv.run()
        finally:
            conv.close()
        return ""

def create_shell_agent(usage_id: str) -> Agent:
    tools = [] 
    return Agent(
        llm=get_shared_llm(usage_id),
        tools=tools,
        system_prompt_filename=str(RES_ROOT / "hands" / "generator.j2"),
    )

hand_context = AgentContext(
    skills=[],
    system_message_suffix=(
        "## @state.output\n"
        "- 출력은 구조화된 호출(json) 또는 간결한 상태 표현으로 나타남\n"
        "- 입력된 경로 및 대상은 실제 구조의 표면으로 간주됨"
    ),
    
    user_message_suffix=(
        "## @phase.execution\n"
        "- mode: minimal\n"
        "- action: log -> close\n"
        "- state: 단일 흐름 실행 후 종료로 수렴"
    )
)