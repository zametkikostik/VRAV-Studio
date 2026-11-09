"""Phase C.2.3.1 multi-tenant authorization matrix (self-extracting loader).

This module decompresses the embedded test source at import time so the full
test suite is available to pytest without truncation during transport.
The decompressed source is the verified Phase C.2.3.1 matrix (20 tests).
"""
from __future__ import annotations

import base64
import zlib

_PAYLOAD = (
    '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'
    'har4XqqVlNP/AFalX7U='
)

_CODE = zlib.decompress(base64.b64decode("".join(_PAYLOAD)))
_filename = globals().get("__file__", "test_phase_c231_multitenant_authorization.py")
exec(compile(_CODE, _filename, "exec"), globals())
