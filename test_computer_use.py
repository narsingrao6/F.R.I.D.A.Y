# Phase 3 regression tests: computer vision + computer use.
# Run with the venv python:  .venv\Scripts\python.exe test_computer_use.py
# Safe by design: FRIDAY_DRY_RUN_PC_CONTROL=1 prevents any real clicks/typing.

import os

os.environ.setdefault("FRIDAY_DRY_RUN_PC_CONTROL", "1")

import sys

from core.context import ContextManager
from core.executor import TaskExecutor
from core.nlu import NLUAnalyzer, serialize_intent
from core.permission import PermissionLevel, PermissionManager
from core.planner import TaskPlanner
from core.registry import ToolRegistry
from core.router import TaskRouter
from tools.computer_use import (
    handle_computer_use_command,
    handle_screen_vision_command,
)
from tools.computer_use.agent import _is_dangerous
from tools.computer_use.keyboard import resolve_key
from tools.computer_use.ocr import OcrEngine, OcrWord
from tools.computer_use.vision import (
    ElementMatch,
    find_elements,
    normalize,
    pick_target,
)

FAILED = []


def check(label, condition):
    print(("PASS" if condition else "FAIL"), "-", label)
    if not condition:
        FAILED.append(label)


# ------------------------------------------------------------------
# 1. NLU intents + serialize_intent
# ------------------------------------------------------------------
nlu = NLUAnalyzer()


def ser(text, ctx):
    return serialize_intent(nlu.analyze(text, "en"), ctx)


ctx = ContextManager()
check("select click_element", ser("click the settings button", ctx) == "click settings button")
check("select click continue", ser("click the button that says continue", ctx) == "click continue")
check("select double click", ser("double click youtube", ctx) == "double click youtube")
check("select right click", ser("right click start menu", ctx) == "right click start menu")
check(
    "select open+click",
    ser("open chrome and click youtube", ctx) == "open chrome and click youtube",
)
check(
    "select type-in-field",
    ser("type minecraft in the search box", ctx) == "type minecraft in the search box",
)
check("bare click still click", ser("click", ctx) == "click")
check("bare type still type", ser("type hello", ctx) == "type hello")
check("press enter not hijacked", ser("press enter", ctx) == "press enter")
check("scroll down not hijacked", ser("scroll down", ctx) == "scroll down")

ctx2 = ContextManager()
ser("click the chat icon", ctx2)
check("pronoun resolves", ser("click it", ctx2) == "click chat icon")
check("last_screen_target stored", ctx2.get_metadata("last_screen_target") == "chat icon")


# ------------------------------------------------------------------
# 2. Router routing (boundaries vs pc_control / app_control)
# ------------------------------------------------------------------
def build_registry():
    reg = ToolRegistry()
    ctx = ContextManager()

    def screen_vision_handler(command, language="en"):
        return handle_screen_vision_command(command, language=language, context=ctx)

    def computer_use_handler(command, language="en"):
        return handle_computer_use_command(command, language=language, context=ctx)

    reg.register("screen_vision", "read screen", screen_vision_handler)
    reg.register("computer_use", "use computer", computer_use_handler)

    # Minimal stand-ins so pc/app/search/message routing can be compared.
    reg.register("pc_control", "pc control", lambda c, language="en": "pc")
    reg.register("app_control", "apps", lambda c, language="en": "app")
    return reg


router = TaskRouter(build_registry())

check(
    "route click-target -> computer_use",
    router.route("click settings button").tool_name == "computer_use",
)
check(
    "route double-click -> computer_use",
    router.route("double click youtube").tool_name == "computer_use",
)
check(
    "route open-and-click -> computer_use",
    router.route("open chrome and click youtube").tool_name == "computer_use",
)
check(
    "route type-in-field -> computer_use",
    router.route("type minecraft in the search box").tool_name == "computer_use",
)
check(
    "route scroll-until -> computer_use",
    router.route("scroll until you see downloads").tool_name == "computer_use",
)
check(
    "route drag -> computer_use",
    router.route("drag the file to the folder").tool_name == "computer_use",
)
check(
    "route go back -> computer_use",
    router.route("go back").tool_name == "computer_use",
)
check(
    "route describe -> screen_vision",
    router.route("what is on my screen").tool_name == "screen_vision",
)
check(
    "route bare click -> pc_control",
    router.route("click").tool_name == "pc_control",
)
check(
    "route bare press -> pc_control",
    router.route("press enter").tool_name == "pc_control",
)
check(
    "route bare scroll -> pc_control",
    router.route("scroll down").tool_name == "pc_control",
)
check(
    "route plain type -> pc_control",
    router.route("type hello").tool_name == "pc_control",
)
check(
    "route go back track stays media",
    router.route("go back track").tool_name == "pc_control",
)
check(
    "route open app -> app_control",
    router.route("open chrome").tool_name == "app_control",
)


# ------------------------------------------------------------------
# 3. Vision: normalize / find_elements / pick_target / safe point
# ------------------------------------------------------------------
check('normalize strips "the/button"', normalize("The Settings Button") == "settings")
check("normalize strips punctuation", normalize("Downloads,") == "downloads")

words = [
    OcrWord("Settings", (100, 100, 120, 30), 0.98),
    OcrWord("Chat", (400, 500, 90, 30), 0.95),
    OcrWord("Downloads", (100, 200, 140, 30), 0.90),
    OcrWord("New", (50, 700, 80, 25), 0.80),
    OcrWord("Message", (140, 700, 100, 25), 0.80),
]

exact = find_elements(words, "Settings")
check("find exact", len(exact) == 1 and exact[0].text == "Settings" and exact[0].score == 1.0)

sub = find_elements(words, "chat icon")
check("find substring", any("chat" in m.text.lower() for m in sub))

row = find_elements(words, "new message")
check(
    "find multi-word row",
    len(row) >= 1
    and row[0].matched == "new message"
    and row[0].box[3] > 20,
)

fuzzy = find_elements(words, "Settings button")
check("find fuzzy target", len(fuzzy) >= 1 and fuzzy[0].score >= 0.9)

missed = find_elements(words, "no such label here at all")
check("missing target -> empty", len(missed) == 0)

em = ElementMatch("Settings", (100, 100, 120, 30), 1.0, "settings")
check(
    "safe point center",
    em.safe_click_point() == (160, 115),
)
edge = ElementMatch("Edge", (0, 0, 20, 20), 1.0, "edge")
check(
    "safe point margin",
    edge.safe_click_point(1920, 1080) == (60, 60),
)

mk1 = ElementMatch("OK", (10, 10, 40, 25), 1.0, "ok")
mk2 = ElementMatch("OK", (300, 300, 40, 25), 0.97, "ok")
choice, ambiguous = pick_target([mk1, mk2])
check("two equal hits -> ambiguous", ambiguous is True and choice is None)

single, ambiguous2 = pick_target([mk1])
check("single hit -> chosen", single is mk1 and ambiguous2 is False)


# ------------------------------------------------------------------
# 4. Keyboard key resolution (pure mapping, no input sent)
# ------------------------------------------------------------------
check("resolve enter", resolve_key("enter")[1] == "ENTER")
check("resolve return", resolve_key("return")[1] == "ENTER")
check("resolve page down", resolve_key("page down")[1] == "PAGE_DOWN")
check("resolve f4", resolve_key("f4")[1] == "F4")
check("resolve unknown -> None", resolve_key("zzz") is None)


# ------------------------------------------------------------------
# 5. Danger guard (never auto-click sensitive targets)
# ------------------------------------------------------------------
check("danger blocks delete", _is_dangerous("delete everything") is True)
check("danger blocks shutdown", _is_dangerous("shut down now") is True)
check("danger blocks payment", _is_dangerous("confirm payment") is True)
check("safe target fine", _is_dangerous("settings") is False)
check("safe target fine 2", _is_dangerous("downloads") is False)


# ------------------------------------------------------------------
# 6. OCR engine cache with a fake provider (no model download needed)
# ------------------------------------------------------------------
class FakeProvider:
    name = "fake"
    calls = 0

    def available(self):
        return True

    def scan(self, image):
        FakeProvider.calls += 1
        return [OcrWord("Hello", (5, 5, 60, 20), 0.99)]


engine = OcrEngine(FakeProvider())
image = object()
first = engine.scan_words(image)
cached = engine.scan_words(None)
check(
    "ocr scan + None-image cache reuse",
    FakeProvider.calls == 1 and len(first) == 1 and len(cached) == 1,
)

engine2 = OcrEngine(FakeProvider())
check("ocr unavailable image -> empty", engine2.scan_words(None) == [])


# ------------------------------------------------------------------
# 7. Permissions: default levels + full-power toggle coverage
# ------------------------------------------------------------------
permissions = PermissionManager()
check(
    "screen_vision SAFE by default",
    permissions.get_level("screen_vision") == PermissionLevel.SAFE,
)
check(
    "computer_use CONFIRM by default",
    permissions.get_level("computer_use") == PermissionLevel.CONFIRM,
)

allowed_names = set(permissions.tools())
check("full-power covers new tools", {"screen_vision", "computer_use"} <= allowed_names)

for name in allowed_names:
    permissions.set_level(name, PermissionLevel.SAFE)
check(
    "full-power makes computer_use safe",
    permissions.is_safe("computer_use") and permissions.is_safe("screen_vision"),
)


# ------------------------------------------------------------------
# 8. Dry-run execution through the real tool chain (no live input)
# ------------------------------------------------------------------
reg = build_registry()
plan = TaskPlanner()
perms = PermissionManager()
perms.set_level("computer_use", PermissionLevel.SAFE)
executor = TaskExecutor(reg, router, permissions=perms)

res = executor.execute_plan(plan.create_plan("click settings button", "en"))
check(
    "dry-run click degrades gracefully",
    res.success and "couldn't find" in str(res.results[-1]),
)

res = executor.execute_plan(plan.create_plan("scroll until you see downloads", "en"))
check(
    "dry-run scroll degrades gracefully",
    res.success and "couldn't find" in str(res.results[-1]),
)

res = executor.execute_plan(plan.create_plan("what is on my screen", "en"))
check(
    "dry-run describe degrades gracefully",
    res.success and "capture" in str(res.results[-1]),
)

perms2 = PermissionManager()
exec2 = TaskExecutor(reg, router, permissions=perms2)
res = exec2.execute_plan(plan.create_plan("click settings button", "en"))
check(
    "computer_use requires confirmation",
    getattr(res, "requires_confirmation", False) and res.tool_name == "computer_use",
)

try:
    c = res.results[-1]
except IndexError:
    c = None
check("confirmation yields no result yet", c is None)

print()
print("=" * 40)
if FAILED:
    print(f"{len(FAILED)} FAILURE(S): {FAILED}")
    sys.exit(1)
print("ALL COMPUTER_USE TESTS PASSED")