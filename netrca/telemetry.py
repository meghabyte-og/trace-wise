"""Per-device telemetry and a synthetic baseline generator.

Real deployments would feed metrics from SNMP, streaming telemetry, or an
observability pipeline. For a self-contained demo we generate a healthy
baseline and let :mod:`netrca.simulator` perturb it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from netrca.topology import Topology


@dataclass
class DeviceMetrics:
    """A single telemetry sample for one device."""

    device_id: str
    reachable: bool = True          # is the device itself responding?
    latency_ms: float = 5.0         # round-trip latency
    packet_loss_pct: float = 0.0    # 0–100
    cpu_pct: float = 20.0           # 0–100
    mem_pct: float = 35.0           # 0–100
    if_errors_per_min: float = 0.0  # interface error rate

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Telemetry:
    """A snapshot of metrics across the whole network."""

    samples: dict[str, DeviceMetrics] = field(default_factory=dict)

    def __getitem__(self, device_id: str) -> DeviceMetrics:
        return self.samples[device_id]

    def __iter__(self):
        return iter(self.samples.values())

    def set(self, metrics: DeviceMetrics) -> None:
        self.samples[metrics.device_id] = metrics

    @classmethod
    def baseline(cls, topology: Topology, seed: int | None = 7) -> "Telemetry":
        """Generate a healthy-looking baseline snapshot for every device.

        Latency grows mildly with distance from the gateway so the numbers feel
        plausible (an access host is a few hops further than a core router).
        """
        rng = np.random.default_rng(seed)
        snap = cls()
        for dev in topology:
            hops = topology.hops_from_gateway(dev.id)
            snap.set(
                DeviceMetrics(
                    device_id=dev.id,
                    reachable=True,
                    latency_ms=round(2.0 + 1.5 * hops + rng.normal(0, 0.4), 2),
                    packet_loss_pct=round(max(0.0, rng.normal(0.05, 0.05)), 3),
                    cpu_pct=round(float(np.clip(rng.normal(22, 6), 3, 70)), 1),
                    mem_pct=round(float(np.clip(rng.normal(38, 8), 10, 80)), 1),
                    if_errors_per_min=round(max(0.0, rng.normal(0.1, 0.2)), 2),
                )
            )
        return snap
