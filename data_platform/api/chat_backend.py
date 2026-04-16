"""Compatibility shim — preserves the uvicorn entry point.

The entire implementation has been moved to the ``data_platform.chat_backend``
package.  This file re-exports ``app`` so that existing startup scripts
(``uvicorn data_platform.api.chat_backend:app``) continue to work unchanged.
"""
from data_platform.chat_backend.app import app  # noqa: F401
