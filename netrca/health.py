"""Turn raw telemetry into per-device health scores, statuses and alerts.

The engine is deliberately threshold-based and explainable: every status change
comes with the metric(s) that triggered it, which is what an operator needs when
triaging an incident.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from netrca.telemetry import DeviceMetrics, Telemetry
from netrca.topology import Topology


class Status(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    DOWN = "down"

    @property
    def severity(self) -> int:
        return {"healthy": 0, "degraded": 1, "critical": 2, "down": 3}[self.value]


# (metric, warn threshold, critical threshold, human label)
_THRESHOLDS = [
    ("packet_loss_pct", 1.0, 10.0, "packet loss"),
    ("latency_ms", 40.0, 120.0, "latency"),
    ("cpu_pct", 80.0, 93.0, "CPU"),
    ("mem_pct", 85.0, 95.0, "memory"),
    ("if_errors_per_min", 10.0, 50.0, "interface errors"),
]

_UNIT = {
    "packet_loss_pct": "%",
    "latency_ms": " ms",
    "cpu_pct": "%",
    "mem_pct": "%",
    "if_errors_per_min": "/min",
}


@dataclass
class Alert:
    """A single threshold breach on a device."""

    device_id: str
    metric: str
    value: float
    severity: Status
    message: str


@dataclass
class DeviceHealth:
    device_id: str
    status: Status
    score: int                      # 0–100, higher is healthier
    reachable: bool
    alerts: list[Alert] = field(default_factory=list)


@dataclass
class HealthReport:
    """Health across the whole network for one telemetry snapshot."""

    devices: dict[str, DeviceHealth] = field(default_factory=dict)

    def __getitem__(self, device_id: str) -> DeviceHealth:
        return self.devices[device_id]

    @property
    def alerts(self) -> list[Alert]:
        out: list[Alert] = []
        for dh in self.devices.values():
            out.extend(dh.alerts)
        return out

    def unhealthy(self) -> set[str]:
        """Devices worse than HEALTHY."""
        return {d for d, h in self.devices.items() if h.status is not Status.HEALTHY}

    def down(self) -> set[str]:
        """Devices that are fully DOWN (unreachable)."""
        return {d for d, h in self.devices.items() if h.status is Status.DOWN}

    def overall_score(self) -> int:
        if not self.devices:
            return 100
        return round(sum(h.score for h in self.devices.values()) / len(self.devices))


class HealthEngine:
    """Scores telemetry against thresholds to produce a :class:`HealthReport`."""

    def evaluate(self, topology: Topology, telemetry: Telemetry) -> HealthReport:
        report = HealthReport()
        for dev in topology:
            metrics = telemetry.samples.get(dev.id)
            if metrics is None:
                # no data == we cannot see it == treat as down
                metrics = DeviceMetrics(device_id=dev.id, reachable=False)
            report.devices[dev.id] = self._score_device(metrics)
        return report

    # ------------------------------------------------------------------ score
    def _score_device(self, m: DeviceMetrics) -> DeviceHealth:
        if not m.reachable:
            return DeviceHealth(
                device_id=m.device_id,
                status=Status.DOWN,
                score=0,
                reachable=False,
                alerts=[
                    Alert(
                        device_id=m.device_id,
                        metric="reachable",
                        value=0.0,
                        severity=Status.DOWN,
                        message="device is not responding",
                    )
                ],
            )

        score = 100
        worst = Status.HEALTHY
        alerts: list[Alert] = []

        for metric, warn, crit, label in _THRESHOLDS:
            value = float(getattr(m, metric))
            if value >= crit:
                severity = Status.CRITICAL
                score -= 35
            elif value >= warn:
                severity = Status.DEGRADED
                score -= 15
            else:
                continue

            if severity.severity > worst.severity:
                worst = severity
            alerts.append(
                Alert(
                    device_id=m.device_id,
                    metric=metric,
                    value=value,
                    severity=severity,
                    message=f"{label} {value:g}{_UNIT[metric]} "
                    f"(threshold {crit if severity is Status.CRITICAL else warn:g})",
                )
            )

        # near-total loss with the device still "reachable" is effectively down
        if m.packet_loss_pct >= 90:
            worst = Status.DOWN
            score = 0

        return DeviceHealth(
            device_id=m.device_id,
            status=worst,
            score=max(0, min(100, score)),
            reachable=True,
            alerts=alerts,
        )
