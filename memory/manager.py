"""
Memory manager — orchestrates detection, storage, retrieval, updates,
deduplication, forgetting, and cloud sync.
"""

import re

from .cloud import CloudMemoryStore
from .detector import detect
from .models import CATEGORIES
from .store import MemoryStore


# Below this confidence the detector's output is too vague to auto-save.
MIN_AUTO_CONFIDENCE = 0.75


class MemoryManager:
    def __init__(self):
        self.store = MemoryStore()
        self.cloud = CloudMemoryStore()
        try:
            self._try_cloud_restore()
        except Exception:
            # Never let a cloud hiccup block startup.
            pass

    # ------------------------------------------------- cloud restore

    def _try_cloud_restore(self):
        if not self.cloud.enabled:
            return

        cloud_memories = self.cloud.download()

        if cloud_memories is None:
            return

        try:
            local_memories = self.store.all()

            if not local_memories:
                self.store.replace_from_export(cloud_memories)
                print("F.R.I.D.A.Y.: Memory restored from cloud.")

        except Exception as error:
            print(
                "F.R.I.D.A.Y.: Memory restore failed "
                f"({type(error).__name__})."
            )

    # ------------------------------------------- explicit remember

    def remember(self, content, category="explicit", confidence=1.0):
        """Store an explicitly requested memory (pinned)."""
        content = content.strip()

        if not content:
            return None

        # Deduplicate: exact match
        existing = self._find_exact(content)
        if existing is not None:
            return existing.id

        memory_id = self.store.add(
            content=content,
            category=category,
            source="explicit",
            confidence=confidence,
            pinned=True,
        )

        self.sync()
        return memory_id

    # ---------------------------------------------------- forget

    def forget(self, query):
        """Deactivate memories matching a query string."""
        query = query.strip()

        if not query:
            return 0

        # Try category-aware forgetting first.
        # e.g. "my name" → search in identity memories.
        category_hints = {
            "name":     "identity",
            "project":  "project",
            "editor":   "technology",
            "ide":      "technology",
            "goal":     "goal",
            "habit":    "habit",
            "favorite": "favorite",
            "favourite": "favorite",
        }

        lower = query.lower()

        for keyword, category in category_hints.items():
            if keyword in lower:
                # Delete all active memories in that category
                # whose content matches the query.
                count = self.store.delete_matching(keyword)
                if count:
                    self.sync()
                    return count

        # Fall back to generic text matching.
        count = self.store.delete_matching(query)

        if count:
            self.sync()

        return count

    # ------------------------------------------------ list memories

    def list_memories(self):
        return self.store.all()

    # ----------------------------------------- automatic consider

    def consider(self, text):
        """
        Analyse a user utterance and automatically store it if the
        detector decides it is worth remembering.
        """
        candidate = detect(text)

        if candidate is None:
            return None

        # Explicit commands always go through.
        if candidate.category == "explicit":
            return self.remember(
                candidate.normalized,
                category="explicit",
                confidence=1.0,
            )

        # Below threshold = too vague to auto-save.
        if candidate.confidence < MIN_AUTO_CONFIDENCE:
            return None

        # The content to store is the normalised form
        # ("The Boss's name is Jesse.").
        store_content = candidate.normalized

        # --- duplicate check (exact) ---
        existing = self._find_exact(store_content)
        if existing is not None:
            return existing.id

        # --- update check (same category, overlapping subject) ---
        updated_id = self._try_update(store_content, candidate.category)
        if updated_id is not None:
            return updated_id

        # --- save new memory ---
        memory_id = self.store.add(
            content=store_content,
            category=candidate.category,
            source="automatic",
            confidence=candidate.confidence,
        )

        self.sync()
        return memory_id

    # ----------------------------------------- relevant context

    def relevant_context(self, query, limit=8):
        """
        Build a memory-context block to inject into the AI prompt.
        Memories are sorted by: pinned → category priority → confidence.
        """
        words = re.findall(
            r"[\w\u0900-\u097F\u0C00-\u0C7F]+",
            query.lower(),
        )

        words = [
            word
            for word in words
            if word not in _STOP_WORDS and len(word) > 1
        ]

        memories = self.store.search(
            words,
            limit=limit,
        )

        if not memories:
            return ""

        # Sort by priority: pinned first, then category rank, then
        # confidence descending.
        memories.sort(
            key=lambda m: (
                not m.pinned,
                m.priority,
                -m.confidence,
            )
        )

        lines = [
            f"- [{m.category}] {m.content}"
            for m in memories
        ]

        return (
            "Relevant memories about the Boss:\n"
            + "\n".join(lines)
        )

    # ------------------------------------------------------- sync

    def sync(self):
        if not self.cloud.enabled:
            return False

        try:
            return self.cloud.upload(
                self.store.export()
            )

        except Exception as error:
            print(
                "F.R.I.D.A.Y.: Memory sync failed "
                f"({type(error).__name__})."
            )

            return False

    # --------------------------------------------------- internals

    def _find_exact(self, content):
        """Return an existing active memory with identical content."""
        normalized = content.lower().strip()
        for memory in self.store.all():
            if memory.content.lower().strip() == normalized:
                return memory
        return None

    def _try_update(self, new_content, category):
        """
        If an existing memory of the same category covers the same
        subject, update it instead of creating a duplicate.

        Example:
            existing: "The Boss uses VS Code."  (technology)
            new:      "The Boss uses IntelliJ."  (technology)
            → Update the old one to "The Boss uses IntelliJ."
        """
        similar = self.store.find_similar(new_content, threshold=0.4)

        for score, memory in similar:
            if memory.category != category:
                continue

            # Same category and overlapping subject → update.
            self.store.update(
                memory.id,
                content=new_content,
            )
            self.sync()
            return memory.id

        return None


# -------------------------------------------------------- stop words

_STOP_WORDS = {
    # English
    "what", "is", "the", "my", "me", "do", "you",
    "remember", "about", "tell", "can", "i", "we",
    "are", "how", "does", "what's", "which", "a",
    "an", "in", "on", "at", "to", "for", "of",
    "and", "or", "be", "it", "was", "has", "have",
    "will", "would", "could", "should", "did",
    "am", "been", "not", "with", "this", "that",
    "just", "so", "if", "but",

    # Telugu romanised
    "enti", "emi", "ela", "cheppu", "naaku", "naa",
    "nenu", "lo", "ki", "ni",

    # Hindi romanised
    "kya", "kaun", "kaise", "batao", "mera", "mujhe",
    "main", "hai", "hain", "ka", "ki", "ke", "ko",
    "se", "ye", "wo",

    # Telugu script stop words
    "ఏంటి", "ఎలా", "ఏమి", "నాకు", "నా", "నేను",
    "చెప్పు", "లో", "కి", "ని",

    # Hindi script stop words
    "क्या", "कौन", "कैसे", "बताओ", "मेरा", "मुझे",
    "मैं", "है", "हैं", "का", "की", "के", "को",
    "से", "ये", "वो",
}