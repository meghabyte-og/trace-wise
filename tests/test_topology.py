"""Tests for the topology model and its reachability maths."""

import unittest

from netrca.topology import Device, Topology


def _diamond() -> Topology:
    """gw -> a, gw -> b ; a -> c, b -> c ; c -> d  (c & d behind a redundant pair)."""
    t = Topology(name="diamond", gateway="gw")
    for nid in ["gw", "a", "b", "c", "d"]:
        t.add_device(Device(nid, nid.upper(), "node", "core", "X"))
    t.add_link("gw", "a")
    t.add_link("gw", "b")
    t.add_link("a", "c")
    t.add_link("b", "c")
    t.add_link("c", "d")
    return t


class TopologyTests(unittest.TestCase):
    def setUp(self):
        self.t = _diamond()

    def test_loads_sample_topology(self):
        topo = Topology.load("data/topology.json")
        self.assertGreater(len(topo), 10)
        self.assertIn("core-rtr-01", topo)
        self.assertEqual(topo.gateway, "internet-gw")

    def test_upstream_and_downstream(self):
        self.assertEqual(self.t.downstream_of("a"), {"c", "d"})
        self.assertEqual(self.t.upstream_of("d"), {"gw", "a", "b", "c"})

    def test_hops_from_gateway(self):
        self.assertEqual(self.t.hops_from_gateway("gw"), 0)
        self.assertEqual(self.t.hops_from_gateway("a"), 1)
        self.assertEqual(self.t.hops_from_gateway("c"), 2)

    def test_redundancy_no_impact(self):
        # killing one of the redundant pair leaves everything reachable
        self.assertEqual(self.t.impact_of(["a"]), set())
        self.assertIn("d", self.t.connected_devices(["a"]))

    def test_both_redundant_paths_down_isolates(self):
        impact = self.t.impact_of(["a", "b"])
        self.assertEqual(impact, {"c", "d"})

    def test_single_point_of_failure(self):
        # c is a choke point: its loss takes d with it
        self.assertEqual(self.t.impact_of(["c"]), {"d"})

    def test_gateway_down_disconnects_all(self):
        self.assertEqual(self.t.connected_devices(["gw"]), set())

    def test_unknown_link_raises(self):
        with self.assertRaises(KeyError):
            self.t.add_link("gw", "ghost")


if __name__ == "__main__":
    unittest.main()
