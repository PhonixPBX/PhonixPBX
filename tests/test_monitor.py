from phonix.services.monitor import Banner, remote_ip


def test_remote_ip():
    assert remote_ip("IPV4/UDP/203.0.113.5/5060") == "203.0.113.5"
    assert remote_ip("IPV4/UDP/127.0.0.1/5060") is None
    assert remote_ip("garbage") is None


def test_banner_threshold_and_whitelist():
    b = Banner(threshold=3, seconds=60, whitelist=["192.168.1.0/24"])
    assert not b.record("203.0.113.5", now=1)
    assert not b.record("203.0.113.5", now=2)
    assert b.record("203.0.113.5", now=3)
    assert not b.record("203.0.113.5", now=4)  # already banned
    assert not any(b.record("192.168.1.20", now=t) for t in range(10))
    # failures outside the window do not count
    b2 = Banner(threshold=2, seconds=60, whitelist=[])
    assert not b2.record("198.51.100.1", now=0)
    assert not b2.record("198.51.100.1", now=10_000)
