# channel.litellm.thread_pool_executor
## @lineage: gate.litellm.thread_pool_executor
## @lineage: gate.bound.core.thread_pool_executor
## @lineage: blm.bound.core.thread_pool_executor
## @lineage: blm.core.thread_pool_executor
## @lineage: blm.litellm_core_utils.thread_pool_executor
## @lineage: gov.blm.litellm_core_utils.thread_pool_executor
from concurrent.futures import ThreadPoolExecutor

MAX_THREADS = 100
# Create a ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=MAX_THREADS)
