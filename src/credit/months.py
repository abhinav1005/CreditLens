"""Tiny helpers for "YYYY-MM" month strings."""


def to_index(month: str) -> int:
    """Months since year 0, so differences between months are plain subtraction."""
    year, mon = month.split("-")
    return int(year) * 12 + int(mon) - 1


def from_index(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def months_between(earlier: str, later: str) -> int:
    return to_index(later) - to_index(earlier)


def month_range(last: str, count: int) -> list[str]:
    """The `count` months ending at `last`, oldest first."""
    end = to_index(last)
    return [from_index(i) for i in range(end - count + 1, end + 1)]
