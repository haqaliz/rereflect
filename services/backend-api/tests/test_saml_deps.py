"""
Dependency smoke test for the SAML 2.0 SSO feature (saml-sso, slice 1 / deps-and-docker).

This is the RED->GREEN anchor for the whole feature: python3-saml pulls the native `xmlsec`
(libxmlsec1/libxml2) binding, which needs OS packages in the backend image + CI. If those are
missing, EVERY later SAML module fails to import and the suite dies at collection. This test
proves the imports work — before any SAML logic exists.

Fails before `python3-saml`/`xmlsec` are installed (requirements.txt) and the native libs are
present (Dockerfile). Passes after. Keep it dependency-only: no network, no config, no XML parsing.
"""


def test_onelogin_saml_auth_imports():
    # The exact entrypoint every SAML provider/route in later aspects will use.
    from onelogin.saml2.auth import OneLogin_Saml2_Auth  # noqa: F401
    from onelogin.saml2.settings import OneLogin_Saml2_Settings  # noqa: F401


def test_xmlsec_native_binding_imports():
    # The native binding that requires libxmlsec1/libxml2 system packages.
    import xmlsec

    # Touch the C extension so a broken/ABI-mismatched build fails loudly here,
    # not deep inside signature validation in a later aspect.
    assert xmlsec.__version__  # e.g. "1.3.13"


def test_lxml_backend_imports():
    from lxml import etree  # noqa: F401
