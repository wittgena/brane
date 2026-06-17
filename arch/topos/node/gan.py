# arch.topos.node.gan
## @lineage: meta.reflector.cognitive.gan
## @lineage: bound.reflect.cognitive.gan
## @lineage: cognitive.node.gan
## @lineage: cognitive.nerve.node.gan
"""
@desc: Base communication module handling message passing and hierarchical event routing (bubbling) 
       between GanNodes, each possessing an independent asynchronous lifecycle within the topos.
"""
import asyncio
from typing import Optional, Set
from watcher.plane.emitter import get_emitter

log = get_emitter("node.gan")

class Message:
    """
    @desc: Data payload for transmitting state changes or commands between nodes within the tree topos.
           Features a bubble-up attribute to propagate child node events up to the parent context.
    """
    def __init__(self, name: str, bubble: bool = False):
        self.name = name
        self.bubble = bubble
        self.sender: Optional['GanNode'] = None

class GanNode:
    """
    @desc: The fundamental unit (Actor) of the topos, owning its own asynchronous event pump.
           Forms a hierarchical tree structure by establishing parent-child relationships with other GanNodes.
           Each node processes events asynchronously via an independent queue, isolated from external interference.
    """
    def __init__(self, name: str):
        self.name = name
        
        # topos Composition
        self.parent: Optional['GanNode'] = None
        self.children: Set['GanNode'] = set()
        
        # Internal State & Lifecycle Management
        self._queue = asyncio.Queue()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def post_message(self, message: Message):
        """
        @desc: Injects a message received externally or from another node into this node's independent event boundary.
        @param: message The message payload to be processed within the current node's context.
        """
        message.sender = self
        self._queue.put_nowait(message)

    async def run(self):
        """
        @desc: The primary event pump maintaining the node's lifecycle.
               Sequentially consumes messages and controls the event flow within the topos.
        """
        self._running = True
        log.debug(f"[{self.name}] GanNode context activated (Started)")
        
        while self._running:
            message = await self._queue.get()
            
            # @flow: Handle safe context termination signal via Poison Pill pattern
            if message is None:  
                break
                
            await self._dispatch_message(message)
            self._queue.task_done()
            
        log.debug(f"[{self.name}] GanNode context terminated (Terminated)")

    async def _dispatch_message(self, message: Message):
        """
        @desc: Resolves events within the local context by invoking dynamic handlers (on_*) mapped to the message name.
               Based on the topological design, messages with an active bubble property delegate responsibility upwards to the parent.
        """
        handler_name = f"on_{message.name}"
        handler = getattr(self, handler_name, None)
        
        # Local Evaluation: Execute if a matching handler exists
        if handler and callable(handler):
            await handler(message)

        # @flow: Upward topos Propagation (Bubbling)
        if message.bubble and self.parent:
            self.parent.post_message(message)

    def mount(self, child: 'GanNode'):
        """
        @desc: Integrates a child node into the current topos and ignites its independent 
               asynchronous lifecycle as a background task within the parent's context.
        @param: child The target GanNode to be incorporated into the current node's sub-topos.
        """
        child.parent = self
        self.children.add(child)
        
        # @step: Register the child node to the event loop as an independent Actor
        child._task = asyncio.create_task(child.run())
        log.debug(f"Node {child.name} has been mounted to the {self.name} topos.")

    async def unmount(self, child: 'GanNode'):
        """
        @desc: Detaches a child node from the current topos and gracefully shuts down its event pump
               to guarantee lifecycle synchronization and prevent orphan processes.
        @param: child The subordinate GanNode to be detached and terminated.
        """
        if child in self.children:
            ## Detach from topos
            self.children.remove(child)
            child.parent = None
            
            ## @step: Inject a shutdown signal (Poison Pill) into the child's event pump
            child._running = False
            child._queue.put_nowait(None)
            
            ## @step: Lifecycle Sync - Wait until the child's memory and tasks are fully cleared
            if child._task:
                await child._task
            log.debug(f"Node {child.name} has been successfully unmounted from the {self.name} topos.")
    
    def stop(self):
        """@desc: Safely halts the event pump by injecting a Poison Pill."""
        self._running = False
        self._queue.put_nowait(None)