"""
Shared SSRF gate for hosts derived from untrusted operator/IdP-supplied input
(e.g. an OIDC issuer or jwks_uri) that this service is about to fetch.

Same semantics as the per-integration copies in `jira_integration.py:195`
(`_assert_host_not_ssrf`) and `zendesk_integration.py:185`: resolve the host
and reject it if any resolved address is loopback, RFC1918-private, or
link-local. Those two copies are left untouched — see
`docs/planning/oidc-sso/oidc-login-flow/spec.md` ("SSRF helper decision").
Consolidating them onto this helper is a named follow-up, not part of this
change.

Unlike the integration copies, this raises `SsrfError` (a plain `ValueError`)
rather than `HTTPException`, so it can be called from a service layer with
no request/response in scope — the caller maps the error to whatever
response is appropriate (e.g. a generic redirect for the OIDC login flow).

Known limitation (inherited, not closed here): this is a resolve-then-fetch
check. There is a TOCTOU window between this resolution and the DNS
resolution performed by the actual HTTP client for the subsequent request
(e.g. DNS rebinding) — the same gap present in the jira/zendesk copies.
"""
import ipaddress
import socket


class SsrfError(ValueError):
    """Raised when a host resolves to a disallowed (loopback/private/link-local) address,
    or cannot be resolved at all."""


def assert_host_not_ssrf(host: str) -> None:
    """Resolve `host` and raise `SsrfError` if any resolved address is loopback,
    RFC1918-private, or link-local, or if the host cannot be resolved."""
    try:
        infos = socket.getaddrinfo(host, 443)
    except socket.gaierror as exc:
        raise SsrfError(f"Could not resolve host {host!r}: {exc}") from exc

    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if addr.is_loopback or addr.is_private or addr.is_link_local:
            raise SsrfError(f"Host {host!r} resolves to a disallowed address.")
