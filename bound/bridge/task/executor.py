# bound.bridge.task.executor
## @lineage: anchor.surface.executor
## @lineage: anchor.base.executor
## @lineage: anchor.executor
## @lineage: channel.bridge.litellm.thread_pool_executor
from concurrent.futures import ThreadPoolExecutor

MAX_THREADS = 100
executor = ThreadPoolExecutor(max_workers=MAX_THREADS)
