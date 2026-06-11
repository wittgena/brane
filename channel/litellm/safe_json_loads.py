# channel.litellm.safe_json_loads
## @lineage: gate.litellm.safe_json_loads
## @lineage: gate.bound.core.safe_json_loads
## @lineage: blm.bound.core.safe_json_loads
## @lineage: blm.core.safe_json_loads
## @lineage: blm.litellm_core_utils.safe_json_loads
## @lineage: gov.blm.litellm_core_utils.safe_json_loads
"""
Helper for safe JSON loading in LiteLLM.
"""

from typing import Any
import json


def safe_json_loads(data: str, default: Any = None) -> Any:
    """
    Safely parse a JSON string. If parsing fails, return the default value (None by default).
    """
    try:
        return json.loads(data)
    except Exception:
        return default
