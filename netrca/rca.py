"""Root cause analysis for network incidents.

When a device fails, every device that depends on it lights up too. An operator
staring at forty red alarms needs to know the *one* thing to fix. This engine
collapses that cascade to its cause.

Method
------
A device that is **down but would still be reachable** through the rest of the
network is failing on its own — a *genuine fault*. A device that is down and is
**cut off no matter what** is *collateral*: something upstream broke its path.

So the algorithm is:

1. Take the set of fully-down devices from the health report.
2. For each down device, test reachability from the gateway while pretending
   only the *other* down devices failed. If the gateway can still reach it, the
   fault is local to that device.
3. Attribute every collateral device to the most-upstream genuine fault on its
   dependency path — that fault is the root cause, the rest are its blast radius.
4. Surface reachable-but-overloaded devices as separate performance root causes.

Redundancy falls out for free: a failed device whose traffic reroutes explains
no collateral and is reported as "down, no service impact".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from netrca.health import HealthReport, Status
from netrca.topology import Topology


@dataclass
class RootCause:
    device_id: str
    kind: str                       # "connectivity" | "performance"
    confidence: float               # 0–1
    reason: str
    impacted: list[str] = field(default_factory=list)  # devices it explains

    @property
    def blast_radius(self) -> int:
        return len(self.impacted)


@dataclass
class RCAResult:
    root_causes: list[RootCause]
    collateral: set[str]            # symptoms explained away as downstream effects
    unexplained: set[str]           # unhealthy devices not tied to any root cause
    total_unhealthy: int

    @property
    def noise_reduction(self) -> float:
        """Fraction of alarms that were collapsed into a smaller set of causes."""
        if self.total_unhealthy == 0:
            return 0.0
        return 1 - (len(self.root_causes) / self.total_unhealthy)

    def summary(self) -> str:
        if not self.root_causes:
            return "No incidents — network is healthy."
        lines = [
            f"{len(self.root_causes)} root cause(s) explain "
            f"{self.total_unhealthy} alarm(s) "
            f"({self.noise_reduction:.0%} noise reduction):"
        ]
        for rc in sorted(self.root_causes, key=lambda r: -r.blast_radius):
            lines.append(
                f"  • {rc.device_id}  [{rc.kind}, {rc.confidence:.0%}]  "
                f"{rc.reason}"
            )
        return "\n".join(lines)


class RCAEngine:
    """Correlates a :class:`HealthReport` against a :class:`Topology`."""

    def analyze(self, topology: Topology, report: HealthReport) -> RCAResult:
        down = report.down()
        unhealthy = report.unhealthy()

        genuine = self._genuine_connectivity_faults(topology, down)
        collateral = down - genuine
        attribution = self._attribute(topology, collateral, genuine)

        root_causes: list[RootCause] = []

        # --- connectivity root causes ----------------------------------
        for fault in genuine:
            explained = sorted(c for c, root in attribution.items() if root == fault)
            dev = topology.devices[fault]
            downstream = topology.downstream_of(fault)
            if explained:
                reason = (
                    f"{dev.name} is down, isolating {len(explained)} "
                    f"downstream device(s)"
                )
                confidence = min(0.98, 0.9 + 0.02 * len(explained))
            elif downstream & down:
                # its dependents are down too, but a concurrent fault took the
                # credit for them — this device is a co-contributor
                reason = (
                    f"{dev.name} is down, contributing to a concurrent outage"
                )
                confidence = 0.8
            elif downstream:
                reason = f"{dev.name} is down, but redundancy held — no service impact"
                confidence = 0.85
            else:
                reason = f"{dev.name} is down (no downstream dependents)"
                confidence = 0.9
            root_causes.append(
                RootCause(
                    device_id=fault,
                    kind="connectivity",
                    confidence=round(confidence, 2),
                    reason=reason,
                    impacted=explained,
                )
            )

        # --- performance root causes -----------------------------------
        reachable_critical = {
            d
            for d in unhealthy
            if d not in down and report[d].status is Status.CRITICAL
        }
        for dev_id in reachable_critical:
            dev = topology.devices[dev_id]
            downstream_degraded = sorted(
                c
                for c in topology.downstream_of(dev_id)
                if c in unhealthy and c not in down
            )
            reason = (
                f"{dev.name} is overloaded "
                f"({self._top_metric(report, dev_id)})"
            )
            if downstream_degraded:
                reason += f", degrading {len(downstream_degraded)} downstream device(s)"
            root_causes.append(
                RootCause(
                    device_id=dev_id,
                    kind="performance",
                    confidence=round(0.7 + 0.05 * min(len(downstream_degraded), 4), 2),
                    reason=reason,
                    impacted=downstream_degraded,
                )
            )

        explained_ids = set(attribution) | {rc.device_id for rc in root_causes}
        for rc in root_causes:
            explained_ids.update(rc.impacted)
        unexplained = unhealthy - explained_ids

        return RCAResult(
            root_causes=root_causes,
            collateral=collateral,
            unexplained=unexplained,
            total_unhealthy=len(unhealthy),
        )

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _genuine_connectivity_faults(
        topology: Topology, down: set[str]
    ) -> set[str]:
        genuine: set[str] = set()
        for d in down:
            # reachability if every *other* down device failed but d did not
            reachable = topology.connected_devices(down - {d})
            if d in reachable:
                genuine.add(d)
        return genuine

    @staticmethod
    def _attribute(
        topology: Topology, collateral: set[str], genuine: set[str]
    ) -> dict[str, str]:
        """Map each collateral device to its most-upstream genuine fault."""
        attribution: dict[str, str] = {}
        for c in collateral:
            fault_ancestors = topology.upstream_of(c) & genuine
            if fault_ancestors:
                # the break closest to the gateway is the true root
                root = min(fault_ancestors, key=topology.hops_from_gateway)
                attribution[c] = root
            else:
                # cut only by a combination of faults — pick the one whose
                # individual removal disconnects c, else the nearest genuine fault
                for f in sorted(genuine, key=topology.hops_from_gateway):
                    if c in topology.impact_of([f]):
                        attribution[c] = f
                        break
        return attribution

    @staticmethod
    def _top_metric(report: HealthReport, device_id: str) -> str:
        alerts = report[device_id].alerts
        if not alerts:
            return "degraded"
        worst = max(alerts, key=lambda a: (a.severity.severity, a.value))
        return worst.message
