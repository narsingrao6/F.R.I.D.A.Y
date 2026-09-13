"""
F.R.I.D.A.Y. Application Launcher
---------------------------------

Fast Windows application and website launcher.

Features:
- Background indexing of Start Menu/Desktop shortcuts
- Common application aliases
- Fuzzy matching
- Whisper transcription tolerance
- English + Hindi + Telugu app names
- Native Hindi/Telugu app-name support
- Website launching
- Microsoft Store / Windows URI launching
- Application closing
- Protected Windows-process safety
- "close it" context support
- No network access
"""

from __future__ import annotations

import csv
import os
import re
import subprocess
import threading
import time
from difflib import SequenceMatcher
from io import StringIO
from typing import Optional

import random


# ============================================================
# WINDOWS PROCESS FLAGS
# ============================================================

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0)


# ============================================================
# APPLICATION ALIASES
# ============================================================

_ALIASES = {

    # ---------------- Browsers ----------------

    "chrome": ("Google Chrome", "chrome.exe"),
    "google chrome": ("Google Chrome", "chrome.exe"),
    "browser": ("Google Chrome", "chrome.exe"),

    "firefox": ("Mozilla Firefox", "firefox.exe"),
    "mozilla firefox": ("Mozilla Firefox", "firefox.exe"),

    "edge": ("Microsoft Edge", "msedge.exe"),
    "microsoft edge": ("Microsoft Edge", "msedge.exe"),

    "brave": ("Brave Browser", "brave.exe"),
    "brave browser": ("Brave Browser", "brave.exe"),

    "opera": ("Opera", "opera.exe"),
    "vivaldi": ("Vivaldi", "vivaldi.exe"),

    # ---------------- Development ----------------

    "vs code": ("Visual Studio Code", "Code.exe"),
    "vscode": ("Visual Studio Code", "Code.exe"),
    "visual studio code": ("Visual Studio Code", "Code.exe"),

    "visual studio": ("Visual Studio", "devenv.exe"),

    "pycharm": ("PyCharm", "pycharm64.exe"),
    "intellij": ("IntelliJ IDEA", "idea64.exe"),
    "intellij idea": ("IntelliJ IDEA", "idea64.exe"),

    "android studio": ("Android Studio", "studio64.exe"),

    "sublime": ("Sublime Text", "sublime_text.exe"),
    "sublime text": ("Sublime Text", "sublime_text.exe"),

    "atom": ("Atom", "atom.exe"),

    "notepad++": ("Notepad++", "notepad++.exe"),
    "notepad plus plus": ("Notepad++", "notepad++.exe"),

    "git bash": ("Git Bash", "git-bash.exe"),
    "postman": ("Postman", "Postman.exe"),
    "docker": ("Docker Desktop", "Docker Desktop.exe"),

    # ---------------- Communication ----------------

    "whatsapp": ("WhatsApp", "WhatsApp.exe"),
    "telegram": ("Telegram", "Telegram.exe"),
    "discord": ("Discord", "Discord.exe"),
    "slack": ("Slack", "slack.exe"),

    "teams": ("Microsoft Teams", "ms-teams.exe"),
    "microsoft teams": ("Microsoft Teams", "ms-teams.exe"),

    "zoom": ("Zoom", "Zoom.exe"),
    "skype": ("Skype", "Skype.exe"),

    # ---------------- Microsoft Office ----------------

    "word": ("Microsoft Word", "WINWORD.EXE"),
    "microsoft word": ("Microsoft Word", "WINWORD.EXE"),

    "excel": ("Microsoft Excel", "EXCEL.EXE"),
    "microsoft excel": ("Microsoft Excel", "EXCEL.EXE"),

    "powerpoint": ("Microsoft PowerPoint", "POWERPNT.EXE"),
    "microsoft powerpoint": ("Microsoft PowerPoint", "POWERPNT.EXE"),
    "ppt": ("Microsoft PowerPoint", "POWERPNT.EXE"),

    "outlook": ("Microsoft Outlook", "OUTLOOK.EXE"),
    "microsoft outlook": ("Microsoft Outlook", "OUTLOOK.EXE"),

    "onenote": ("OneNote", "ONENOTE.EXE"),
    "access": ("Microsoft Access", "MSACCESS.EXE"),

    # ---------------- Media ----------------

    "vlc": ("VLC Media Player", "vlc.exe"),
    "vlc player": ("VLC Media Player", "vlc.exe"),

    "spotify": ("Spotify", "Spotify.exe"),
    "itunes": ("iTunes", "iTunes.exe"),

    "obs": ("OBS Studio", "obs64.exe"),
    "obs studio": ("OBS Studio", "obs64.exe"),

    "audacity": ("Audacity", "Audacity.exe"),

    # ---------------- Utilities ----------------

    "notepad": ("Notepad", "notepad.exe"),

    "calculator": ("Calculator", "calc.exe"),
    "calc": ("Calculator", "calc.exe"),

    "paint": ("Paint", "mspaint.exe"),

    "snipping tool": ("Snipping Tool", "SnippingTool.exe"),

    "task manager": ("Task Manager", "Taskmgr.exe"),

    "control panel": ("Control Panel", "control.exe"),

    "settings": ("Settings", "ms-settings:"),

    "file explorer": ("File Explorer", "explorer.exe"),
    "explorer": ("File Explorer", "explorer.exe"),

    "cmd": ("Command Prompt", "cmd.exe"),
    "command prompt": ("Command Prompt", "cmd.exe"),

    "terminal": ("Windows Terminal", "wt.exe"),
    "windows terminal": ("Windows Terminal", "wt.exe"),

    "powershell": ("PowerShell", "powershell.exe"),

    # ---------------- Creative ----------------

    "photoshop": ("Adobe Photoshop", "Photoshop.exe"),
    "illustrator": ("Adobe Illustrator", "Illustrator.exe"),
    "premiere": ("Adobe Premiere Pro", "Adobe Premiere Pro.exe"),
    "after effects": ("Adobe After Effects", "AfterFX.exe"),

    "figma": ("Figma", "Figma.exe"),
    "blender": ("Blender", "blender.exe"),
    "gimp": ("GIMP", "gimp-2.10.exe"),
    "canva": ("Canva", "Canva.exe"),

    # ---------------- Gaming ----------------

    "steam": ("Steam", "steam.exe"),
    "epic games": ("Epic Games Launcher", "EpicGamesLauncher.exe"),
    "minecraft": ("Minecraft Launcher", "MinecraftLauncher.exe"),

    # ---------------- System ----------------

    "this pc": ("This PC", "explorer.exe"),
    "my computer": ("This PC", "explorer.exe"),
    "recycle bin": ("Recycle Bin", "explorer.exe"),
}


# ============================================================
# COMMON USER FOLDERS & DRIVES
# ============================================================

_FOLDERS = {

    # User profile folders (resolved under %USERPROFILE%).
    "downloads": "Downloads",
    "download": "Downloads",
    "downloaded": "Downloads",
    "documents": "Documents",
    "document": "Documents",
    "docs": "Documents",
    "desktop": "Desktop",
    "pictures": "Pictures",
    "picture": "Pictures",
    "photos": "Pictures",
    "photo": "Pictures",
    "music": "Music",
    "videos": "Videos",
    "video": "Videos",

    "my downloads": "Downloads",
    "my documents": "Documents",
    "my docs": "Documents",
    "my desktop": "Desktop",
    "my pictures": "Pictures",
    "my photos": "Pictures",
    "my music": "Music",
    "my videos": "Videos",
}

_DRIVE_LETTER_RE = re.compile(r"^([A-Za-z]):\\?$")


# ============================================================
# WINDOWS URI / STORE APPS
# ============================================================

_UWP_APPS = {
    "calculator": "calculator:",
    "calc": "calculator:",

    "settings": "ms-settings:",

    "store": "ms-windows-store:",
    "microsoft store": "ms-windows-store:",

    "photos": "ms-photos:",
    "camera": "microsoft.windows.camera:",

    "clock": "ms-clock:",
    "alarms": "ms-clock:",

    "maps": "bingmaps:",
    "weather": "bingweather:",

    "mail": "outlookmail:",
    "calendar": "outlookcal:",

    "xbox": "xbox:",

    "movies": "mswindowsvideo:",
    "groove": "mswindowsmusic:",
    "music": "mswindowsmusic:",

    "whatsapp": "whatsapp:",
    "spotify": "spotify:",
    "telegram": "telegram:",
    "discord": "discord:",
    "messenger": "messenger:",
}


# ============================================================
# WEBSITE ALIASES
# ============================================================

_WEBSITES = {

    "youtube": "https://www.youtube.com",
    "you tube": "https://www.youtube.com",
    "utube": "https://www.youtube.com",

    "google": "https://www.google.com",

    "gmail": "https://mail.google.com",
    "g mail": "https://mail.google.com",

    "netflix": "https://www.netflix.com",
    "net flix": "https://www.netflix.com",

    "prime video": "https://www.primevideo.com",
    "prime": "https://www.primevideo.com",

    "amazon": "https://www.amazon.com",

    "twitter": "https://twitter.com",
    "x": "https://twitter.com",

    "facebook": "https://www.facebook.com",
    "face book": "https://www.facebook.com",
    "fb": "https://www.facebook.com",

    "instagram": "https://www.instagram.com",
    "insta": "https://www.instagram.com",
    "insta gram": "https://www.instagram.com",

    "linkedin": "https://www.linkedin.com",
    "linked in": "https://www.linkedin.com",

    "github": "https://github.com",
    "git hub": "https://github.com",

    "chat gpt": "https://chatgpt.com",
    "chatgpt": "https://chatgpt.com",

    "openai": "https://openai.com",

    "claude": "https://claude.ai",

    "reddit": "https://www.reddit.com",
    "twitch": "https://www.twitch.tv",

    "wikipedia": "https://www.wikipedia.org",
    "wiki": "https://www.wikipedia.org",

    "yahoo": "https://www.yahoo.com",
    "bing": "https://www.bing.com",

    "hotstar": "https://www.hotstar.com",
    "jio cinema": "https://www.jiocinema.com",

    "flipkart": "https://www.flipkart.com",
    "zomato": "https://www.zomato.com",
    "swiggy": "https://www.swiggy.com",

    "pinterest": "https://www.pinterest.com",
    "quora": "https://www.quora.com",

    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
}


# ============================================================
# PROCESS NAME OVERRIDES
# ============================================================

_PROCESS_NAMES = {
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",

    "firefox": "firefox.exe",

    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",

    "brave": "brave.exe",

    "vs code": "Code.exe",
    "vscode": "Code.exe",
    "visual studio code": "Code.exe",

    "visual studio": "devenv.exe",

    "pycharm": "pycharm64.exe",
    "intellij": "idea64.exe",
    "intellij idea": "idea64.exe",

    "android studio": "studio64.exe",

    "word": "WINWORD.EXE",
    "microsoft word": "WINWORD.EXE",

    "excel": "EXCEL.EXE",
    "microsoft excel": "EXCEL.EXE",

    "powerpoint": "POWERPNT.EXE",
    "microsoft powerpoint": "POWERPNT.EXE",
    "ppt": "POWERPNT.EXE",

    "outlook": "OUTLOOK.EXE",

    "task manager": "Taskmgr.exe",

    "teams": "ms-teams.exe",
    "microsoft teams": "ms-teams.exe",

    "discord": "Discord.exe",
    "telegram": "Telegram.exe",
    "whatsapp": "WhatsApp.exe",

    "spotify": "Spotify.exe",

    "vlc": "vlc.exe",

    "steam": "steam.exe",

    "obs": "obs64.exe",
    "obs studio": "obs64.exe",

    "notepad": "notepad.exe",

    "paint": "mspaint.exe",

    "calculator": "calc.exe",
    "calc": "calc.exe",

    "blender": "blender.exe",

    "photoshop": "Photoshop.exe",

    "figma": "Figma.exe",

    "postman": "Postman.exe",

    "docker": "Docker Desktop.exe",

    "slack": "slack.exe",
    "zoom": "Zoom.exe",
    "skype": "Skype.exe",
}


# ============================================================
# PROTECTED WINDOWS PROCESSES
# ============================================================

_PROTECTED_PROCESSES = {
    "explorer.exe",
    "svchost.exe",
    "csrss.exe",
    "wininit.exe",
    "winlogon.exe",
    "lsass.exe",
    "services.exe",
    "smss.exe",
    "dwm.exe",
    "taskhost.exe",
    "taskhostw.exe",
    "sihost.exe",
    "shellexperiencehost.exe",
    "startmenuexperiencehost.exe",
    "searchhost.exe",
    "runtimebroker.exe",
    "system",
    "registry",
    "systemsettings.exe",
    "ctfmon.exe",
}


# ============================================================
# NATIVE HINDI / TELUGU APP NAMES
# ============================================================

_NATIVE_APP_NAMES = {

    # ---------------- Hindi ----------------

    "यूट्यूब": "youtube",
    "यू ट्यूब": "youtube",

    "गूगल": "google",
    "जीमेल": "gmail",

    "क्रोम": "chrome",

    "फ़ायरफ़ॉक्स": "firefox",
    "फायरफॉक्स": "firefox",

    "एज": "edge",

    "नोटपैड": "notepad",
    "कैलकुलेटर": "calculator",

    "व्हाट्सएप": "whatsapp",
    "वॉट्सऐप": "whatsapp",

    "टेलीग्राम": "telegram",
    "इंस्टाग्राम": "instagram",

    "फेसबुक": "facebook",
    "ट्विटर": "twitter",

    "नेटफ्लिक्स": "netflix",

    "अमेज़न": "amazon",
    "अमेज़ॉन": "amazon",

    "स्पॉटिफ़ाई": "spotify",
    "स्पॉटिफाई": "spotify",

    "रेडिट": "reddit",
    "लिंक्डइन": "linkedin",

    "पेंट": "paint",
    "वर्ड": "word",
    "एक्सेल": "excel",
    "पावरपॉइंट": "powerpoint",

    "फ़ाइल मैनेजर": "file explorer",

    "सेटिंग्स": "settings",
    "सेटिंग": "settings",

    "कैमरा": "camera",

    "फ़ोटो": "photos",
    "फोटो": "photos",

    # ---------------- Telugu ----------------

    "యూట్యూబ్": "youtube",
    "గూగుల్": "google",
    "క్రోమ్": "chrome",

    "ఫైర్‌ఫాక్స్": "firefox",
    "ఫైర్‌ఫాక్స్": "firefox",

    "ఎడ్జ్": "edge",

    "నోట్‌ప్యాడ్": "notepad",
    "క్యాలిక్యులేటర్": "calculator",

    "వాట్సాప్": "whatsapp",
    "ఇన్‌స్టాగ్రామ్": "instagram",

    "ఫేస్‌బుక్": "facebook",
    "నెట్‌ఫ్లిక్స్": "netflix",

    "సెట్టింగ్స్": "settings",
    "సెట్టింగ్": "settings",
}


# ============================================================
# SPOKEN / WHISPER VARIANTS
# ============================================================

_SPOKEN_VARIANTS = {

    # Chrome
    "crome": "chrome",
    "chrom": "chrome",
    "krome": "chrome",
    "crom": "chrome",
    "google crome": "google chrome",
    "google chrom": "google chrome",

    # Firefox
    "fire fox": "firefox",
    "mozilla": "firefox",
    "fire": "firefox",

    # Edge
    "ej": "edge",
    "edg": "edge",

    # VS Code
    "v s code": "vs code",
    "vs cod": "vs code",
    "viscode": "vs code",
    "v code": "vs code",
    "vscode": "vs code",
    "vs": "vs code",
    "visual studio code": "vs code",

    # Notepad
    "note pad": "notepad",
    "notpad": "notepad",
    "not pad": "notepad",
    "notepad plus": "notepad++",
    "notepad plus plus": "notepad++",

    # Calculator
    "calculater": "calculator",
    "calc": "calculator",
    "calci": "calculator",
    "kelculator": "calculator",
    "kalculator": "calculator",

    # Word
    "ms word": "word",
    "microsoft word": "word",

    # Excel
    "ms excel": "excel",
    "microsoft excel": "excel",
    "exel": "excel",
    "excell": "excel",

    # PowerPoint
    "power point": "powerpoint",
    "ppt": "powerpoint",
    "ms powerpoint": "powerpoint",
    "ms ppt": "powerpoint",
    "microsoft powerpoint": "powerpoint",
    "pawer point": "powerpoint",

    # WhatsApp
    "whats app": "whatsapp",
    "watsapp": "whatsapp",
    "wats app": "whatsapp",
    "whatsap": "whatsapp",
    "what's app": "whatsapp",
    "watsap": "whatsapp",

    # ChatGPT
    "chat g p t": "chat gpt",
    "chat gp t": "chat gpt",
    "chat gbt": "chat gpt",
    "chatgbt": "chat gpt",
    "chad gpt": "chat gpt",
    "chadgpt": "chat gpt",
    "gpt chat": "chat gpt",
    "gpt": "chat gpt",
    "chat openai": "chat gpt",
    "openai chat": "chat gpt",
    "open ai": "openai",
    "open a i": "openai",

    # Telegram
    "tele gram": "telegram",
    "telgram": "telegram",

    # Discord
    "dis cord": "discord",
    "diskord": "discord",

    # Spotify
    "spotfy": "spotify",
    "sportify": "spotify",
    "spottify": "spotify",

    # VLC
    "vlc player": "vlc",
    "vlc media player": "vlc",

    # Explorer
    "file explorer": "file explorer",
    "my computer": "file explorer",
    "this pc": "file explorer",
    "files": "file explorer",
    "folder": "file explorer",
    "folders": "file explorer",
    "file folder": "file explorer",
    "file manager": "file explorer",

    # Outlook
    "out look": "outlook",
    "ms outlook": "outlook",

    # Teams
    "ms teams": "teams",
    "team": "teams",

    # Slack
    "slak": "slack",

    # Zoom
    "zum": "zoom",
    "zom": "zoom",

    # Paint
    "ms paint": "paint",
    "mspaint": "paint",

    # Terminal
    "cmd": "command prompt",
    "command prompt": "command prompt",
    "terminal": "terminal",
    "windows terminal": "terminal",

    # PowerShell
    "power shell": "powershell",
    "powershell": "powershell",

    # Photoshop
    "photo shop": "photoshop",
    "ps": "photoshop",
    "adobe photoshop": "photoshop",

    # Blender
    "blendar": "blender",

    # OBS
    "obs studio": "obs",
    "o b s": "obs",

    # Steam
    "steem": "steam",

    # Brave
    "brav": "brave",
    "brave browser": "brave",

    # Task Manager
    "task manger": "task manager",
    "taskmanager": "task manager",
    "task maneger": "task manager",

    # Settings
    "setting": "settings",
    "system settings": "settings",

    # Figma
    "figmaa": "figma",

    # Postman
    "post man": "postman",

    # Docker
    "doker": "docker",
    "docker desktop": "docker",

    # Snipping Tool
    "snip": "snipping tool",
    "snipping": "snipping tool",
    "screenshot": "snipping tool",
    "screen shot": "snipping tool",

    # Control Panel
    "control penal": "control panel",

    # OneNote
    "one note": "onenote",

    # Audacity
    "audecity": "audacity",

    # Git Bash
    "git": "git bash",
    "gitbash": "git bash",

    # Android Studio
    "android": "android studio",

    # IntelliJ
    "intelli j": "intellij",
    "intellij idea": "intellij",

    # Sublime
    "sub lime": "sublime",
    "sublime text": "sublime",

    # Camera
    "cam": "camera",
}


# ============================================================
# APPLICATION INDEX
# ============================================================

_app_index: dict[str, str] = {}
_index_ready = threading.Event()


def _add_index_entry(name: str, path: str) -> None:
    """Add an application to the index without overwriting aliases."""
    normalized = _normalize(name)

    if normalized and normalized not in _app_index:
        _app_index[normalized] = path


def _scan_shortcuts() -> None:
    """Scan Start Menu and Desktop shortcuts."""

    roots: list[str] = []

    appdata = os.environ.get("APPDATA", "")
    if appdata:
        roots.append(
            os.path.join(
                appdata,
                r"Microsoft\Windows\Start Menu\Programs",
            )
        )

    programdata = os.environ.get("PROGRAMDATA", "")
    if programdata:
        roots.append(
            os.path.join(
                programdata,
                r"Microsoft\Windows\Start Menu\Programs",
            )
        )

    userprofile = os.environ.get("USERPROFILE", "")
    if userprofile:
        roots.append(os.path.join(userprofile, "Desktop"))
        roots.append(
            os.path.join(
                userprofile,
                "OneDrive",
                "Desktop",
            )
        )

    public = os.environ.get("PUBLIC", "")
    if public:
        roots.append(os.path.join(public, "Desktop"))

    for root in roots:

        if not os.path.isdir(root):
            continue

        try:
            for dirpath, _, filenames in os.walk(root):

                for filename in filenames:

                    if not filename.lower().endswith(
                        (".lnk", ".url")
                    ):
                        continue

                    name = os.path.splitext(filename)[0]
                    full_path = os.path.join(dirpath, filename)

                    _add_index_entry(name, full_path)

        except (PermissionError, OSError):
            continue


def _scan_path_executables() -> None:
    """Scan common program directories for executable files."""

    directories: list[str] = []

    program_files = os.environ.get(
        "PROGRAMFILES",
        r"C:\Program Files",
    )

    program_files_x86 = os.environ.get(
        "PROGRAMFILES(X86)",
        r"C:\Program Files (x86)",
    )

    localappdata = os.environ.get(
        "LOCALAPPDATA",
        "",
    )

    directories.append(program_files)
    directories.append(program_files_x86)

    if localappdata:
        directories.append(
            os.path.join(
                localappdata,
                "Programs",
            )
        )

    for base in directories:

        if not os.path.isdir(base):
            continue

        try:
            entries = os.scandir(base)
        except (PermissionError, OSError):
            continue

        try:

            for entry in entries:

                if not entry.is_dir():
                    continue

                try:

                    for child in os.scandir(entry.path):

                        if not child.is_file():
                            continue

                        if not child.name.lower().endswith(".exe"):
                            continue

                        name = os.path.splitext(
                            child.name
                        )[0]

                        _add_index_entry(
                            name,
                            child.path,
                        )

                except (PermissionError, OSError):
                    continue

        finally:
            try:
                entries.close()
            except Exception:
                pass


def _build_index() -> None:
    """Build the application index in the background."""

    start = time.perf_counter()

    try:
        _scan_shortcuts()
        _scan_path_executables()

        elapsed = (
            time.perf_counter() - start
        ) * 1000

        print(
            f"F.R.I.D.A.Y.: Indexed "
            f"{len(_app_index)} apps "
            f"in {elapsed:.0f}ms."
        )

    except Exception as exc:
        print(
            f"F.R.I.D.A.Y.: App index error: {exc}"
        )

    finally:
        _index_ready.set()


_indexer = threading.Thread(
    target=_build_index,
    name="FRIDAY-AppIndexer",
    daemon=True,
)

_indexer.start()


# ============================================================
# NORMALIZATION
# ============================================================

def _normalize(name: str) -> str:
    """
    Normalize Latin text.

    Native-script names are handled separately because removing
    non-Latin characters would otherwise erase them completely.
    """

    if not name:
        return ""

    text = str(name).strip().lower()

    # Normalize apostrophes.
    text = text.replace("’", "'")

    # Remove punctuation while keeping ASCII letters/numbers.
    text = re.sub(
        r"[^a-z0-9\s+]",
        " ",
        text,
    )

    # Normalize whitespace.
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def _resolve_native_name(name: str) -> str:
    """Resolve a Hindi/Telugu native-script application name."""

    if not name:
        return ""

    raw = name.strip()

    if raw in _NATIVE_APP_NAMES:
        return _NATIVE_APP_NAMES[raw]

    return ""


def _resolve_canonical(name: str) -> str:
    """Resolve native names and spoken variants."""

    native = _resolve_native_name(name)

    if native:
        return native

    normalized = _normalize(name)

    return _SPOKEN_VARIANTS.get(
        normalized,
        normalized,
    )


# ============================================================
# PHONETIC MATCHING
# ============================================================

def _phonetic_key(word: str) -> str:
    """
    Lightweight phonetic normalization.

    Designed for common Whisper mistakes such as:
    crome -> chrome
    exel -> excel
    pawer -> power
    """

    word = word.lower().strip()

    word = re.sub(
        r"(.)\1+",
        r"\1",
        word,
    )

    replacements = (
        ("ph", "f"),
        ("ck", "k"),
        ("gh", "g"),
        ("wh", "w"),
        ("wr", "r"),
        ("kn", "n"),
        ("qu", "kw"),
        ("x", "ks"),
        ("z", "s"),
        ("c", "k"),
        ("j", "g"),
    )

    for old, new in replacements:
        word = word.replace(old, new)

    if len(word) > 1:
        word = (
            word[0]
            + re.sub(
                r"[aeiou]",
                "",
                word[1:],
            )
        )

    return word


def _score_match(
    query: str,
    candidate: str,
) -> float:
    """Calculate a multi-signal fuzzy match score."""

    q = _normalize(query)
    c = _normalize(candidate)

    if not q or not c:
        return 0.0

    if q == c:
        return 1.0

    score = 0.0

    # Prefix.
    if c.startswith(q):
        score = max(
            score,
            0.85 + 0.1 * (
                len(q) / len(c)
            ),
        )

    elif q.startswith(c):
        score = max(
            score,
            0.80 + 0.1 * (
                len(c) / len(q)
            ),
        )

    # Contains.
    if q in c:
        score = max(
            score,
            0.70 + 0.15 * (
                len(q) / len(c)
            ),
        )

    elif c in q:
        score = max(
            score,
            0.65 + 0.10 * (
                len(c) / len(q)
            ),
        )

    # Token overlap.
    q_tokens = set(q.split())
    c_tokens = set(c.split())

    if q_tokens and c_tokens:

        overlap = q_tokens & c_tokens

        if overlap:

            token_score = (
                len(overlap)
                / max(
                    len(q_tokens),
                    len(c_tokens),
                )
            )

            score = max(
                score,
                0.60 + 0.35 * token_score,
            )

    # Whole-string phonetic.
    q_phon = _phonetic_key(q)
    c_phon = _phonetic_key(c)

    if q_phon == c_phon:

        score = max(
            score,
            0.88,
        )

    # Per-token phonetic overlap.
    q_phon_tokens = {
        _phonetic_key(token)
        for token in q.split()
        if len(token) > 1
    }

    c_phon_tokens = {
        _phonetic_key(token)
        for token in c.split()
        if len(token) > 1
    }

    if q_phon_tokens and c_phon_tokens:

        phon_overlap = (
            q_phon_tokens
            & c_phon_tokens
        )

        if phon_overlap:

            phon_score = (
                len(phon_overlap)
                / max(
                    len(q_phon_tokens),
                    len(c_phon_tokens),
                )
            )

            score = max(
                score,
                0.55 + 0.40 * phon_score,
            )

    # Sequence similarity.
    sequence_score = SequenceMatcher(
        None,
        q,
        c,
    ).ratio()

    score = max(
        score,
        sequence_score * 0.90,
    )

    return score


# ============================================================
# BEST APPLICATION MATCH
# ============================================================

def _best_match(
    query: str,
    min_score: float = 0.60,
) -> tuple[
    Optional[str],
    Optional[str],
]:

    canonical = _resolve_canonical(query)

    if not canonical:
        return None, None

    # Exact spoken/canonical alias.
    if canonical in _ALIASES:

        display, executable = _ALIASES[
            canonical
        ]

        return display, executable

    # Exact indexed application.
    if canonical in _app_index:

        return (
            canonical.title(),
            _app_index[canonical],
        )

    best_score = 0.0
    best_display = None
    best_path = None

    # Score aliases first.
    for alias, (
        display,
        executable,
    ) in _ALIASES.items():

        score = _score_match(
            canonical,
            alias,
        )

        if score > best_score:

            best_score = score
            best_display = display
            best_path = executable

    # Score installed applications.
    for app_name, path in _app_index.items():

        score = _score_match(
            canonical,
            app_name,
        )

        if score > best_score:

            best_score = score
            best_display = app_name
            best_path = path

    if (
        best_path
        and best_score >= min_score
    ):

        return (
            best_display.title()
            if best_display
            else canonical.title(),
            best_path,
        )

    return None, None


# ============================================================
# PROCESS RESOLUTION
# ============================================================

def _get_process_name(
    query: str,
    min_score: float = 0.70,
) -> tuple[str, str]:

    canonical = _resolve_canonical(query)

    display, path = _best_match(
        canonical,
        min_score=min_score,
    )

    if display and path:

        normalized_display = _normalize(
            display
        )

        if normalized_display in _PROCESS_NAMES:

            return (
                _PROCESS_NAMES[
                    normalized_display
                ],
                display,
            )

        if normalized_display in _ALIASES:

            return (
                _ALIASES[
                    normalized_display
                ][1],
                display,
            )

        if path.lower().endswith(".exe"):

            return (
                os.path.basename(path),
                display,
            )

    if canonical in _PROCESS_NAMES:

        return (
            _PROCESS_NAMES[canonical],
            canonical.title(),
        )

    if canonical in _ALIASES:

        return (
            _ALIASES[canonical][1],
            _ALIASES[canonical][0],
        )

    if canonical.endswith(".exe"):

        return (
            canonical,
            canonical,
        )

    return (
        canonical + ".exe",
        canonical.title(),
    )


# ============================================================
# OPEN APPLICATION / WEBSITE
# ============================================================

def _start_path(path: str) -> bool:
    """Start a Windows executable, shortcut, or URI."""

    try:

        os.startfile(path)
        return True

    except Exception:

        try:

            subprocess.Popen(
                [path],
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=(
                    _DETACHED_PROCESS
                    | _CREATE_NO_WINDOW
                ),
            )

            return True

        except Exception:

            return False


def _resolve_folder_path(name: str) -> Optional[str]:
    """Resolve a folder/drive request to an existing folder path."""

    if not name:
        return None

    raw = name.strip()

    # Literal path or drive letter, e.g. "C:\\Users\\Admin\\Downloads"
    # or "D:".
    if os.path.isdir(raw):
        return os.path.abspath(raw)

    drive = _DRIVE_LETTER_RE.match(raw)

    if drive:
        root = drive.group(1) + ":\\"

        if os.path.isdir(root):
            return root

    key = _normalize(raw)

    if key.endswith("folder"):
        key = key[: -len("folder")].strip()

    key = key.strip()

    if not key:
        return None

    target = _FOLDERS.get(key)

    if target is None and key.startswith("my "):
        target = _FOLDERS.get(key[3:])

    if not target:
        return None

    user = os.environ.get(
        "USERPROFILE",
        "",
    ) or str(Path.home())

    path = os.path.join(user, target)

    return path if os.path.isdir(path) else None


_FOLDER_LEADS = (
    "open up",
    "open",
    "show me",
    "show",
    "go to",
    "navigate to",
    "take me to",
    "launch",
    "start",
)


def _folder_target(cmd_norm: str) -> Optional[str]:
    """
    Extract a folder path from a normalized command like
    "open downloads", "show my documents folder", or "downloads" alone.
    Returns None unless the phrase actually names a real folder.
    """

    key = cmd_norm

    matched_lead = False

    for lead in _FOLDER_LEADS:

        if key.startswith(lead):
            key = key[len(lead):].strip()
            matched_lead = True
            break

    if not matched_lead and not key.endswith("folder"):
        # Without an open/show verb a short folder name still works
        # ("downloads"), but a full sentence must not be hijacked.
        if _FOLDERS.get(key) is None:
            return None

    key = _strip_filler(key)

    return _resolve_folder_path(key)


def open_app(
    name: str,
) -> tuple[bool, str]:

    """
    Open an application or website.

    Returns:
        (success, display_name_or_error)
    """

    if not name:
        return False, ""

    # Allow the background index a small amount of time.
    _index_ready.wait(
        timeout=0.25
    )

    canonical = _resolve_canonical(name)

    if not canonical:
        return False, name

    # ---------------- Folder / drive / path ----------------

    folder_path = _resolve_folder_path(name)

    if folder_path is not None:

        if _start_path(folder_path):
            return (
                True,
                os.path.basename(
                    folder_path.rstrip("\\/")
                )
                or name,
            )

        return False, name

    # ---------------- Website ----------------

    if canonical in _WEBSITES:

        if _start_path(
            _WEBSITES[canonical]
        ):

            return (
                True,
                canonical.title(),
            )

        return (
            False,
            canonical,
        )

    # ---------------- URI app ----------------

    if canonical in _UWP_APPS:

        uri = _UWP_APPS[canonical]

        if _start_path(uri):

            return (
                True,
                canonical.title(),
            )

    # ---------------- Normal app ----------------

    display, path = _best_match(
        canonical,
        min_score=0.60,
    )

    if not path:

        return (
            False,
            name,
        )

    if _start_path(path):

        return (
            True,
            display or name,
        )

    return (
        False,
        display or name,
    )


# ============================================================
# CLOSE APPLICATION
# ============================================================

_BROWSER_PROCESSES = (
    "msedge.exe",
    "chrome.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
    "vivaldi.exe",
    "iexplore.exe",
    "chromium.exe",
)


def _close_browser_window(
    display: str,
) -> bool:
    """
    Close browser processes whose visible window title contains
    the requested website/application name.
    """

    target = _normalize(display)

    if not target:
        return False

    pids: list[str] = []

    for browser in _BROWSER_PROCESSES:

        try:

            result = subprocess.run(
                [
                    "tasklist",
                    "/V",
                    "/FO",
                    "CSV",
                    "/FI",
                    f"IMAGENAME eq {browser}",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=_CREATE_NO_WINDOW,
            )

        except Exception:
            continue

        if not result.stdout:
            continue

        try:

            reader = csv.reader(
                StringIO(
                    result.stdout
                )
            )

            next(reader, None)

            for row in reader:

                if len(row) <= 8:
                    continue

                pid = row[1]
                window_title = row[8]

                if (
                    "N/A" not in window_title
                    and target in _normalize(
                        window_title
                    )
                ):

                    pids.append(pid)

        except Exception:
            continue

        if pids:
            break

    if not pids:
        return False

    for pid in pids:

        try:

            subprocess.run(
                [
                    "taskkill",
                    "/F",
                    "/PID",
                    pid,
                ],
                capture_output=True,
                timeout=5,
                creationflags=_CREATE_NO_WINDOW,
            )

        except Exception:
            pass

    return True


def close_app(
    name: str,
) -> tuple[bool, str]:

    """
    Close an application.

    Returns:
        (success, display_name_or_error)
    """

    if not name:
        return False, ""

    canonical = _resolve_canonical(name)

    if not canonical:
        return False, name

    process_name, display = _get_process_name(
        canonical,
        min_score=0.70,
    )

    if process_name.lower() in _PROTECTED_PROCESSES:

        return (
            False,
            f"{display} is a system process "
            f"and cannot be closed for safety.",
        )

    # Websites are normally inside a browser.
    if canonical in _WEBSITES:

        if _close_browser_window(display):

            return True, display

    try:

        result = subprocess.run(
            [
                "taskkill",
                "/F",
                "/IM",
                process_name,
            ],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        )

        if result.returncode == 0:

            return True, display

    except Exception:
        pass

    # Fallback for normal applications with a window title.
    try:

        result = subprocess.run(
            [
                "taskkill",
                "/F",
                "/FI",
                f"WINDOWTITLE eq {display}*",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        )

        stdout = (
            result.stdout or ""
        ).lower()

        stderr = (
            result.stderr or ""
        ).lower()

        if (
            result.returncode == 0
            and "no tasks running" not in stdout
            and "not found" not in stderr
        ):

            return True, display

    except Exception:
        pass

    return False, display


# ============================================================
# COMMAND PARSING
# ============================================================

_OPEN_PATTERNS = [

    # English + Indian mixed language.
    r"(.+)\s+(?:open\s+(?:chey|cheyyi|chesuko|kar|karo|kijiye))",
    r"(.+)\s+(?:start\s+(?:chey|cheyyi|kar|karo|kijiye))",

    # Telugu romanized.
    r"(.+)\s+(?:thiyu|tiyyandi|therivu)",
    r"(?:thiyu|tiyyandi|therivu)\s+(.+)",

    # Hindi romanized.
    r"(.+)\s+(?:khol|kholo|kholiye|khol\s+do|khol\s+de|kholna|khol\s+dijiye)",
    r"(.+)\s+(?:chalao|chala\s+do|chala\s+de|chalu\s+karo|chalu\s+kar\s+do)",

    r"(?:khol|kholo|kholiye|khol\s+do|khol\s+de|kholna|khol\s+dijiye)\s+(.+)",
    r"(?:chalao|chala\s+do|chala\s+de|chalu\s+karo|chalu\s+kar\s+do)\s+(.+)",

    # Telugu native.
    r"(.+)\s+(?:ఓపెన్|తెరువు|తియ్యి|స్టార్ట్)\s*(?:చెయ్యి|చేయి|చేయ్)?",
    r"(?:ఓపెన్|తెరువు|తియ్యి|స్టార్ట్)\s*(?:చెయ్యి|చేయి|చేయ్)?\s+(.+)",

    # Hindi native.
    r"(.+)\s+(?:खोल|खोलो|खोलिए|खोल\s+दो|खोल\s+दे|चलाओ|चला\s+दो|शुरू\s+करो)",
    r"(?:खोल|खोलो|खोलिए|खोल\s+दो|खोल\s+दे|चलाओ|चला\s+दो|शुरू\s+करो)\s+(.+)",

    # Simple English LAST.
    r"(?:open|launch|start|run)\s+(.+)",
]


_CLOSE_PATTERNS = [

    # Mixed English.
    r"(.+)\s+(?:close\s+(?:chey|cheyyi|kar|karo|kijiye))",
    r"(.+)\s+(?:band\s+(?:chey|cheyyi|kar|karo|kijiye))",

    # Telugu romanized.
    r"(.+)\s+(?:aapeyyi|apu|aapeyi)",
    r"(?:aapeyyi|apu|aapeyi)\s+(.+)",

    # Hindi romanized.
    r"(.+)\s+(?:band\s+kar|band\s+karo|band\s+kijiye|band\s+kar\s+do|band\s+kardo|bund\s+karo)",
    r"(.+)\s+(?:hatao|hata\s+do|hata\s+de|band\s+kar\s+de)",

    r"(?:band\s+kar|band\s+karo|band\s+kijiye|band\s+kar\s+do|band\s+kardo|bund\s+karo)\s+(.+)",
    r"(?:hatao|hata\s+do|hata\s+de|band\s+kar\s+de)\s+(.+)",

    # Telugu native.
    r"(.+)\s+(?:క్లోజ్|బంద్|ఆపు|ఆపేయి)\s*(?:చెయ్యి|చేయి|చేయ్)?",
    r"(?:క్లోజ్|బంద్|ఆపు|ఆపేయి)\s*(?:చెయ్యి|చేయి|చేయ్)?\s+(.+)",

    # Hindi native.
    r"(.+)\s+(?:बंद\s+करो|बंद\s+कर\s+दो|बंद\s+करदो|बंद\s+कीजिए|हटाओ|हटा\s+दो)",
    r"(?:बंद\s+करो|बंद\s+कर\s+दो|बंद\s+करदो|बंद\s+कीजिए|हटाओ|हटा\s+दो)\s+(.+)",

    # English.
    r"(?:close|quit|exit|kill|end|terminate)\s+(.+)",
    r"(.+)\s+(?:close|quit|band)\b",
]


_OPEN_RE = [
    re.compile(
        pattern,
        re.IGNORECASE,
    )
    for pattern in _OPEN_PATTERNS
]


_CLOSE_RE = [
    re.compile(
        pattern,
        re.IGNORECASE,
    )
    for pattern in _CLOSE_PATTERNS
]


# ============================================================
# FILLER WORDS
# ============================================================

_FILLERS = {
    "the",
    "a",
    "an",
    "my",
    "please",
    "plz",
    "pls",

    "for",
    "me",
    "up",

    "friday",
    "fraiday",
    "fryday",

    # Telugu romanized.
    "ni",
    "lo",
    "ra",
    "le",
    "na",
    "ki",
    "ko",

    # Hindi romanized.
    "ko",
    "ka",
    "ki",
    "ke",
    "se",
    "hai",
    "ho",
    "do",
    "de",
}


def _strip_filler(
    name: str,
) -> str:

    if not name:
        return ""

    words = name.strip().split()

    cleaned = [
        word
        for word in words
        if word.lower()
        not in _FILLERS
    ]

    return (
        " ".join(cleaned).strip()
        if cleaned
        else name.strip()
    )


# ============================================================
# WAKE WORD
# ============================================================

_WAKE_WORD = re.compile(
    r"^(?:hey\s+)?"
    r"(?:friday|fraiday|fry\s*day|fryday)"
    r"(?:[,.\s]+|$)",
    re.IGNORECASE,
)


def parse_app_command(
    text: str,
) -> tuple[
    Optional[str],
    Optional[str],
]:

    """
    Parse an application command.

    Returns:
        ("open", app)
        ("close", app)
        (None, None)
    """

    if not text:
        return None, None

    # Remove wake word.
    command = _WAKE_WORD.sub(
        "",
        text.strip(),
    ).strip()

    if not command:
        return None, None

    # Close first.
    for pattern in _CLOSE_RE:

        match = pattern.search(
            command
        )

        if not match:
            continue

        app = _strip_filler(
            match.group(1)
        )

        if app:
            return "close", app

    # Open.
    for pattern in _OPEN_RE:

        match = pattern.search(
            command
        )

        if not match:
            continue

        app = _strip_filler(
            match.group(1)
        )

        if app:
            return "open", app

    return None, None


# ============================================================
# RESPONSE STATE
# ============================================================

_last_opened_app: Optional[str] = None


_OPEN_ACKS_EN = [
    "Yes, Boss.",
    "Sure, Boss.",
    "On it, Boss.",
    "Right away, Boss.",
    "Done, Boss.",
]


_OPEN_ACKS_TE = [
    "అలాగే బాస్.",
    "చేస్తున్నాను బాస్.",
    "వెంటనే బాస్.",
    "సరే బాస్.",
]


_OPEN_ACKS_HI = [
    "जी बॉस.",
    "अभी करता हूँ बॉस.",
    "जरूर बॉस.",
    "ठीक है बॉस.",
]


# ============================================================
# RESPONSES
# ============================================================

def _open_response(
    app_name: str,
    language: str,
) -> str:

    global _last_opened_app

    success, display = open_app(
        app_name
    )

    if success:

        _last_opened_app = display

        if language == "te":
            return random.choice(
                _OPEN_ACKS_TE
            )

        if language == "hi":
            return random.choice(
                _OPEN_ACKS_HI
            )

        return random.choice(
            _OPEN_ACKS_EN
        )

    if language == "te":

        return (
            f"Sorry Boss, "
            f"{app_name} "
            f"కనుగొనలేకపోయాను."
        )

    if language == "hi":

        return (
            f"Sorry Boss, "
            f"{app_name} "
            f"नहीं मिल रहा."
        )

    return (
        f"Sorry Boss, "
        f"I couldn't find "
        f"{app_name} on this system."
    )


def _close_response(
    app_name: str,
    language: str,
) -> str:

    global _last_opened_app

    success, display = close_app(
        app_name
    )

    if success:

        if (
            _last_opened_app
            and _normalize(
                _last_opened_app
            )
            == _normalize(display)
        ):

            _last_opened_app = None

        if language == "te":

            return (
                f"{display} "
                f"close చేసేశాను Boss."
            )

        if language == "hi":

            return (
                f"{display} "
                f"बंद कर दिया Boss."
            )

        return (
            f"Done, {display} "
            f"has been closed, Boss."
        )

    if language == "te":

        return (
            f"Sorry Boss, "
            f"{display} "
            f"run అవుతున్నట్టు లేదు."
        )

    if language == "hi":

        return (
            f"Sorry Boss, "
            f"{display} "
            f"चल नहीं रहा लगता है."
        )

    return (
        f"Sorry Boss, "
        f"{display} "
        f"doesn't seem to be running."
    )


# ============================================================
# MAIN COMMAND HANDLER
# ============================================================

def handle_app_command(
    command: str,
    language: str = "en",
) -> Optional[str]:

    """
    Handle an application open/close command.

    Returns:
        Spoken response string,
        or None when command is not an app command.
    """

    global _last_opened_app

    if not command:
        return None

    # Normalize only Latin commands here.
    # Native-script commands remain available to the parser.
    cmd_norm = _normalize(command)

    # Contextual close commands.
    context_close = {
        "close it",
        "close that",
        "close this",
        "close",
        "quit it",
        "exit it",
        "kill it",
        "stop it",

        "band karo",
        "band cheyyi",
        "close chey",
        "close cheyyi",
    }

    if cmd_norm in context_close:

        if _last_opened_app:

            return _close_response(
                _last_opened_app,
                language,
            )

        # FRIDAY may have opened a screenshot viewer itself.
        from pc_control import close_screenshot_viewer

        if close_screenshot_viewer():

            if language == "te":

                return (
                    "స్క్రీన్ షాట్ విండో "
                    "close చేసేశాను బాస్."
                )

            if language == "hi":

                return (
                    "स्क्रीनशॉट विंडो "
                    "बंद कर दिया बॉस."
                )

            return (
                "Closed the screenshot "
                "window, Boss."
            )

        if language == "te":

            return (
                "ఏ యాప్ క్లోజ్ చేయాలో "
                "అర్థం కాలేదు బాస్."
            )

        if language == "hi":

            return (
                "समझ नहीं आया कि "
                "कौन सा ऐप बंद करना है बॉस."
            )

        return (
            "I'm not sure which app "
            "you want me to close, Boss."
        )

    # Context follow-ups like "open the first chat" after opening an app.
    if (
        re.search(
            r"open\s+(?:the\s+)?first\s+"
            r"(chat|conversation|message|dm|group)",
            cmd_norm,
        )
        or re.search(
            r"^(?:open|go\s+to)\s+first\s+"
            r"(chat|conversation|message|dm|group)",
            cmd_norm,
        )
    ):

        from pc_control import open_first_chat

        result = open_first_chat(
            _last_opened_app,
            language,
        )

        if result is not None:
            return result

    # Folder / drive commands like "open downloads",
    # "show my documents folder", or "go to videos".
    folder_path = _folder_target(cmd_norm)

    if folder_path is not None:

        if _start_path(folder_path):

            _last_opened_app = os.path.basename(
                folder_path.rstrip("\\/")
            )

            if language == "te":
                return random.choice(_OPEN_ACKS_TE)

            if language == "hi":
                return random.choice(_OPEN_ACKS_HI)

            return random.choice(_OPEN_ACKS_EN)

        if language == "te":

            return (
                f"Sorry Boss, "
                f"{cmd_norm} "
                f"కనుగొనలేకపోయాను."
            )

        if language == "hi":

            return (
                f"Sorry Boss, "
                f"{cmd_norm} "
                f"नहीं मिल रहा."
            )

        return (
            f"Sorry Boss, "
            f"I couldn't find "
            f"{cmd_norm} on this system."
        )

    action, app_name = parse_app_command(
        command
    )

    if action is None or not app_name:
        return None

    normalized_app = _normalize(
        app_name
    )

    # Contextual references.
    context_words = {
        "it",
        "this",
        "that",
        "the app",
        "application",
        "app",
        "computer",
        "pc",
        "system",
        "program",
        "dini",
        "isey",
        "isko",
    }

    if action == "close":

        if normalized_app in context_words:

            if _last_opened_app:

                app_name = _last_opened_app

            else:

                if language == "te":

                    return (
                        "ఏ యాప్ క్లోజ్ చేయాలో "
                        "అర్థం కాలేదు బాస్."
                    )

                if language == "hi":

                    return (
                        "समझ नहीं आया कि "
                        "कौन सा ऐप बंद करना है बॉस."
                    )

                return (
                    "Which application "
                    "should I close, Boss?"
                )

        # "Close the image/picture/photo" closes the screenshot viewer.
        if normalized_app in {
            "screenshot",
            "screen shot",
            "screen shot image",
            "image",
            "image viewer",
            "picture",
            "photo",
            "pic",
            "photo viewer",
            "picture viewer",
            "snapshot",
        }:

            from pc_control import close_screenshot_viewer

            if close_screenshot_viewer():

                if language == "te":

                    return (
                        "స్క్రీన్ షాట్ విండో "
                        "close చేసేశాను బాస్."
                    )

                if language == "hi":

                    return (
                        "स्क्रीनशॉट विंडो "
                        "बंद कर दिया बॉस."
                    )

                return (
                    "Closed the screenshot "
                    "window, Boss."
                )

            if language == "te":

                return (
                    "స్క్రీన్ షాట్ విండో "
                    "కనుగొనలేకపోయాను బాస్."
                )

            if language == "hi":

                return (
                    "स्क्रीनशॉट विंडो "
                    "नहीं मिली बॉस."
                )

            return (
                "I couldn't find the "
                "screenshot window, Boss."
            )

    if action == "open":

        return _open_response(
            app_name,
            language,
        )

    return _close_response(
        app_name,
        language,
    )


# ============================================================
# OPTIONAL DEBUG HELPERS
# ============================================================

def get_index_size() -> int:
    """Return number of indexed applications."""

    return len(_app_index)


def is_index_ready() -> bool:
    """Return whether application indexing is complete."""

    return _index_ready.is_set()


def list_indexed_apps() -> list[str]:
    """Return indexed application names."""

    return sorted(
        _app_index.keys()
    )


__all__ = [
    "open_app",
    "close_app",
    "parse_app_command",
    "handle_app_command",
    "get_index_size",
    "is_index_ready",
    "list_indexed_apps",
]