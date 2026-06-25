"""Tests for telemetry scoring and status classification."""

import unittest

from netrca.health import HealthEngine, Status
from netrca.telemetry import DeviceMetrics, Telemetry
from netrca.topology import Device, Topology


def _single() -> Topology:
    t = Topology(name="one", gateway="gw")
    t.add_device(Device("gw", "GW", "gateway", "edge", "X"))
    t.add_device(Device("n1", "Node 1", "switch", "access", "X"))
    t.add_link("gw", "n1")
    return t


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.topo = _single()
        self.engine = HealthEngine()

    def _report_for(self, n1_metrics: DeviceMetrics):
        tel = Telemetry()
        tel.set(DeviceMetrics("gw"))
        tel.set(n1_metrics)
        return self.engine.evaluate(self.topo, tel)

    def test_healthy_baseline(self):
        rep = self._report_for(DeviceMetrics("n1"))
        self.assertEqual(rep["n1"].status, Status.HEALTHY)
        self.assertEqual(rep["n1"].score, 100)
        self.assertEqual(rep.unhealthy(), set())

    def test_unreachable_is_down(self):
        rep = self._report_for(DeviceMetrics("n1", reachable=False))
        self.assertEqual(rep["n1"].status, Status.DOWN)
        self.assertEqual(rep["n1"].score, 0)
        self.assertIn("n1", rep.down())

    def test_degraded_from_latency(self):
        rep = self._report_for(DeviceMetrics("n1", latency_ms=55))
        self.assertEqual(rep["n1"].status, Status.DEGRADED)
        self.assertTrue(any(a.metric == "latency_ms" for a in rep["n1"].alerts))

    def test_critical_from_cpu(self):
        rep = self._report_for(DeviceMetrics("n1", cpu_pct=95))
        self.assertEqual(rep["n1"].status, Status.CRITICAL)

    def test_near_total_loss_counts_as_down(self):
        rep = self._report_for(DeviceMetrics("n1", packet_loss_pct=95))
        self.assertEqual(rep["n1"].status, Status.DOWN)

    def test_overall_score_averages(self):
        rep = self._report_for(DeviceMetrics("n1", reachable=False))
        # gw=100, n1=0  ->  average 50
        self.assertEqual(rep.overall_score(), 50)

    def test_missing_telemetry_treated_as_down(self):
        tel = Telemetry()
        tel.set(DeviceMetrics("gw"))
        rep = self.engine.evaluate(self.topo, tel)  # n1 has no sample
        self.assertEqual(rep["n1"].status, Status.DOWN)


if __name__ == "__main__":
    unittest.main()
