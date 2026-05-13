"""Enums."""

import enum
from typing import Any

from typing_extensions import Self


class CrossReferenceType(str, enum.Enum):
    """Cross Reference Type."""

    NONE = "none"
    """No cross reference."""

    SEE = "see"
    """SEE-cross reference."""

    ALSO = "see also"
    """SEE ALSO-cross reference."""

    def __str__(self) -> str:
        return self.value

    @classmethod
    def _missing_(cls, value: Any) -> Self | None:  # noqa: ANN401
        if value is None:
            return cls.NONE
        if isinstance(value, str):
            return cls(value.upper())
        return None
