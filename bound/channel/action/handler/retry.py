# bound.channel.action.handler.retry
## @lineage: bound.bridge.action.handler.retry
## @lineage: bound.client.handler.retry
## @lineage: bound.handler.retry
## @lineage: bound.channel.handler.retry
from typing import Literal

def completion_with_retries(*args, **kwargs):
    try:
        import tenacity
    except Exception as e:
        raise Exception(f"tenacity import failed please run `pip install tenacity`. Error{e}")

    num_retries = kwargs.pop("num_retries", 3)
    kwargs["max_retries"] = 0
    kwargs["num_retries"] = 0
    retry_strategy: Literal["exponential_backoff_retry", "constant_retry"] = kwargs.pop("retry_strategy", "constant_retry")
    original_function = kwargs.pop("original_function", completion)
    if retry_strategy == "exponential_backoff_retry":
        retryer = tenacity.Retrying(
            wait=tenacity.wait_exponential(multiplier=1, max=10),
            stop=tenacity.stop_after_attempt(num_retries),
            reraise=True,
        )
    else:
        retryer = tenacity.Retrying(
            stop=tenacity.stop_after_attempt(num_retries), reraise=True
        )
    return retryer(original_function, *args, **kwargs)


async def acompletion_with_retries(*args, **kwargs):
    """
    [DEPRECATED]. Use 'acompletion' or router.acompletion instead!
    Executes a litellm.completion() with 3 retries
    """
    try:
        import tenacity
    except Exception as e:
        raise Exception(
            f"tenacity import failed please run `pip install tenacity`. Error{e}"
        )

    num_retries = kwargs.pop("num_retries", 3)
    kwargs["max_retries"] = 0
    kwargs["num_retries"] = 0
    retry_strategy = kwargs.pop("retry_strategy", "constant_retry")
    original_function = kwargs.pop("original_function", completion)
    if retry_strategy == "exponential_backoff_retry":
        retryer = tenacity.AsyncRetrying(
            wait=tenacity.wait_exponential(multiplier=1, max=10),
            stop=tenacity.stop_after_attempt(num_retries),
            reraise=True,
        )
    else:
        retryer = tenacity.AsyncRetrying(stop=tenacity.stop_after_attempt(num_retries), reraise=True)
    return await retryer(original_function, *args, **kwargs)

def responses_with_retries(*args, **kwargs):
    from anchor.action.api.response import responses
    try:
        import tenacity
    except Exception as e:
        raise Exception(
            f"tenacity import failed please run `pip install tenacity`. Error{e}"
        )

    num_retries = kwargs.pop("num_retries", 3)
    kwargs["max_retries"] = 0
    kwargs["num_retries"] = 0
    retry_strategy: Literal["exponential_backoff_retry", "constant_retry"] = kwargs.pop(
        "retry_strategy", "constant_retry"
    )  # type: ignore
    original_function = kwargs.pop("original_function", responses)
    if retry_strategy == "exponential_backoff_retry":
        retryer = tenacity.Retrying(
            wait=tenacity.wait_exponential(multiplier=1, max=10),
            stop=tenacity.stop_after_attempt(num_retries),
            reraise=True,
        )
    else:
        retryer = tenacity.Retrying(stop=tenacity.stop_after_attempt(num_retries), reraise=True)
    return retryer(original_function, *args, **kwargs)


async def aresponses_with_retries(*args, **kwargs):
    from anchor.action.api.aresponse import aresponses
    try:
        import tenacity
    except Exception as e:
        raise Exception(f"tenacity import failed please run `pip install tenacity`. Error{e}")

    num_retries = kwargs.pop("num_retries", 3)
    kwargs["max_retries"] = 0
    kwargs["num_retries"] = 0
    retry_strategy = kwargs.pop("retry_strategy", "constant_retry")
    original_function = kwargs.pop("original_function", aresponses)
    if retry_strategy == "exponential_backoff_retry":
        retryer = tenacity.AsyncRetrying(
            wait=tenacity.wait_exponential(multiplier=1, max=10),
            stop=tenacity.stop_after_attempt(num_retries),
            reraise=True,
        )
    else:
        retryer = tenacity.AsyncRetrying(stop=tenacity.stop_after_attempt(num_retries), reraise=True)
    return await retryer(original_function, *args, **kwargs)