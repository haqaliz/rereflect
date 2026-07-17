"""
Unit tests for the shared SSRF gate (`src/utils/ssrf.py`).

`socket.getaddrinfo` is mocked in every test to avoid real DNS lookups; we
assert purely on how resolved-IP classes (public/loopback/private/
link-local) and resolution failures are handled.
"""
import socket
from unittest.mock import patch

import pytest

from src.utils.ssrf import SsrfError, assert_host_not_ssrf


def _fake_getaddrinfo(ip: str):
    """Build a `socket.getaddrinfo`-shaped return value for a single resolved IPv4 address."""
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    sockaddr = (ip, 443, 0, 0) if family == socket.AF_INET6 else (ip, 443)
    return [(family, socket.SOCK_STREAM, 6, "", sockaddr)]


def test_public_host_passes():
    with patch("socket.getaddrinfo", return_value=_fake_getaddrinfo("93.184.216.34")):
        assert_host_not_ssrf("example.com")  # does not raise


def test_loopback_rejected():
    with patch("socket.getaddrinfo", return_value=_fake_getaddrinfo("127.0.0.1")):
        with pytest.raises(SsrfError):
            assert_host_not_ssrf("localhost")


def test_private_10_range_rejected():
    with patch("socket.getaddrinfo", return_value=_fake_getaddrinfo("10.0.0.5")):
        with pytest.raises(SsrfError):
            assert_host_not_ssrf("internal.corp")


def test_private_192_168_range_rejected():
    with patch("socket.getaddrinfo", return_value=_fake_getaddrinfo("192.168.1.10")):
        with pytest.raises(SsrfError):
            assert_host_not_ssrf("router.local")


def test_link_local_metadata_endpoint_rejected():
    with patch("socket.getaddrinfo", return_value=_fake_getaddrinfo("169.254.169.254")):
        with pytest.raises(SsrfError):
            assert_host_not_ssrf("metadata.internal")


def test_unresolvable_host_rejected():
    with patch("socket.getaddrinfo", side_effect=socket.gaierror("Name or service not known")):
        with pytest.raises(SsrfError):
            assert_host_not_ssrf("does-not-resolve.invalid")


def test_multiple_resolved_addresses_any_bad_one_rejects():
    """If a host resolves to both a public and a private address, reject it —
    an attacker only needs one malicious record to win a DNS race."""
    infos = _fake_getaddrinfo("93.184.216.34") + _fake_getaddrinfo("10.0.0.1")
    with patch("socket.getaddrinfo", return_value=infos):
        with pytest.raises(SsrfError):
            assert_host_not_ssrf("mixed.example.com")
