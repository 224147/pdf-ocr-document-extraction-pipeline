"""Runtime environment setup performed before any model is downloaded.

Docling and EasyOCR fetch their weights over HTTPS on first use, and both steps
are fragile in locked-down environments. These helpers make that step reliable.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def enable_system_trust() -> bool:
    """Route Python's TLS verification through the OS trust store.

    macOS framework Python ships without a usable CA bundle, so model downloads
    fail with CERTIFICATE_VERIFY_FAILED unless the system store is used.
    """
    try:
        import truststore

        truststore.inject_into_ssl()
        return True
    except Exception as error:
        logger.debug("System trust store unavailable: %s", error)
        return False


def configure_model_downloads() -> None:
    """Prefer the plain HuggingFace CDN over the Xet transfer backend.

    The Xet client aborts the interpreter during shutdown on some platforms and
    its CAS endpoints are commonly blocked by corporate proxies.
    """
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")


def bootstrap() -> None:
    configure_model_downloads()
    enable_system_trust()
