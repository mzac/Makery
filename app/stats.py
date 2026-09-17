"""Live GPU and CPU numbers, for the readout under the progress bar.

A render takes minutes and the bar moves in jumps. "GPU 98%" beside it is the
honest signal that the machine is actually working, and "GPU 0%" while the bar
sits still is the honest signal that it is not.

GPU comes from NVML (nvidia-ml-py), which needs the container to have the GPU
passed through (`gpus: all` in compose) - without it every GPU field is None
and the page simply leaves it out. CPU is read from /proc/stat, which inside a
container is the host's, so it is whole-machine CPU: exactly what is wanted.
"""

import asyncio
import collections
import logging
import os
import time

log = logging.getLogger("makery.stats")

_nvml = None
_handle = None
_cpu_prev: tuple[int, int] | None = None  # (busy, total) jiffies
_snapshot: dict = {"gpu_pct": None, "vram_used_mb": None, "vram_total_mb": None,
                   "cpu_pct": None, "ram_used_mb": None, "ram_total_mb": None,
                   "gpu_temp_c": None, "disk_used_pct": None}

# The last few minutes, for the graph on the parent page. Three minutes at one
# sample a second: enough to see a render start and to see the card cool down
# again, and small enough to send on every poll without thinking about it.
HISTORY = 180
_history: collections.deque = collections.deque(maxlen=HISTORY)

# statvfs is cheap but it is not free, and a disk does not fill up in a second.
DISK_EVERY = 15.0
_disk_at = 0.0
_disk: dict = {"disk_used_pct": None, "disk_free_gb": None, "disk_total_gb": None}


def _init_nvml() -> None:
    global _nvml, _handle
    try:
        import pynvml

        pynvml.nvmlInit()
        _nvml = pynvml
        _handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(_handle)
        log.info("NVML up: %s", name.decode() if isinstance(name, bytes) else name)
    except Exception as exc:
        log.info("no GPU stats (%s); is `gpus: all` set on this service?", exc)
        _nvml = None


def _read_cpu() -> float | None:
    """Whole-machine CPU busy % since the previous call."""
    global _cpu_prev
    try:
        with open("/proc/stat") as f:
            fields = f.readline().split()[1:]
        nums = [int(x) for x in fields[:8]]
        idle = nums[3] + nums[4]  # idle + iowait
        total = sum(nums)
    except (OSError, ValueError, IndexError):
        return None
    busy = total - idle
    prev, _cpu_prev = _cpu_prev, (busy, total)
    if prev is None or total == prev[1]:
        return None
    return round(100 * (busy - prev[0]) / (total - prev[1]), 1)


_GPU_NONE = {"gpu_pct": None, "vram_used_mb": None, "vram_total_mb": None,
             "gpu_temp_c": None}


def _read_gpu() -> dict:
    if _nvml is None:
        return dict(_GPU_NONE)
    try:
        util = _nvml.nvmlDeviceGetUtilizationRates(_handle)
        mem = _nvml.nvmlDeviceGetMemoryInfo(_handle)
        out = {
            "gpu_pct": int(util.gpu),
            "vram_used_mb": int(mem.used / 1e6),
            "vram_total_mb": int(mem.total / 1e6),
            "gpu_temp_c": None,
        }
        try:
            out["gpu_temp_c"] = int(_nvml.nvmlDeviceGetTemperature(
                _handle, _nvml.NVML_TEMPERATURE_GPU))
        except Exception:
            pass  # not every driver reports it; the rest is still worth having
        return out
    except Exception as exc:
        log.debug("nvml read failed: %s", exc)
        return dict(_GPU_NONE)


def _read_ram() -> dict:
    """Whole-machine memory. /proc/meminfo inside a container is the host's,
    which is the number a parent watching the machine wants."""
    try:
        total = available = None
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    available = int(line.split()[1])
                if total is not None and available is not None:
                    break
        if total is None or available is None:
            return {"ram_used_mb": None, "ram_total_mb": None}
        return {"ram_used_mb": round((total - available) / 1024),
                "ram_total_mb": round(total / 1024)}
    except (OSError, ValueError, IndexError):
        return {"ram_used_mb": None, "ram_total_mb": None}


def _read_disk() -> dict:
    """Where their pictures are kept, not the container's own root."""
    global _disk_at, _disk
    now = time.time()
    if now - _disk_at < DISK_EVERY and _disk["disk_total_gb"] is not None:
        return _disk
    _disk_at = now
    try:
        from . import gallery

        st = os.statvfs(gallery.GALLERY_DIR)
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        _disk = {
            "disk_used_pct": round(100 * (total - free) / total, 1) if total else None,
            "disk_free_gb": round(free / 1e9, 1),
            "disk_total_gb": round(total / 1e9, 1),
        }
    except Exception:
        _disk = {"disk_used_pct": None, "disk_free_gb": None, "disk_total_gb": None}
    return _disk


def snapshot() -> dict:
    """The latest numbers. Cheap - filled in by the sampler, not on request."""
    return dict(_snapshot)


def history() -> list:
    """The last few minutes, oldest first, for the graph on the parent page."""
    return list(_history)


async def sampler(every: float = 1.0) -> None:
    """Background task: refresh the snapshot once a second."""
    _init_nvml()
    _read_cpu()  # prime the delta
    while True:
        try:
            _snapshot.update(_read_gpu())
            _snapshot["cpu_pct"] = _read_cpu()
            _snapshot.update(_read_ram())
            _snapshot.update(_read_disk())
            _snapshot["at"] = time.time()
            # Percentages only in the history: the graph draws 0-100 and the
            # current readout beside it carries the real numbers.
            vram = (100 * _snapshot["vram_used_mb"] / _snapshot["vram_total_mb"]
                    if _snapshot.get("vram_total_mb") else None)
            ram = (100 * _snapshot["ram_used_mb"] / _snapshot["ram_total_mb"]
                   if _snapshot.get("ram_total_mb") else None)
            _history.append({
                "t": round(_snapshot["at"]),
                "cpu": _snapshot.get("cpu_pct"),
                "gpu": _snapshot.get("gpu_pct"),
                "vram": round(vram, 1) if vram is not None else None,
                "ram": round(ram, 1) if ram is not None else None,
            })
        except Exception:
            log.exception("stats sample failed")
        await asyncio.sleep(every)
