"""Legacy Python compatibility helpers, outside the MoonJMAP v0.1 delivery.

The supported implementation and public contract live in ``src/sync``.  The
re-exports below are kept for older local scripts only; they are not the v0.1
API, are not used by the acceptance oracle, and are not counted in validation.
See ``docs/state-contract.md`` and ``tests/verify.py`` for the current model.
"""

from .sync import (
    AccountScope,
    Added,
    Completeness,
    EmailRecord,
    EmailView,
    Limits,
    QueryKey,
    SyncResult,
    apply_email_get,
    apply_query_changes,
    begin_refresh,
)

__all__ = [
    "AccountScope", "Added", "Completeness", "EmailRecord", "EmailView",
    "Limits", "QueryKey", "SyncResult", "apply_email_get",
    "apply_query_changes", "begin_refresh",
]
