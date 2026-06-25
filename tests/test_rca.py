"""End-to-end tests for the root cause analysis engine."""

import unittest

from netrca import HealthEngine, RCAEngine, Simulator, Topology


class RCATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topo = Topology.load("data/topology.json")
        cls.sim = Simulator(cls.topo)
        cls.he = HealthEngine()
        cls.rca = RCAEngine()

    def _analyze(self, scenario):
        report = self.he.evaluate(self.topo, self.sim.apply(scenario))
        return self.rca.analyze(self.topo, report)

    def test_healthy_has_no_root_causes(self):
        res = self._analyze("healthy")
        self.assertEqual(res.root_causes, [])
        self.assertEqual(res.total_unhealthy, 0)

    def test_access_switch_is_single_root(self):
        res = self._analyze("access-switch-down")
        roots = [rc.device_id for rc in res.root_causes]
        self.assertEqual(roots, ["acc-sw-a1"])
        rc = res.root_causes[0]
        self.assertEqual(rc.kind, "connectivity")
        self.assertEqual(set(rc.impacted), {"srv-app-01", "srv-web-01"})

    def test_distribution_outage_collapses_cascade(self):
        res = self._analyze("distribution-outage")
        self.assertEqual(len(res.root_causes), 1)
        self.assertEqual(res.root_causes[0].device_id, "dist-sw-b")
        # one root explains six alarms -> meaningful noise reduction
        self.assertEqual(res.total_unhealthy, 6)
        self.assertGreater(res.noise_reduction, 0.8)
        self.assertEqual(res.unexplained, set())

    def test_redundancy_holds_reports_no_impact(self):
        res = self._analyze("firewall-failover")
        self.assertEqual(len(res.root_causes), 1)
        rc = res.root_causes[0]
        self.assertEqual(rc.device_id, "fw-01")
        self.assertEqual(rc.impacted, [])          # nothing isolated
        self.assertIn("redundancy", rc.reason.lower())

    def test_dual_core_yields_two_roots(self):
        res = self._analyze("dual-core-failure")
        roots = {rc.device_id for rc in res.root_causes}
        self.assertEqual(roots, {"core-rtr-01", "core-rtr-02"})
        self.assertEqual(res.unexplained, set())

    def test_overload_is_performance_root(self):
        res = self._analyze("db-overload")
        self.assertEqual(len(res.root_causes), 1)
        rc = res.root_causes[0]
        self.assertEqual(rc.device_id, "srv-db-01")
        self.assertEqual(rc.kind, "performance")

    def test_mixed_incident_separates_concerns(self):
        res = self._analyze("mixed-incident")
        kinds = {rc.device_id: rc.kind for rc in res.root_causes}
        self.assertEqual(kinds.get("dist-sw-b"), "connectivity")
        self.assertEqual(kinds.get("srv-app-01"), "performance")
        self.assertEqual(res.unexplained, set())

    def test_every_alarm_is_explained(self):
        # no scenario should leave dangling, unattributed alarms
        for scenario in self.sim.list_scenarios():
            res = self._analyze(scenario)
            self.assertEqual(
                res.unexplained, set(), msg=f"unexplained alarms in {scenario}"
            )


if __name__ == "__main__":
    unittest.main()
