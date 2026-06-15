# acps.task.__init__
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = ["RpcTask", "RpcTaskKind"]


class RpcTaskKind(Enum):
    REQUEST = "request"
    NOTIFICATION = "notification"


@dataclass(slots=True)
class RpcTask:
    kind: RpcTaskKind
    message: dict[str, Any]


from acps.task.dispatcher import (  # noqa: E402
    DefaultMessageDispatcher,
    MessageDispatcher,
    NotificationRunner,
    RequestRunner,
)
from acps.task.queue import InMemoryMessageQueue, MessageQueue  # noqa: E402
from acps.task.sender import MessageSender, SenderFactory  # noqa: E402
from acps.task.state import InMemoryMessageStateStore, MessageStateStore  # noqa: E402
from acps.task.supervisor import TaskSupervisor  # noqa: E402

__all__ += [
    "DefaultMessageDispatcher",
    "InMemoryMessageQueue",
    "InMemoryMessageStateStore",
    "MessageDispatcher",
    "MessageQueue",
    "MessageSender",
    "MessageStateStore",
    "NotificationRunner",
    "RequestRunner",
    "SenderFactory",
    "TaskSupervisor",
]
