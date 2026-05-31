"""Pagination primitives shared by list endpoints (used from V1 onward)."""
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@dataclass
class PageParams:
    limit: int = DEFAULT_LIMIT
    offset: int = 0

    def normalized(self) -> "PageParams":
        return PageParams(
            limit=max(1, min(self.limit, MAX_LIMIT)),
            offset=max(0, self.offset),
        )


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
