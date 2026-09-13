from dataclasses import dataclass


# Priority rank: lower number = higher priority in retrieval.
CATEGORIES = {
    "identity": 1,
    "instruction": 2,
    "project": 3,
    "preference": 4,
    "technology": 5,
    "goal": 6,
    "habit": 7,
    "favorite": 8,
    "other": 9,
    "explicit": 10,
    "fact": 10,
}


@dataclass
class Memory:
    id: int
    content: str
    category: str
    source: str
    confidence: float
    created_at: str
    updated_at: str
    active: bool = True
    pinned: bool = False

    @classmethod
    def from_row(cls, row):
        return cls(
            id=row["id"],
            content=row["content"],
            category=row["category"],
            source=row["source"],
            confidence=row["confidence"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            active=bool(row["active"]),
            pinned=bool(row["pinned"]),
        )

    @property
    def priority(self):
        """Lower number = higher priority for retrieval."""
        return CATEGORIES.get(self.category, 10)