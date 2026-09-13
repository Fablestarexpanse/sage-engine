"""
Host machine telemetry for the Nexus admin API (CPU, RAM, optional NVIDIA GPUs).
"""

from __future__ import annotations

import csv
import logging
import platform
import re
import shutil
import subprocess
from io import StringIO
from typing import Any

logger = logging.getLogger(__name__)


def _parse_float(val: str) -> float | None:
    s = val.strip()
    if not s or s.upper() == "N/A" or s == "[N/A]":
        return None
    try:
        return float(s)
    except ValueError:
        m = re.match(r"^([\d.]+)", s)
        return float(m.group(1)) if m else None


def _parse_int(val: str) -> int | None:
    f = _parse_float(val)
    return int(f) if f is not None else None


def _query_nvidia_gpus() -> list[dict[str, Any]]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        proc = subprocess.run(
            [
                exe,
                "--query-gpu=index,name,temperature.gpu,fan.speed,utilization.gpu,"
                "memory.used,memory.total,power.draw,power.limit,clocks.current.graphics",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.debug("nvidia-smi failed: %s", e)
        return []
    if proc.returncode != 0 or not proc.stdout.strip():
        return []

    gpus: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = next(csv.reader(StringIO(line)))
        except csv.Error:
            continue
        if len(row) < 10:
            continue
        idx, name, temp_s, fan_s, util_s, mem_u_s, mem_t_s, pwr_s, pwr_lim_s, clk_s = row[:10]
        idx_n = _parse_int(idx)
        mem_u = _parse_float(mem_u_s)
        mem_t = _parse_float(mem_t_s)
        vram_pct: float | None = None
        if mem_u is not None and mem_t is not None and mem_t > 0:
            vram_pct = round(100.0 * mem_u / mem_t, 1)
        util = _parse_int(util_s)
        gpus.append(
            {
                "index": idx_n if idx_n is not None else 0,
                "name": name.strip(),
                "temperature_c": _parse_int(temp_s),
                "fan_percent": _parse_int(fan_s),
                "gpu_util_percent": util if util is not None else 0,
                "memory_used_mib": mem_u,
                "memory_total_mib": mem_t,
                "memory_percent": vram_pct,
                "power_draw_w": _parse_float(pwr_s),
                "power_limit_w": _parse_float(pwr_lim_s),
                "clock_mhz": _parse_int(clk_s),
            }
        )
    return gpus


def get_host_snapshot() -> dict[str, Any]:
    """Blocking snapshot: call from a thread pool on the async event loop."""
    try:
        import psutil
    except ImportError:
        return {
            "ok": False,
            "error": "psutil not installed",
            "hostname": platform.node(),
            "os": f"{platform.system()} {platform.release()}",
            "cpu_percent": None,
            "memory_percent": None,
            "memory_used_gb": None,
            "memory_total_gb": None,
            "gpus": [],
        }

    mem = psutil.virtual_memory()
    cpu_pct = psutil.cpu_percent(interval=0.12)

    gpus = _query_nvidia_gpus()

    return {
        "ok": True,
        "error": None,
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "python_version": platform.python_version(),
        "cpu_percent": round(cpu_pct, 1),
        "cpu_count": psutil.cpu_count(logical=True),
        "memory_percent": round(mem.percent, 1),
        "memory_used_gb": round(mem.used / (1024**3), 2),
        "memory_total_gb": round(mem.total / (1024**3), 2),
        "gpus": gpus,
    }
