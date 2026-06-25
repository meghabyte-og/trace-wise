"""Reproducible fault injection for demos and tests.

A scenario names one or more faults. The simulator applies them to a healthy
baseline and, importantly, *propagates* them: a downed device makes everything
that loses its last path unreachable too — exactly the cascade an operator would
see — so the RCA engine has a realistic mess to untangle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from netrca.telemetry import Telemetry
from netrca.topology import Topology


@dataclass
class Fault:
    device_id: str
    kind: str = "down"      # "down" | "overload"


@dataclass
class Scenario:
    name: str
    description: str
    faults: list[Fault] = field(default_factory=list)


# A library of illustrative incidents. Each is a single, nameable story.
SCENARIOS: dict[str, Scenario] = {
    "healthy": Scenario(
        "healthy", "All devices nominal — no faults injected.", []
    ),
    "access-switch-down": Scenario(
        "access-switch-down",
        "Access Switch A1 fails, isolating the two hosts behind it.",
        [Fault("acc-sw-a1", "down")],
    ),
    "distribution-outage": Scenario(
        "distribution-outage",
        "Distribution Switch B fails — a whole site falls off the network.",
        [Fault("dist-sw-b", "down")],
    ),
    "firewall-failover": Scenario(
        "firewall-failover",
        "Edge Firewall 01 dies, but the redundant pair absorbs the traffic.",
        [Fault("fw-01", "down")],
    ),
    "dual-core-failure": Scenario(
        "dual-core-failure",
        "Both core routers drop — total isolation, attributed to two roots.",
        [Fault("core-rtr-01", "down"), Fault("core-rtr-02", "down")],
    ),
    "db-overload": Scenario(
        "db-overload",
        "Database Server 01 is pegged at high CPU and memory.",
        [Fault("srv-db-01", "overload")],
    ),
    "mixed-incident": Scenario(
        "mixed-incident",
        "A distribution outage and an unrelated overload at the same time.",
        [Fault("dist-sw-b", "down"), Fault("srv-app-01", "overload")],
    ),
}


class Simulator:
    """Applies a :class:`Scenario` to a topology, returning telemetry."""

    def __init__(self, topology: Topology) -> None:
        self.topology = topology

    @staticmethod
    def list_scenarios() -> list[str]:
        return list(SCENARIOS)

    def apply(self, scenario: str | Scenario, seed: int | None = 7) -> Telemetry:
        scn = SCENARIOS[scenario] if isinstance(scenario, str) else scenario
        snap = Telemetry.baseline(self.topology, seed=seed)

        down = {f.device_id for f in scn.faults if f.kind == "down"}
        overloads = [f.device_id for f in scn.faults if f.kind == "overload"]

        # 1. propagate connectivity loss
        collateral = self.topology.impact_of(down)
        for dev_id in down | collateral:
            snap[dev_id].reachable = False

        # 2. apply overloads to devices that are still reachable
        still_up = self.topology.connected_devices(down)
        for dev_id in overloads:
            if dev_id not in still_up:
                continue
            m = snap[dev_id]
            m.cpu_pct = 96.0
            m.mem_pct = 97.0
            m.latency_ms = round(m.latency_ms + 60, 2)
            # congestion bleeds into reachable downstream devices
            for child in self.topology.downstream_of(dev_id):
                if child in still_up and child not in down | collateral:
                    c = snap[child]
                    c.latency_ms = round(c.latency_ms + 45, 2)
                    c.packet_loss_pct = round(c.packet_loss_pct + 2.5, 2)

        return snap
