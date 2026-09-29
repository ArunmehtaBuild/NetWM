"""N-9 regression check (D-043): what ``pcap_to_flows`` costs on a full day - wall time, peak memory, flows.

    python scripts/pcap_converter_cost.py --pcap D:/CIC-2017-PCAP/Tuesday-WorkingHours.pcap --tag d043
    python scripts/pcap_converter_cost.py --pcap ... --flow-aggregator <old flow_aggregator.py> --tag pre-d043

A slice cannot show a whole-capture cost: the session-cap failure (D-040) appeared only on a full day,
and D-043 keeps one entry per 5-tuple for the whole capture (a continuation's direction). Each call runs
one converter in a fresh process and records its peak working set (Windows) or max RSS (elsewhere), so
two runs compare converters, not a process that already held the other's memory.

Writes results/runs/pcap-converter-cost[-tag]/.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from netwm.utils import save_run


def peak_memory_mb() -> float:
    """This process's peak resident memory so far, in MB."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE  # a 64-bit pseudo-handle, not an int
        kernel32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        kernel32.K32GetProcessMemoryInfo.restype = wintypes.BOOL
        c = Counters()
        c.cb = ctypes.sizeof(c)
        if not kernel32.K32GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb):
            raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
        return c.PeakWorkingSetSize / 2**20
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # KB on Linux


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pcap", required=True)
    ap.add_argument("--flow-aggregator", default=None, help="a flow_aggregator.py to take pcap_to_flows from")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    if args.flow_aggregator:
        spec = importlib.util.spec_from_file_location("baseline_flow_aggregator", args.flow_aggregator)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        pcap_to_flows = module.pcap_to_flows
    else:
        from netwm.features.flow_aggregator import pcap_to_flows

    before = peak_memory_mb()
    started = time.perf_counter()
    flows = pcap_to_flows(args.pcap)
    seconds = time.perf_counter() - started
    result = {"pcap": args.pcap, "flow_aggregator": args.flow_aggregator or "netwm.features.flow_aggregator",
              "seconds": round(seconds, 1), "peak_memory_mb": round(peak_memory_mb(), 1),
              "peak_memory_mb_before_converting": round(before, 1), "flows": int(len(flows)),
              "dropped_packets_session_cap": int(flows.attrs.get("dropped_packets", 0)),
              # equal hashes = the same flow table, row for row (two converters' outputs compared)
              "flows_sha256": hashlib.sha256(pd.util.hash_pandas_object(flows, index=False).to_numpy().tobytes()).hexdigest()}
    save_run("pcap-converter-cost" + (f"-{args.tag}" if args.tag else ""), result,
             config={**vars(args), "decision": "D-043", "command": " ".join(sys.argv)})
    print(result)


if __name__ == "__main__":
    main()
