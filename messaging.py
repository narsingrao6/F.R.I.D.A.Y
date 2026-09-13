"""
F.R.I.D.A.Y. Messaging tool.

Sends WhatsApp messages using the WhatsApp desktop client. F.R.I.D.A.Y.
focuses the app, opens the contact's chat via the search box, types the
message and presses Enter to send it.

Handles:
    "send a message to father saying good morning"
    "message mom that i will be late"
    "whatsapp john happy birthday"
"""

from __future__ import annotations

import ctypes
import re
import time

from pc_control import (
    _combo,
    _find_app_window,
    _tap_key,
    _type_unicode,
    VK,
)

_WAKE_WORD = re.compile(
    r"^(?:hey\s+)?"
    r"(?:friday|fraiday|fry\s*day|fryday)"
    r"(?:[,.\s]+|$)",
    re.IGNORECASE,
)

# "send (a) message to <contact> saying|that <text>"
_SEND_TO_RE = re.compile(
    r"^(?:send(?:\s+a)?\s+message\s+to|"
    r"send\s+whatsapp(?:\s+message)?\s+to)\s+"
    r"(.+?)\s+"
    r"(?:saying|that|stating|text|with\s+the\s+message|[,:])\s+"
    r"(.+)$",
    re.IGNORECASE,
)

# "message|whatsapp|text <contact> saying|that <text>"
_SHORT_RE = re.compile(
    r"^(?:message|whatsapp|text)\s+"
    r"(.+?)\s+"
    r"(?:saying|that|stating|text\s+is|[,:])\s+"
    r"(.+)$",
    re.IGNORECASE,
)

# "whatsapp <contact> <text>" (single-word contact, no separator)
_WHATSAPP_RE = re.compile(
    r"^whatsapp\s+(\S+)\s+(.+)$",
    re.IGNORECASE,
)


def _parse_message(command: str) -> tuple[str, str] | None:
    text = _WAKE_WORD.sub("", command or "").strip()

    match = _SEND_TO_RE.match(text)
    if not match:
        match = _SHORT_RE.match(text)
    if not match:
        match = _WHATSAPP_RE.match(text)
    if not match:
        return None

    contact = match.group(1).strip(" ,.-")
    message = match.group(2).strip()

    if not contact or not message:
        return None

    return contact, message


def _find_or_open_whatsapp() -> int | None:
    hwnd = _find_app_window("whatsapp")

    if hwnd:
        return hwnd

    try:
        from app_launcher import handle_app_command

        handle_app_command("open whatsapp", "en")
    except Exception:
        pass

    time.sleep(2.5)
    return _find_app_window("whatsapp")


def handle_messaging_command(
    command: str,
    language: str = "en",
) -> str | None:
    """Send a WhatsApp message. Returns a spoken response or None."""

    if not command or not command.strip():
        return None

    parsed = _parse_message(command)

    if not parsed:

        if language == "te":

            return (
                "దయచేసి Sahayak: "
                "send a message to "
                "<name> saying <message> "
                "అని చెప్పండి బాస్."
            )

        if language == "hi":

            return (
                "बॉस, ऐसे बोलिए: "
                "send a message to "
                "<name> saying <message>"
            )

        return (
            "Say it like this, Boss: "
            "send a message to <name> "
            "saying <message>"
        )

    contact, message_text = parsed

    hwnd = _find_or_open_whatsapp()

    if not hwnd:

        if language == "te":

            return (
                f"{contact} కు message "
                f"పంపాలంటే WhatsApp "
                f"తెరవలేకపోయాను బాస్."
            )

        if language == "hi":

            return (
                f"WhatsApp नहीं खोल पाई, "
                f"{contact} को message "
                f"नहीं भेज पाई बॉस."
            )

        return (
            f"I couldn't open WhatsApp to "
            f"message {contact}, Boss."
        )

    ctypes.windll.user32.ShowWindow(hwnd, 9)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.6)

    _combo("CTRL", "F")
    time.sleep(0.5)
    _type_unicode(contact)
    time.sleep(1.0)
    _tap_key(VK["ENTER"])
    time.sleep(1.2)

    _type_unicode(message_text)
    time.sleep(0.3)
    _tap_key(VK["ENTER"])

    if language == "te":

        return (
            f"{contact} కు message "
            f"పంపాను బాస్."
        )

    if language == "hi":

        return (
            f"{contact} को message "
            f"भेज दिया बॉस."
        )

    return (
        f"Message sent to {contact}, Boss."
    )