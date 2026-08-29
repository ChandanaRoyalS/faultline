"""Watch what actually binds in redis-cart: anon + slab, not memory.current (T7.19).

`docker stats` and `memory.current` both count reclaimable page cache, which RDB bgsaves fill and
the kernel drops before it OOM-kills anything. Reading those is what produced T7.13's retracted
90-minute figure. `anon` is the data that cannot be reclaimed.

    uv run python docs/evidence/t7.19-redis-growth/poll.py [samples]
"""

from __future__ import annotations

import datetime
import subprocess
import sys
import time

FIELDS = "^anon |^slab |^file |^inactive_file "


def sh(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


def redis(*args: str) -> str:
    return sh(["docker", "exec", "redis-cart", "redis-cli", *args])


def sample() -> dict[str, int] | None:
    raw = sh(
        [
            "docker",
            "exec",
            "redis-cart",
            "sh",
            "-c",
            f"cat /sys/fs/cgroup/memory.current; grep -E '{FIELDS}' /sys/fs/cgroup/memory.stat",
        ]
    )
    lines = raw.splitlines()
    if not lines:
        return None
    values = {"current": int(lines[0])}
    for line in lines[1:]:
        key, value = line.split()
        values[key] = int(value)
    values["used_memory"] = int(redis("INFO", "memory").split("used_memory:")[1].split()[0])
    values["keys"] = int(redis("DBSIZE"))
    return values


def main() -> None:
    columns = ("anon", "slab", "file", "inactive_file", "current", "used_memory", "keys")
    print("time,elapsed_s," + ",".join(columns), flush=True)
    started = time.time()
    for _ in range(int(sys.argv[1]) if len(sys.argv) > 1 else 40):
        values = sample()
        if values:
            stamp = datetime.datetime.now(datetime.UTC).strftime("%H:%M:%SZ")
            row = ",".join(str(values[c]) for c in columns)
            print(f"{stamp},{time.time() - started:.0f},{row}", flush=True)
        time.sleep(60)


if __name__ == "__main__":
    main()
