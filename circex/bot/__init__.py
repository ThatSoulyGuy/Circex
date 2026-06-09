"""SkyPortal poster bot — maps CircularExtraction to SkyPortal API writes.

See docs/design_skyportal_bot.md. The mapping (skyportal_map) is pure and
offline-testable; the poster (poster) defaults to dry-run and only hits a live
SkyPortal with an explicit token + flag.
"""

from circex.bot.skyportal_map import (
    PhotometryPoint,
    SkyPortalActions,
    SourceUpsert,
    to_actions,
)

__all__ = [
    "PhotometryPoint",
    "SkyPortalActions",
    "SourceUpsert",
    "to_actions",
]
