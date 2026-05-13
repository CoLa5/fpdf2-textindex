"""Link Location."""

import dataclasses


@dataclasses.dataclass(kw_only=True, slots=True)
class LinkLocation:
    """Link Location."""

    page: int
    """The page the link is referened/used on."""

    x: float
    """The `x`-position on the page."""

    y: float
    """The `y`-position on the page."""

    w: float
    """The width the link has on the page."""

    h: float
    """The height the link has on the page."""
