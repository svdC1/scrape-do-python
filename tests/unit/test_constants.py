import os
import ssl
import pytest
from scrape_do.constants import (
    SCRAPE_DO_CA_PATH,
    DEFAULT_PROXY_SSL_CONTEXT,
)


pytestmark = pytest.mark.unit


class TestBundledCA:

    @staticmethod
    def test_ca_path_resolves_to_an_existing_file():
        """
        Ensures `SCRAPE_DO_CA_PATH` resolves to a real, readable file on
        disk so downstream consumers (the SSL context, third-party tools)
        can load it without a runtime FileNotFoundError.
        """
        assert isinstance(SCRAPE_DO_CA_PATH, str)
        assert os.path.isfile(SCRAPE_DO_CA_PATH)

    @staticmethod
    def test_ca_path_points_to_pem_or_crt_contents():
        """
        Ensures the bundled file looks like a PEM-encoded certificate
        (cheap content sanity check — doesn't validate the cert chain).
        """
        with open(SCRAPE_DO_CA_PATH, "rb") as f:
            head = f.read(64)
        assert b"-----BEGIN CERTIFICATE-----" in head

    @staticmethod
    def test_default_proxy_ssl_context_is_ssl_context():
        """
        Ensures `DEFAULT_PROXY_SSL_CONTEXT` is a usable `ssl.SSLContext`.
        """
        assert isinstance(DEFAULT_PROXY_SSL_CONTEXT, ssl.SSLContext)

    @staticmethod
    def test_default_proxy_ssl_context_verifies_by_default():
        """
        Ensures the default context performs verification — the proxy
        clients rely on this for HTTPS-target validation through
        Scrape.do's MITM step.
        """
        assert DEFAULT_PROXY_SSL_CONTEXT.verify_mode == ssl.CERT_REQUIRED
        assert DEFAULT_PROXY_SSL_CONTEXT.check_hostname is True

    @staticmethod
    def test_default_proxy_ssl_context_loaded_scrape_do_ca():
        """
        Ensures the bundled Scrape.do CA was actually loaded into the
        default context — at least one cert in its CA store should match
        the bundled file's subject.
        """
        ca_certs = DEFAULT_PROXY_SSL_CONTEXT.get_ca_certs()
        assert len(ca_certs) > 0
        # Look for any cert whose subject CN mentions "scrape" — the
        # bundled CA is Scrape.do's, so its subject identifies it.
        # Subject is a tuple of tuples like ((('commonName', '...'),),...)
        joined_subjects = [
            str(cert.get("subject", "")).lower()
            for cert in ca_certs
        ]
        assert any("scrape" in s for s in joined_subjects), (
            "Bundled Scrape.do CA not found in DEFAULT_PROXY_SSL_CONTEXT — "
            "expected at least one CA with 'scrape' in its subject."
            )
