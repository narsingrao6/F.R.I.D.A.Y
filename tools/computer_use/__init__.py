"""
F.R.I.D.A.Y. Computer Use layer.

Screen-aware computer agent for Phase 3:
OBSERVE -> UNDERSTAND -> PLAN -> ACT -> VERIFY.

Modules:
    screen.py     capture/describe the screen to PIL images
    ocr.py        local text detection (RapidOCR / onnxruntime)
    vision.py     find visible elements on the screen
    mouse.py      move & click the pointer
    keyboard.py   type and press keys
    agent.py      the natural-language computer-use agent + tool handlers
"""

from .agent import (
    handle_computer_use_command,
    handle_screen_vision_command,
    ComputerUseAgent,
)

__all__ = (
    "handle_computer_use_command",
    "handle_screen_vision_command",
    "ComputerUseAgent",
)