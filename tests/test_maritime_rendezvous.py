from packages.agents.maritime_agent import haversine_m


def test_haversine_sanity():
    d = haversine_m(34.0, -119.0, 34.001, -119.001)
    assert 0 < d < 300
