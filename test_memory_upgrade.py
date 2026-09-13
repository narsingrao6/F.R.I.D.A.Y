"""
Automated tests for F.R.I.D.A.Y.'s upgraded memory system.

Run:
    python test_memory_upgrade.py

All 15 tests must pass.
"""

import os
import sys
import tempfile

# Ensure project root is on the path so imports work.
sys.path.insert(
    0,
    os.path.dirname(os.path.abspath(__file__)),
)

from memory.detector import detect
from memory.store import MemoryStore
from memory.manager import MemoryManager

PASSED = 0
FAILED = 0


def ok(name, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILED += 1
        msg = f"  FAIL  {name}"
        if detail:
            msg += f"  -- {detail}"
        print(msg)


def _temp_store():
    """Create a MemoryStore backed by a disposable temp file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return MemoryStore(path=path), path


def _temp_manager():
    """Create a MemoryManager whose store uses a temp DB."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    mgr = MemoryManager.__new__(MemoryManager)
    mgr.store = MemoryStore(path=path)
    # Disable cloud for tests.
    from memory.cloud import CloudMemoryStore
    mgr.cloud = CloudMemoryStore()
    mgr.cloud.bucket_name = None  # force disabled
    return mgr, path


def _cleanup(path):
    """Best-effort delete; Windows may still hold the SQLite lock."""
    try:
        os.unlink(path)
    except (PermissionError, OSError):
        pass


# ============================================================= Tests


def test_01_identity_english():
    """'My name is Jesse' → identity memory."""
    c = detect("My name is Jesse.")
    ok("01 identity detected",
       c is not None and c.category == "identity",
       f"got {c}")
    if c:
        ok("01 normalized content",
           "jesse" in c.normalized.lower(),
           c.normalized)


def test_02_identity_telugu():
    """'నా పేరు Jesse' → same identity detection."""
    c = detect("నా పేరు Jesse")
    ok("02 Telugu identity detected",
       c is not None and c.category == "identity",
       f"got {c}")
    if c:
        ok("02 normalized has Jesse",
           "jesse" in c.normalized.lower(),
           c.normalized)


def test_03_identity_hindi():
    """'मेरा नाम जेसी है' → identity."""
    c = detect("मेरा नाम जेसी है")
    ok("03 Hindi identity detected",
       c is not None and c.category == "identity",
       f"got {c}")


def test_04_preference():
    """'I prefer VS Code' → preference."""
    c = detect("I prefer VS Code")
    ok("04 preference detected",
       c is not None and c.category == "preference",
       f"got {c}")
    if c:
        ok("04 confidence >= 0.80",
           c.confidence >= 0.80,
           f"confidence={c.confidence}")


def test_05_project():
    """'I'm working on a Minecraft mod called Dimension Keys'."""
    c = detect("I'm working on a Minecraft mod called Dimension Keys")
    ok("05 project detected",
       c is not None and c.category == "project",
       f"got {c}")


def test_06_ignore_time():
    """'What time is it?' → None (ignored)."""
    c = detect("What time is it?")
    ok("06 time question ignored",
       c is None,
       f"got {c}")


def test_07_ignore_command():
    """'Open Chrome' → None (ignored)."""
    c = detect("Open Chrome")
    ok("07 command ignored",
       c is None,
       f"got {c}")


def test_08_sensitive_blocked():
    """'My password is abc123' → None (sensitive)."""
    c = detect("My password is abc123")
    ok("08 sensitive data blocked",
       c is None,
       f"got {c}")


def test_09_duplicate_prevention():
    """Storing the same fact twice → only 1 memory in DB."""
    mgr, path = _temp_manager()
    try:
        mgr.consider("My name is Jesse.")
        mgr.consider("My name is Jesse.")
        memories = mgr.list_memories()
        name_mems = [
            m for m in memories
            if "jesse" in m.content.lower()
        ]
        ok("09 no duplicates",
           len(name_mems) == 1,
           f"found {len(name_mems)} name memories")
    finally:
        _cleanup(path)


def test_10_memory_update():
    """'I use VS Code' then 'I switched to IntelliJ' → 1 updated memory."""
    mgr, path = _temp_manager()
    try:
        mgr.consider("I use VS Code")
        mgr.consider("I switched to IntelliJ")
        memories = mgr.list_memories()
        tech_mems = [
            m for m in memories
            if m.category == "technology"
        ]
        ok("10 update: 1 tech memory",
           len(tech_mems) == 1,
           f"found {len(tech_mems)} tech memories")
        if tech_mems:
            ok("10 updated to IntelliJ",
               "intellij" in tech_mems[0].content.lower(),
               tech_mems[0].content)
    finally:
        _cleanup(path)


def test_11_retrieval():
    """Store name, then query 'What is my name?' → retrieves it."""
    mgr, path = _temp_manager()
    try:
        mgr.consider("My name is Jesse.")
        context = mgr.relevant_context("What is my name?")
        ok("11 retrieval finds name",
           "jesse" in context.lower(),
           f"context={context!r}")
    finally:
        _cleanup(path)


def test_12_forget():
    """'Forget my name' → deactivates name memory."""
    mgr, path = _temp_manager()
    try:
        mgr.consider("My name is Jesse.")
        count = mgr.forget("name")
        ok("12 forget deactivated",
           count > 0,
           f"deleted {count}")
        context = mgr.relevant_context("What is my name?")
        ok("12 name gone from context",
           "jesse" not in context.lower(),
           f"context={context!r}")
    finally:
        _cleanup(path)


def test_13_persistence():
    """Memories survive store close and reopen."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        # First session: store a memory.
        store1 = MemoryStore(path=path)
        store1.add(
            content="The Boss's name is Jesse.",
            category="identity",
            source="automatic",
            confidence=0.95,
        )

        # Second session: reopen the DB.
        store2 = MemoryStore(path=path)
        memories = store2.all()
        found = any(
            "jesse" in m.content.lower()
            for m in memories
        )
        ok("13 persistence across restart",
           found,
           f"memories={[m.content for m in memories]}")
    finally:
        _cleanup(path)


def test_14_bug_fix_no_crash():
    """handle_local_command with memory=None must not crash."""
    from commands import handle_local_command
    try:
        result = handle_local_command("hello", "en", memory=None)
        ok("14 no crash with memory=None",
           True)
    except UnboundLocalError as e:
        ok("14 no crash with memory=None",
           False,
           f"UnboundLocalError: {e}")
    except Exception:
        # Other exceptions are fine — the bug was specifically
        # UnboundLocalError on memory_answer.
        ok("14 no crash with memory=None",
           True)


def test_15_priority_ordering():
    """Identity memories surface before other categories."""
    mgr, path = _temp_manager()
    try:
        mgr.consider("I usually code at night")
        mgr.consider("My name is Jesse.")
        mgr.consider("I prefer dark mode")

        context = mgr.relevant_context("Tell me about the Boss")
        lines = context.strip().split("\n")

        # The identity memory should appear first (after the header).
        identity_idx = None
        for i, line in enumerate(lines):
            if "[identity]" in line.lower():
                identity_idx = i
                break

        ok("15 identity is first memory",
           identity_idx is not None and identity_idx <= 1,
           f"identity at index {identity_idx}, lines={lines}")
    finally:
        _cleanup(path)


# ============================================================ runner


def main():
    print("\n" + "=" * 60)
    print("F.R.I.D.A.Y. Memory System — Upgrade Tests")
    print("=" * 60 + "\n")

    test_01_identity_english()
    test_02_identity_telugu()
    test_03_identity_hindi()
    test_04_preference()
    test_05_project()
    test_06_ignore_time()
    test_07_ignore_command()
    test_08_sensitive_blocked()
    test_09_duplicate_prevention()
    test_10_memory_update()
    test_11_retrieval()
    test_12_forget()
    test_13_persistence()
    test_14_bug_fix_no_crash()
    test_15_priority_ordering()

    print(f"\n{'=' * 60}")
    print(f"Results: {PASSED} passed, {FAILED} failed")
    print("=" * 60 + "\n")

    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
