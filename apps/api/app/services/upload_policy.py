"""Upload policy constants (shared by API and tests)."""
ALLOWED_ASSET_TYPES = frozenset({"image", "video", "audio", "model", "other"})
ALLOWED_MIME_PREFIXES = ("image/", "video/", "audio/", "application/octet-stream")
