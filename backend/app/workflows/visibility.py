"""Chat and shared-research visibility policy.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import uuid


class ChatVisibilityPolicy:
    """Decide whether a user may see a private, direct, group, or public item."""

    @staticmethod
    def can_read(
        visibility: str,
        user_id: uuid.UUID,
        owner_id: uuid.UUID,
        recipient_id: uuid.UUID | None = None,
        member_ids: set[uuid.UUID] | None = None,
    ) -> bool:
        """Return access according to explicit recipients and group membership."""
        if user_id == owner_id or visibility == "public":
            return True
        if visibility == "direct":
            return user_id == recipient_id
        if visibility == "group":
            return user_id in (member_ids or set())
        return False
