"""linkgate.vt birim testleri — ağ çağrısı yapmaz, saf mantık + parsing."""
from linkgate.vt import VTResult, _url_id, check_url


def test_url_id_is_base64url_without_padding():
    # VT v3 örneği: http://www.virustotal.com için bilinen kimlik biçimi
    uid = _url_id("https://example.com")
    assert "=" not in uid
    assert "/" not in uid and "+" not in uid  # urlsafe alfabe


def test_vtresult_safe_logic():
    safe = VTResult(harmless=70, malicious=0, suspicious=0, checked=True)
    assert safe.is_safe is True
    bad = VTResult(harmless=60, malicious=3, checked=True)
    assert bad.is_safe is False
    unchecked = VTResult(checked=False)
    assert unchecked.is_safe is False


def test_vtresult_summary_strings():
    assert "GÜVENLİ" in VTResult(checked=True, harmless=10).summary()
    assert "RİSKLİ" in VTResult(checked=True, malicious=2).summary()
    assert "kontrol edilmedi" in VTResult(checked=False).summary()


def test_check_url_without_key_skips(monkeypatch):
    monkeypatch.delenv("VT_API_KEY", raising=False)
    res = check_url("https://example.com", api_key=None)
    assert res.checked is False
    assert res.error is not None
