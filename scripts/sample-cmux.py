#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import pathlib
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass


DEFAULT_DURATION_SECONDS = 20
DEFAULT_INTERVAL_MS = 1


@dataclass(frozen=True)
class Process:
    pid: int
    cpu: str
    rss: str
    command: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find the current cmux app process and run macOS sample against it. "
            "If multiple cmux app processes are running, list them and require --pid."
        )
    )
    parser.add_argument("--pid", type=int, help="sample this pid instead of auto-detecting cmux")
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_DURATION_SECONDS,
        help=f"sampling duration in seconds (default: {DEFAULT_DURATION_SECONDS})",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_MS,
        help=f"sampling interval in milliseconds (default: {DEFAULT_INTERVAL_MS})",
    )
    parser.add_argument(
        "--out-dir",
        type=pathlib.Path,
        default=pathlib.Path.home() / "Desktop" / "cmux-samples",
        help="directory for sample output (default: ~/Desktop/cmux-samples)",
    )
    parser.add_argument("--list", action="store_true", help="list detected cmux app processes and exit")
    return parser.parse_args()


def ps_processes() -> list[Process]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,pcpu=,rss=,command="],
        check=True,
        capture_output=True,
        text=True,
    )
    processes: list[Process] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(maxsplit=3)
        if len(parts) != 4:
            continue
        pid_raw, cpu, rss, command = parts
        try:
            pid = int(pid_raw)
        except ValueError:
            continue
        processes.append(Process(pid=pid, cpu=cpu, rss=rss, command=command))
    return processes


def is_cmux_app_process(process: Process) -> bool:
    command = process.command
    first_arg = command.split(maxsplit=1)[0]
    executable_name = pathlib.Path(first_arg).name

    if executable_name in {"cmux", "cmux DEV", "cmux STAGING", "cmux NIGHTLY"}:
        return "/Contents/MacOS/" in first_arg

    return bool(
        re.search(
            r"/cmux(?: DEV(?: [^/]+)?| STAGING| NIGHTLY)?\.app/Contents/MacOS/cmux(?: DEV| NIGHTLY)?(?:\s|$)",
            command,
        )
    )


def find_cmux_processes() -> list[Process]:
    this_pid = os.getpid()
    return [
        process
        for process in ps_processes()
        if process.pid != this_pid and is_cmux_app_process(process)
    ]


def print_processes(processes: list[Process]) -> None:
    if not processes:
        print("No cmux app processes found.")
        return

    print("Detected cmux app processes:")
    print(f"{'PID':>8} {'CPU%':>7} {'RSS_KB':>10} COMMAND")
    for process in sorted(processes, key=lambda item: item.pid):
        print(f"{process.pid:>8} {process.cpu:>7} {process.rss:>10} {process.command}")


def live_process(pid: int) -> bool:
    return subprocess.run(["ps", "-p", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def choose_pid(args: argparse.Namespace) -> int:
    if args.pid is not None:
        if not live_process(args.pid):
            sys.exit(f"sample-cmux: --pid {args.pid} does not name a live process")
        return args.pid

    processes = find_cmux_processes()
    if args.list:
        print_processes(processes)
        raise SystemExit(0)

    if len(processes) == 1:
        return processes[0].pid

    print_processes(processes)
    if not processes:
        sys.exit("sample-cmux: start cmux, reproduce the slowdown, then run this script again")
    sys.exit("sample-cmux: multiple cmux processes found; rerun with --pid <pid>")


def output_path(out_dir: pathlib.Path, pid: int) -> pathlib.Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return out_dir.expanduser() / f"cmux-{pid}-{stamp}.sample.txt"


def main() -> int:
    args = parse_args()
    if args.duration <= 0:
        sys.exit("sample-cmux: --duration must be greater than 0")
    if args.interval <= 0:
        sys.exit("sample-cmux: --interval must be greater than 0")

    pid = choose_pid(args)
    out_path = output_path(args.out_dir, pid)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    command = ["sample", str(pid), str(args.duration), str(args.interval), "-file", str(out_path)]
    print(f"Sampling cmux pid {pid} for {args.duration}s at {args.interval}ms interval...", flush=True)
    result = subprocess.run(command, text=True)
    if result.returncode != 0:
        print(
            "sample-cmux: sample failed. If macOS denied access, rerun with sudo:",
            file=sys.stderr,
        )
        print("  sudo " + shlex.join(command), file=sys.stderr)
        return result.returncode

    print(f"Sample written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
