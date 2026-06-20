"""linkgate.extract birim testleri — tarayıcı gerektirmez, hızlı koşar."""
from linkgate.extract import (
    base_domain,
    find_url_in_json,
    is_real_target,
    parse_proxy,
)


def test_base_domain():
    assert base_domain("sub.aylink.co") == "aylink.co"
    assert base_domain("aylink.co") == "aylink.co"
    assert base_domain("localhost") == "localhost"


def test_is_real_target_rejects_gate():
    assert is_real_target("https://example.com/file", "aylink.co") is True
    assert is_real_target("https://aylink.co/x", "aylink.co") is False
    assert is_real_target("https://go.aylink.co/x", "aylink.co") is False


def test_is_real_target_rejects_trackers():
    assert is_real_target("https://www.google.com/recaptcha", "aylink.co") is False
    assert is_real_target("https://ppcnt.eu/go.php", "aylink.co") is False
    assert is_real_target("https://challenges.cloudflare.com/x", "aylink.co") is False


def test_is_real_target_handles_garbage():
    assert is_real_target("not-a-url", "aylink.co") is False
    assert is_real_target("", "aylink.co") is False


def test_find_url_prefers_known_keys():
    assert find_url_in_json({"url": "https://target.com/a"}) == "https://target.com/a"
    assert find_url_in_json({"link": "https://t.com/b"}) == "https://t.com/b"


def test_find_url_nested():
    data = {"status": True, "data": {"go": "https://deep.com/x"}}
    assert find_url_in_json(data) == "https://deep.com/x"


def test_find_url_in_list():
    assert find_url_in_json([{"a": 1}, {"url": "https://l.com/y"}]) == "https://l.com/y"


def test_find_url_none_when_absent():
    assert find_url_in_json({"status": False, "n": 3}) is None
    assert find_url_in_json("plain text") is None


def test_parse_proxy_full():
    p = parse_proxy("http://user:pass@host.com:8080")
    assert p == {"server": "http://host.com:8080", "username": "user", "password": "pass"}


def test_parse_proxy_no_auth():
    assert parse_proxy("http://host.com:3128") == {"server": "http://host.com:3128"}


def test_parse_proxy_empty():
    assert parse_proxy(None) is None
    assert parse_proxy("") is None
