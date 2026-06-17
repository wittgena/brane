# phase.runtime.surface.sensor
## @lineage: phase.runtime.sensor
## @lineage: phase.node.sensor
import asyncio
import json
import hashlib
import re
from pathlib import Path
from typing import Set, List
import redis.asyncio as airedis
from arch.proto.event.psi import PsiType
from phase.bind.resolver import (
    find_current_self,
    resolve_path,
    resolve_pattern,
)

## config
REDIS_URL = "redis://redis.self"
SENSOR_PREFIX = "sensor:watcher"
SENSOR_KEYLIST = f"{SENSOR_PREFIX}:keylist"

SELF_ROOT = find_current_self()
REDIS_ROOT = resolve_path("surface") / "redis"

watcher_pattern = resolve_pattern()
watcher_regex = re.compile(watcher_pattern)

def safe_decode(v):
    if isinstance(v, bytes):
        return v.decode()
    return v

## util
def key_to_filename(key: str) -> str:
    return key.replace(":", "__") + ".json"


async def fetch_keys(redis) -> Set[str]:
    cursor = b"0"
    keys = set()

    while cursor:
        cursor, batch = await redis.scan(cursor=cursor, count=200)
        for k in batch:
            key = safe_decode(k)
            if watcher_regex.match(key):
                keys.add(key)

        if cursor == b"0":
            break

    return keys


async def dump_key(redis, key: str):
    t = await redis.type(key)
    if t == b"string":
        val = await redis.get(key)
        try:
            data = json.loads(val)
        except Exception:
            data = safe_decode(val)
    elif t == b"hash":
        data = {
            safe_decode(k): safe_decode(v)
            for k, v in (await redis.hgetall(key)).items()
        }
    elif t == b"list":
        data = [safe_decode(v) for v in await redis.lrange(key, 0, -1)]
    elif t == b"set":
        data = sorted(safe_decode(v) for v in await redis.smembers(key))
    elif t == b"zset":
        data = [
            {"member": safe_decode(m), "score": s}
            for m, s in await redis.zrange(key, 0, -1, withscores=True)
        ]
    else:
        data = f"[unsupported] type={safe_decode(t)}"
    out_path = REDIS_ROOT / key_to_filename(key)
    out_path.write_text(
        json.dumps({key: data}, indent=2),
        encoding="utf-8"
    )


## sensor core
async def sense_once(redis) -> List[PsiType]:
    def safe_decode(v):
        if isinstance(v, bytes):
            return v.decode()
        return v

    REDIS_ROOT.mkdir(parents=True, exist_ok=True)
    previous = {
        safe_decode(k)
        for k in await redis.smembers(SENSOR_KEYLIST)
    }

    current = await fetch_keys(redis)
    added = current - previous
    removed = previous - current

    signals: List[PsiType] = []
    for k in sorted(added):
        await dump_key(redis, k)
        signals.append(PsiType(kind="watcher:key_added", tag=k, payload="source: redis"))

    for k in sorted(removed):
        (REDIS_ROOT / key_to_filename(k)).unlink(missing_ok=True)
        signals.append(
            PsiType(
                kind="watcher:key_removed",
                tag="removed",
                payload=""
            )
        )

    pipe = redis.pipeline()
    pipe.delete(SENSOR_KEYLIST)
    if current:
        pipe.sadd(SENSOR_KEYLIST, *current)

    await pipe.execute()
    return signals


## loop
async def main_loop(interval: int = 1):
    print("## Redis Sensor (ε)")
    print(f"[connect] {REDIS_URL}")
    redis = await airedis.from_url(REDIS_URL)
    while True:
        signals = await sense_once(redis)
        if not signals:
            print("[steady] no key changes")
        else:
            for psi in signals:
                print(f"[ψ] {psi.symbol}")

            print(f"[update] emitted={len(signals)}")
        await asyncio.sleep(interval)

def main():
    asyncio.run(main_loop())


if __name__ == "__main__":
    main()