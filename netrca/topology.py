"""Network topology as a directed dependency graph.

Edges point *downstream*: ``from`` provides connectivity to ``to``. A device is
considered connected when at least one path of healthy devices links it back to
the gateway, so redundant uplinks are honoured automatically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import networkx as nx


@dataclass(frozen=True)
class Device:
    """A node in the network."""

    id: str
    name: str
    type: str
    tier: str
    site: str


class Topology:
    """A directed dependency graph of network devices.

    The graph is built so that ``gateway`` is the single source every device
    must be able to reach to be considered "connected".
    """

    #: rough order of tiers from the edge inward, used for layout and ranking
    TIER_ORDER = ["edge", "core", "security", "distribution", "access", "host"]

    def __init__(self, name: str, gateway: str) -> None:
        self.name = name
        self.gateway = gateway
        self.graph = nx.DiGraph()
        self.devices: dict[str, Device] = {}

    # ------------------------------------------------------------------ build
    def add_device(self, device: Device) -> None:
        self.devices[device.id] = device
        self.graph.add_node(device.id)

    def add_link(self, upstream: str, downstream: str) -> None:
        if upstream not in self.devices or downstream not in self.devices:
            raise KeyError(
                f"link references unknown device: {upstream} -> {downstream}"
            )
        self.graph.add_edge(upstream, downstream)

    @classmethod
    def from_dict(cls, data: dict) -> "Topology":
        topo = cls(name=data["name"], gateway=data["gateway"])
        for d in data["devices"]:
            topo.add_device(
                Device(
                    id=d["id"],
                    name=d["name"],
                    type=d["type"],
                    tier=d["tier"],
                    site=d.get("site", "—"),
                )
            )
        for link in data["links"]:
            topo.add_link(link["from"], link["to"])
        if topo.gateway not in topo.devices:
            raise ValueError(f"gateway {topo.gateway!r} is not a declared device")
        return topo

    @classmethod
    def load(cls, path: str | Path) -> "Topology":
        return cls.from_dict(json.loads(Path(path).read_text()))

    # -------------------------------------------------------------- queries
    def __len__(self) -> int:
        return len(self.devices)

    def __contains__(self, device_id: str) -> bool:
        return device_id in self.devices

    def __iter__(self) -> Iterable[Device]:
        return iter(self.devices.values())

    def upstream_of(self, device_id: str) -> set[str]:
        """All devices ``device_id`` transitively depends on (its ancestors)."""
        return nx.ancestors(self.graph, device_id)

    def downstream_of(self, device_id: str) -> set[str]:
        """All devices that transitively depend on ``device_id``."""
        return nx.descendants(self.graph, device_id)

    def hops_from_gateway(self, device_id: str) -> int:
        """Shortest dependency distance from the gateway (gateway == 0)."""
        try:
            return nx.shortest_path_length(self.graph, self.gateway, device_id)
        except nx.NetworkXNoPath:
            return len(self.graph)  # effectively "unreachable / far"

    # --------------------------------------------------------- reachability
    def connected_devices(self, down: Iterable[str] = ()) -> set[str]:
        """Devices still reachable from the gateway when ``down`` are removed.

        ``down`` are devices treated as failed (and therefore not traversable).
        A device in ``down`` is never connected. The gateway itself is connected
        unless it is in ``down``.
        """
        down = set(down)
        if self.gateway in down:
            return set()
        survivors = self.graph.subgraph(
            [n for n in self.graph.nodes if n not in down]
        )
        return set(nx.descendants(survivors, self.gateway)) | {self.gateway}

    def impact_of(self, down: Iterable[str]) -> set[str]:
        """Devices that lose connectivity when ``down`` fail.

        This is the set of devices reachable in the healthy network but no longer
        reachable once ``down`` are removed — i.e. the collateral of the failure,
        excluding the failed devices themselves.
        """
        down = set(down)
        healthy = self.connected_devices()
        degraded = self.connected_devices(down)
        return (healthy - degraded) - down

    def to_layout(self) -> dict[str, tuple[float, float]]:
        """A stable left-to-right layered layout keyed by tier order.

        Returns normalised coordinates in the unit square, suitable for SVG.
        """
        tiers: dict[str, list[str]] = {}
        for dev in self.devices.values():
            tiers.setdefault(dev.tier, []).append(dev.id)

        ordered_tiers = [t for t in self.TIER_ORDER if t in tiers]
        # any unexpected tiers go at the end, alphabetically
        ordered_tiers += sorted(t for t in tiers if t not in self.TIER_ORDER)

        pos: dict[str, tuple[float, float]] = {}
        n_cols = max(len(ordered_tiers) - 1, 1)
        for col, tier in enumerate(ordered_tiers):
            members = sorted(tiers[tier])
            n_rows = max(len(members) - 1, 1)
            for row, dev_id in enumerate(members):
                x = col / n_cols
                y = row / n_rows if len(members) > 1 else 0.5
                pos[dev_id] = (x, y)
        return pos
