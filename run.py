#!/usr/bin/env python3
"""Command-line entry point for netrca.

Examples
--------
    python run.py scenarios                 # list built-in fault scenarios
    python run.py analyze distribution-outage   # print a health + RCA report
    python run.py serve --port 5000         # launch the web dashboard
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from netrca import HealthEngine, RCAEngine, Simulator, Topology
from netrca.health import Status

ROOT = Path(__file__).parent
DEFAULT_TOPOLOGY = ROOT / "data" / "topology.json"

# ANSI colours for the console report
_COLOR = {
    Status.HEALTHY: "\033[32m",
    Status.DEGRADED: "\033[33m",
    Status.CRITICAL: "\033[35m",
    Status.DOWN: "\033[31m",
}
_RESET = "\033[0m"


def _load(topology_path: str) -> Topology:
    return Topology.load(topology_path)


def cmd_scenarios(args: argparse.Namespace) -> int:
    topo = _load(args.topology)
    sim = Simulator(topo)
    from netrca.simulator import SCENARIOS

    print(f"Topology: {topo.name}  ({len(topo)} devices)\n")
    print("Available scenarios:")
    for name in sim.list_scenarios():
        print(f"  {name:<22} {SCENARIOS[name].description}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    topo = _load(args.topology)
    sim = Simulator(topo)
    report = HealthEngine().evaluate(topo, sim.apply(args.scenario))
    result = RCAEngine().analyze(topo, report)

    print(f"\nTopology : {topo.name}")
    print(f"Scenario : {args.scenario}")
    print(f"Health   : {report.overall_score()}/100   "
          f"({len(report.unhealthy())} device(s) alarming)\n")

    print("Device status")
    print("-" * 60)
    for dev in topo:
        h = report[dev.id]
        color = _COLOR[h.status]
        print(f"  {color}{h.status.value.upper():<9}{_RESET} "
              f"{dev.id:<14} {dev.name:<24} score {h.score:>3}")

    print("\nRoot cause analysis")
    print("-" * 60)
    print(result.summary())
    if result.collateral:
        print("\nSuppressed as downstream symptoms:")
        print("  " + ", ".join(sorted(result.collateral)))
    if result.unexplained:
        print("\nUnexplained alarms:")
        print("  " + ", ".join(sorted(result.unexplained)))
    print()
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from netrca.web.app import create_app

    app = create_app(args.topology)
    print(f"Dashboard running at http://{args.host}:{args.port}  (Ctrl+C to stop)")
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="netrca", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topology", default=str(DEFAULT_TOPOLOGY),
                        help="path to a topology JSON file")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("scenarios", help="list built-in fault scenarios")

    p_an = sub.add_parser("analyze", help="run health + RCA and print a report")
    p_an.add_argument("scenario", nargs="?", default="distribution-outage",
                      help="scenario name (see `scenarios`)")

    p_sv = sub.add_parser("serve", help="launch the web dashboard")
    p_sv.add_argument("--host", default="127.0.0.1")
    p_sv.add_argument("--port", type=int, default=5000)
    p_sv.add_argument("--debug", action="store_true")

    args = parser.parse_args(argv)
    return {
        "scenarios": cmd_scenarios,
        "analyze": cmd_analyze,
        "serve": cmd_serve,
    }[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
