# arch.contract.exp.frag
## @lineage: arch.code.exp.frag
## @lineage: nexus.exp.frag
## @lineage: arch.code.frag.exp
## @lineage: xor.block.frag.exp
import inspect
import re
import types
from typing import Callable, ParamSpec, TypeVar, overload

P = ParamSpec("P")
R = TypeVar("R")

@overload
def exp(f: Callable[P, R], version: str | None = None) -> Callable[P, R]: ...

@overload
def exp(f: None = None, version: str | None = None) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def exp(
    f: Callable[P, R] | None = None,
    version: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    if f:
        return _exp(f, version)
    else:
        def decorator(f: Callable[P, R]) -> Callable[P, R]:
            return _exp(f, version)
        return decorator


def _exp(api: Callable[P, R], version: str | None = None) -> Callable[P, R]:
    """Add exp notice to the API's docstring."""
    if inspect.isclass(api):
        api_type = "class"
    elif inspect.isfunction(api):
        api_type = "function"
    elif isinstance(api, property):
        api_type = "property"
    elif isinstance(api, types.MethodType):
        api_type = "method"
    else:
        api_type = str(type(api))

    indent = _get_min_indent_of_docstring(api.__doc__) if api.__doc__ else ""

    version_text = f" (introduced in v{version})" if version else ""
    notice = (
        indent + f"Exp: This {api_type} may change or "
        f"be removed in a future release without warning{version_text}."
    )

    if api_type == "property":
        api.__doc__ = api.__doc__ + "\n\n" + notice if api.__doc__ else notice
    else:
        if api.__doc__:
            api.__doc__ = notice + "\n\n" + api.__doc__
        else:
            api.__doc__ = notice
    return api


def _get_min_indent_of_docstring(docstring_str: str) -> str:
    if not docstring_str or "\n" not in docstring_str:
        return ""

    match = re.match(r"^\s*", docstring_str.rsplit("\n", 1)[-1])
    return match.group() if match else ""
