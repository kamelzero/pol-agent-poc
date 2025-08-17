from common.geo import latlon_to_h3


def test_h3_res8_stable():
    h = latlon_to_h3(34.0, -119.0, 8)
    assert isinstance(h, str) and len(h) > 5
