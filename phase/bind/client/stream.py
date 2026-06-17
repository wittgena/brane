# phase.bind.client.stream
## @lineage: phase.bound.client.stream
## @lineage: phase.reflect.client.stream
import urllib.request
import urllib.parse
import json
import time
import subprocess
import re
import argparse
import traceback
import sys
import os
from dataclasses import dataclass, field
from typing import List, Optional, Generator
from pathlib import Path
from watcher.plane.emitter import get_logger

log = get_logger("client.stream")

class StreamClient:
    """∂Φ boundary reader (SSE → JSON decoding)"""
    def stream(self, req: urllib.request.Request, is_json: bool = True) -> Generator:
        with urllib.request.urlopen(req, timeout=30) as resp:
            buffer = ""
            while True:
                chunk = resp.read(1024).decode("utf-8", errors="ignore")
                if not chunk:
                    break

                buffer += chunk
                lines = buffer.split("\n")
                buffer = lines.pop()

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    if line.startswith("data:"):
                        line = line[5:].strip()

                    if is_json:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            continue
                    else:
                        yield line
