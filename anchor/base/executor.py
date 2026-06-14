# anchor.base.executor
## @lineage: channel.bridge.litellm.thread_pool_executor
from concurrent.futures import ThreadPoolExecutor

MAX_THREADS = 100
executor = ThreadPoolExecutor(max_workers=MAX_THREADS)
