"""Flask dashboard for live network health and root cause analysis."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, render_template, request

from netrca import HealthEngine, RCAEngine, Simulator, Topology
from netrca.simulator import SCENARIOS

# SVG canvas geometry (the template draws into this box)
_CANVAS_W, _CANVAS_H = 1000, 520
_PAD_X, _PAD_Y = 90, 70


def _node_positions(topology: Topology) -> dict[str, tuple[float, float]]:
    layout = topology.to_layout()
    placed: dict[str, tuple[float, float]] = {}
    for dev_id, (nx_, ny_) in layout.items():
        x = _PAD_X + nx_ * (_CANVAS_W - 2 * _PAD_X)
        y = _PAD_Y + ny_ * (_CANVAS_H - 2 * _PAD_Y)
        placed[dev_id] = (round(x, 1), round(y, 1))
    return placed


def _build_view(topology: Topology, scenario: str) -> dict:
    sim = Simulator(topology)
    telemetry = sim.apply(scenario)
    report = HealthEngine().evaluate(topology, telemetry)
    result = RCAEngine().analyze(topology, report)

    root_ids = {rc.device_id for rc in result.root_causes}
    pos = _node_positions(topology)

    nodes = []
    for dev in topology:
        h = report[dev.id]
        x, y = pos[dev.id]
        nodes.append({
            "id": dev.id,
            "name": dev.name,
            "tier": dev.tier,
            "type": dev.type,
            "site": dev.site,
            "x": x,
            "y": y,
            "status": h.status.value,
            "score": h.score,
            "is_root": dev.id in root_ids,
            "is_collateral": dev.id in result.collateral,
        })

    edges = []
    for upstream, downstream in topology.graph.edges:
        x1, y1 = pos[upstream]
        x2, y2 = pos[downstream]
        broken = (
            report[upstream].status.value == "down"
            or report[downstream].status.value == "down"
        )
        edges.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "broken": broken})

    # device rows sorted worst-first
    severity = {"down": 0, "critical": 1, "degraded": 2, "healthy": 3}
    rows = sorted(
        (
            {
                "id": dev.id,
                "name": dev.name,
                "tier": dev.tier,
                "site": dev.site,
                "status": report[dev.id].status.value,
                "score": report[dev.id].score,
                "role": (
                    "root cause" if dev.id in root_ids
                    else "symptom" if dev.id in result.collateral
                    else ""
                ),
            }
            for dev in topology
        ),
        key=lambda r: (severity[r["status"]], r["name"]),
    )

    return {
        "topology": topology,
        "scenarios": [(n, SCENARIOS[n].description) for n in sim.list_scenarios()],
        "scenario": scenario,
        "scenario_desc": SCENARIOS[scenario].description,
        "report": report,
        "result": result,
        "overall": report.overall_score(),
        "alarm_count": len(report.unhealthy()),
        "nodes": nodes,
        "edges": edges,
        "rows": rows,
        "canvas_w": _CANVAS_W,
        "canvas_h": _CANVAS_H,
    }


def create_app(topology_path: str | Path) -> Flask:
    topology = Topology.load(topology_path)
    app = Flask(__name__)

    @app.route("/")
    def dashboard():
        scenario = request.args.get("scenario", "distribution-outage")
        if scenario not in SCENARIOS:
            scenario = "distribution-outage"
        return render_template("dashboard.html", **_build_view(topology, scenario))

    return app
