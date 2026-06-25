"""netrca — Network Health monitoring & Root Cause Analysis.

A small, dependency-light toolkit that:

  * models a network as a directed dependency graph (``topology``),
  * scores per-device health from telemetry and raises alerts (``health``),
  * separates the genuine fault from its downstream cascade (``rca``),
  * injects reproducible failure scenarios for demos and tests (``simulator``).

The public surface is intentionally small::

    from netrca import Topology, HealthEngine, RCAEngine, Simulator
"""

from netrca.topology import Topology, Device
from netrca.telemetry import Telemetry, DeviceMetrics
from netrca.health import HealthEngine, HealthReport, Alert, Status
from netrca.rca import RCAEngine, RCAResult, RootCause
from netrca.simulator import Simulator, Scenario

__all__ = [
    "Topology",
    "Device",
    "Telemetry",
    "DeviceMetrics",
    "HealthEngine",
    "HealthReport",
    "Alert",
    "Status",
    "RCAEngine",
    "RCAResult",
    "RootCause",
    "Simulator",
    "Scenario",
]

__version__ = "1.0.0"
