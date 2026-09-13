import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import CATEGORIES, Memory


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    def __init__(self, path=None):
        if path is None:
            data_dir = Path(
                os.environ.get("FRIDAY_DATA_DIR", Path.home() / ".friday")
            )
            data_dir.mkdir(parents=True, exist_ok=True)
            path = data_dir / "memory.db"

        self.path = str(path)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'fact',
                    source TEXT NOT NULL DEFAULT 'automatic',
                    confidence REAL NOT NULL DEFAULT 0.5,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    pinned INTEGER NOT NULL DEFAULT 0
                )
            """)

            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_active
                ON memories(active)
            """)

            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_category
                ON memories(category)
            """)

            db.commit()

    # ------------------------------------------------------------ add

    def add(
        self,
        content,
        category="fact",
        source="automatic",
        confidence=0.5,
        pinned=False,
    ):
        now = _utc_now()

        with self._connect() as db:
            cursor = db.execute("""
                INSERT INTO memories
                (
                    content,
                    category,
                    source,
                    confidence,
                    created_at,
                    updated_at,
                    active,
                    pinned
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """, (
                content.strip(),
                category,
                source,
                float(confidence),
                now,
                now,
                int(pinned),
            ))

            db.commit()
            return cursor.lastrowid

    # --------------------------------------------------------- update

    def update(self, memory_id, content=None, category=None,
               confidence=None):
        """Update an existing memory's fields and bump updated_at."""
        sets = []
        params = []

        if content is not None:
            sets.append("content = ?")
            params.append(content.strip())

        if category is not None:
            sets.append("category = ?")
            params.append(category)

        if confidence is not None:
            sets.append("confidence = ?")
            params.append(float(confidence))

        if not sets:
            return False

        sets.append("updated_at = ?")
        params.append(_utc_now())
        params.append(memory_id)

        with self._connect() as db:
            cursor = db.execute(
                f"UPDATE memories SET {', '.join(sets)} "
                "WHERE id = ? AND active = 1",
                params,
            )
            db.commit()
            return cursor.rowcount > 0

    # ------------------------------------------------------------ all

    def all(self):
        with self._connect() as db:
            rows = db.execute("""
                SELECT *
                FROM memories
                WHERE active = 1
                ORDER BY pinned DESC, updated_at DESC
            """).fetchall()

        return [Memory.from_row(row) for row in rows]

    # --------------------------------------------------- find_similar

    def find_similar(self, content, threshold=0.35):
        """
        Find active memories whose keywords overlap with *content*.

        Returns a list of (score, Memory) tuples sorted by score
        descending, where score is the fraction of query keywords
        found in the memory content.
        """
        keywords = _extract_keywords(content)

        if not keywords:
            return []

        memories = self.all()
        scored = []

        for memory in memories:
            mem_lower = memory.content.lower()
            hits = sum(1 for kw in keywords if kw in mem_lower)
            score = hits / len(keywords)

            if score >= threshold:
                scored.append((score, memory))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    # --------------------------------------------------------- search

    def search(self, terms, limit=8):
        memories = self.all()

        if not terms:
            return memories[:limit]

        terms = [
            term.lower()
            for term in terms
            if term and len(term) > 2
        ]

        if not terms:
            return memories[:limit]

        scored = []

        for memory in memories:
            content = memory.content.lower()
            score = sum(
                1 for term in terms
                if term in content
            )

            if score:
                # Boost pinned and high-priority categories.
                priority_boost = (
                    (10 - CATEGORIES.get(memory.category, 10))
                    * 0.1
                )

                pinned_boost = 2.0 if memory.pinned else 0.0

                total = score + priority_boost + pinned_boost
                scored.append((total, memory))

        scored.sort(
            key=lambda item: (
                item[0],
                item[1].confidence,
                item[1].updated_at,
            ),
            reverse=True,
        )

        return [
            memory
            for _, memory in scored[:limit]
        ]

    # --------------------------------------------------------- delete

    def delete(self, memory_id):
        with self._connect() as db:
            cursor = db.execute("""
                UPDATE memories
                SET active = 0, updated_at = ?
                WHERE id = ?
            """, (
                _utc_now(),
                memory_id,
            ))

            db.commit()
            return cursor.rowcount > 0

    def delete_matching(self, text):
        with self._connect() as db:
            cursor = db.execute("""
                UPDATE memories
                SET active = 0, updated_at = ?
                WHERE active = 1
                  AND lower(content) LIKE ?
            """, (
                _utc_now(),
                f"%{text.lower()}%",
            ))

            db.commit()
            return cursor.rowcount

    # ---------------------------------------------------------- clear

    def clear(self):
        with self._connect() as db:
            db.execute("""
                UPDATE memories
                SET active = 0, updated_at = ?
                WHERE active = 1
                  AND pinned = 0
            """, (_utc_now(),))

            db.commit()

    # ------------------------------------------------- export / import

    def export(self):
        return [
            {
                "id": memory.id,
                "content": memory.content,
                "category": memory.category,
                "source": memory.source,
                "confidence": memory.confidence,
                "created_at": memory.created_at,
                "updated_at": memory.updated_at,
                "active": memory.active,
                "pinned": memory.pinned,
            }
            for memory in self.all()
        ]

    def replace_from_export(self, memories):
        with self._connect() as db:
            db.execute("DELETE FROM memories")

            for memory in memories:
                db.execute("""
                    INSERT INTO memories
                    (
                        id,
                        content,
                        category,
                        source,
                        confidence,
                        created_at,
                        updated_at,
                        active,
                        pinned
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    memory["id"],
                    memory["content"],
                    memory["category"],
                    memory["source"],
                    memory["confidence"],
                    memory["created_at"],
                    memory["updated_at"],
                    int(memory.get("active", True)),
                    int(memory.get("pinned", False)),
                ))

            db.commit()


# ------------------------------------------------------------ helpers

# Stop words for keyword extraction (English + Telugu romanised + Hindi).
_STOP_WORDS = {
    # English
    "a", "an", "the", "is", "am", "are", "was", "were", "be",
    "been", "being", "i", "my", "me", "we", "our", "you", "your",
    "he", "she", "it", "they", "them", "his", "her", "its",
    "do", "does", "did", "have", "has", "had", "will", "would",
    "can", "could", "should", "shall", "may", "might",
    "to", "of", "in", "on", "at", "for", "with", "from", "by",
    "that", "this", "these", "those", "what", "which", "who",
    "and", "or", "but", "not", "so", "if", "then",
    "very", "just", "also", "really", "about",

    # Telugu romanised
    "naa", "na", "nenu", "naaku", "lo", "ki", "ni", "anu",
    "ante", "undi", "chala", "chestha",

    # Hindi romanised
    "mera", "meri", "main", "mujhe", "hai", "hain", "ka", "ki",
    "ke", "ko", "se", "par", "pe", "bhi", "bahut", "karta",
}


def _extract_keywords(text):
    """Pull meaningful words from text, ignoring stop words."""
    words = re.findall(
        r"[\w\u0900-\u097F\u0C00-\u0C7F]+",
        text.lower(),
    )
    return [w for w in words if w not in _STOP_WORDS and len(w) > 2]