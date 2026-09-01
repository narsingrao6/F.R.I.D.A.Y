"""
Fast application open / close for F.R.I.D.A.Y. on Windows.

Design:
  1. On import, a background thread indexes every .lnk in the Start Menu,
     Desktop, and common install paths.  The index is a dict mapping
     lowercase app names to their launch paths, so a lookup is O(1).
  2. Opening uses `os.startfile` (instant, non-blocking, no shell window).
  3. Closing uses `taskkill` by image name (forceful, immediate).
  4. Fuzzy matching: if the user says "chrome" we match "Google Chrome",
     if they say "vs code" we match "Visual Studio Code", etc.
  5. Well-known aliases are hardcoded for the apps people actually say
     versus the .lnk name Windows gives them.

The whole module is synchronous and never touches the network.
"""

import os
import re
import glob
import subprocess
import threading
import time
from pathlib import Path
from difflib import SequenceMatcher

# ----------------------------------------------------------- app index

# Pre-built aliases so "chrome" matches even if the shortcut says
# "Google Chrome" and the exe is called "chrome.exe".
_ALIASES = {
    # Browsers
    "chrome":           ("Google Chrome",       "chrome.exe"),
    "google chrome":    ("Google Chrome",       "chrome.exe"),
    "firefox":          ("Mozilla Firefox",     "firefox.exe"),
    "mozilla firefox":  ("Mozilla Firefox",     "firefox.exe"),
    "edge":             ("Microsoft Edge",      "msedge.exe"),
    "microsoft edge":   ("Microsoft Edge",      "msedge.exe"),
    "brave":            ("Brave Browser",       "brave.exe"),
    "opera":            ("Opera",               "opera.exe"),
    "vivaldi":          ("Vivaldi",             "vivaldi.exe"),

    # Development
    "vs code":          ("Visual Studio Code",  "Code.exe"),
    "vscode":           ("Visual Studio Code",  "Code.exe"),
    "visual studio code": ("Visual Studio Code","Code.exe"),
    "visual studio":    ("Visual Studio",       "devenv.exe"),
    "pycharm":          ("PyCharm",             "pycharm64.exe"),
    "intellij":         ("IntelliJ IDEA",       "idea64.exe"),
    "android studio":   ("Android Studio",      "studio64.exe"),
    "sublime":          ("Sublime Text",        "sublime_text.exe"),
    "sublime text":     ("Sublime Text",        "sublime_text.exe"),
    "atom":             ("Atom",                "atom.exe"),
    "notepad++":        ("Notepad++",           "notepad++.exe"),
    "notepad plus plus": ("Notepad++",          "notepad++.exe"),
    "git bash":         ("Git Bash",            "git-bash.exe"),
    "postman":          ("Postman",             "Postman.exe"),
    "docker":           ("Docker Desktop",      "Docker Desktop.exe"),

    # Communication
    "whatsapp":         ("WhatsApp",            "WhatsApp.exe"),
    "telegram":         ("Telegram",            "Telegram.exe"),
    "discord":          ("Discord",             "Discord.exe"),
    "slack":            ("Slack",               "slack.exe"),
    "teams":            ("Microsoft Teams",     "ms-teams.exe"),
    "microsoft teams":  ("Microsoft Teams",     "ms-teams.exe"),
    "zoom":             ("Zoom",                "Zoom.exe"),
    "skype":            ("Skype",               "Skype.exe"),

    # Microsoft Office
    "word":             ("Microsoft Word",      "WINWORD.EXE"),
    "microsoft word":   ("Microsoft Word",      "WINWORD.EXE"),
    "excel":            ("Microsoft Excel",     "EXCEL.EXE"),
    "microsoft excel":  ("Microsoft Excel",     "EXCEL.EXE"),
    "powerpoint":       ("Microsoft PowerPoint","POWERPNT.EXE"),
    "microsoft powerpoint": ("Microsoft PowerPoint", "POWERPNT.EXE"),
    "ppt":              ("Microsoft PowerPoint","POWERPNT.EXE"),
    "outlook":          ("Microsoft Outlook",   "OUTLOOK.EXE"),
    "microsoft outlook": ("Microsoft Outlook",  "OUTLOOK.EXE"),
    "onenote":          ("OneNote",             "ONENOTE.EXE"),
    "access":           ("Microsoft Access",    "MSACCESS.EXE"),

    # Media
    "vlc":              ("VLC Media Player",    "vlc.exe"),
    "vlc player":       ("VLC Media Player",    "vlc.exe"),
    "spotify":          ("Spotify",             "Spotify.exe"),
    "itunes":           ("iTunes",              "iTunes.exe"),
    "obs":              ("OBS Studio",          "obs64.exe"),
    "obs studio":       ("OBS Studio",          "obs64.exe"),
    "audacity":         ("Audacity",            "Audacity.exe"),

    # Utilities
    "notepad":          ("Notepad",             "notepad.exe"),
    "calculator":       ("Calculator",          "calc.exe"),
    "calc":             ("Calculator",          "calc.exe"),
    "paint":            ("Paint",               "mspaint.exe"),
    "snipping tool":    ("Snipping Tool",       "SnippingTool.exe"),
    "task manager":     ("Task Manager",        "Taskmgr.exe"),
    "control panel":    ("Control Panel",       "control.exe"),
    "settings":         ("Settings",            "ms-settings:"),
    "file explorer":    ("File Explorer",       "explorer.exe"),
    "explorer":         ("File Explorer",       "explorer.exe"),
    "cmd":              ("Command Prompt",      "cmd.exe"),
    "command prompt":   ("Command Prompt",      "cmd.exe"),
    "terminal":         ("Windows Terminal",    "wt.exe"),
    "windows terminal": ("Windows Terminal",    "wt.exe"),
    "powershell":       ("PowerShell",          "powershell.exe"),

    # Design / Creative
    "photoshop":        ("Adobe Photoshop",     "Photoshop.exe"),
    "illustrator":      ("Adobe Illustrator",   "Illustrator.exe"),
    "premiere":         ("Adobe Premiere Pro",  "Adobe Premiere Pro.exe"),
    "after effects":    ("Adobe After Effects", "AfterFX.exe"),
    "figma":            ("Figma",               "Figma.exe"),
    "blender":          ("Blender",             "blender.exe"),
    "gimp":             ("GIMP",                "gimp-2.10.exe"),
    "canva":            ("Canva",               "Canva.exe"),

    # Gaming
    "steam":            ("Steam",               "steam.exe"),
    "epic games":       ("Epic Games Launcher", "EpicGamesLauncher.exe"),
    "minecraft":        ("Minecraft Launcher",  "MinecraftLauncher.exe"),

    # System
    "this pc":          ("This PC",             "explorer.exe"),
    "my computer":      ("This PC",             "explorer.exe"),
    "recycle bin":      ("Recycle Bin",          "explorer.exe"),
}

# UWP / Microsoft Store apps opened via protocol URIs or full app IDs.
_UWP_APPS = {
    "calculator":   "calculator:",
    "calc":         "calculator:",
    "settings":     "ms-settings:",
    "store":        "ms-windows-store:",
    "microsoft store": "ms-windows-store:",
    "photos":       "ms-photos:",
    "camera":       "microsoft.windows.camera:",
    "clock":        "ms-clock:",
    "alarms":       "ms-clock:",
    "maps":         "bingmaps:",
    "weather":      "bingweather:",
    "mail":         "outlookmail:",
    "calendar":     "outlookcal:",
    "xbox":         "xbox:",
    "movies":       "mswindowsvideo:",
    "groove":       "mswindowsmusic:",
    "music":        "mswindowsmusic:",
    # Added modern apps that support URI invocation
    "whatsapp":     "whatsapp:",
    "spotify":      "spotify:",
    "telegram":     "telegram:",
    "discord":      "discord:",
    "messenger":    "messenger:",
}

# Process names that don't match the app name at all.
_PROCESS_NAMES = {
    "chrome":           "chrome.exe",
    "google chrome":    "chrome.exe",
    "firefox":          "firefox.exe",
    "edge":             "msedge.exe",
    "microsoft edge":   "msedge.exe",
    "brave":            "brave.exe",
    "vs code":          "Code.exe",
    "vscode":           "Code.exe",
    "visual studio code": "Code.exe",
    "word":             "WINWORD.EXE",
    "microsoft word":   "WINWORD.EXE",
    "excel":            "EXCEL.EXE",
    "microsoft excel":  "EXCEL.EXE",
    "powerpoint":       "POWERPNT.EXE",
    "ppt":              "POWERPNT.EXE",
    "outlook":          "OUTLOOK.EXE",
    "task manager":     "Taskmgr.exe",
    "teams":            "ms-teams.exe",
    "microsoft teams":  "ms-teams.exe",
    "discord":          "Discord.exe",
    "telegram":         "Telegram.exe",
    "whatsapp":         "WhatsApp.exe",
    "spotify":          "Spotify.exe",
    "vlc":              "vlc.exe",
    "steam":            "steam.exe",
    "obs":              "obs64.exe",
    "obs studio":       "obs64.exe",
    "notepad":          "notepad.exe",
    "paint":            "mspaint.exe",
    "calculator":       "calc.exe",
    "calc":             "calc.exe",
    "blender":          "blender.exe",
    "photoshop":        "Photoshop.exe",
    "figma":            "Figma.exe",
    "postman":          "Postman.exe",
    "docker":           "Docker Desktop.exe",
    "slack":            "slack.exe",
    "zoom":             "Zoom.exe",
    "skype":            "Skype.exe",
}

_PROTECTED_PROCESSES = {
    "explorer.exe", "svchost.exe", "csrss.exe", "wininit.exe",
    "winlogon.exe", "lsass.exe", "services.exe", "smss.exe",
    "dwm.exe", "taskhost.exe", "taskhostw.exe", "sihost.exe",
    "shellexperiencehost.exe", "startmenuexperiencehost.exe",
    "searchhost.exe", "runtimebroker.exe", "system",
    "registry", "systemsettings.exe", "ctfmon.exe",
}


# -------------------------------------------------------------- index builder

# The index: lowercase name -> full path to .lnk or .exe
_app_index: dict[str, str] = {}
_index_ready = threading.Event()


def _scan_shortcuts():
    """Walk the Start Menu and Desktop for .lnk files."""
    roots = []

    # Per-user Start Menu
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        roots.append(os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs"))

    # All-users Start Menu
    programdata = os.environ.get("PROGRAMDATA", "")
    if programdata:
        roots.append(os.path.join(programdata, r"Microsoft\Windows\Start Menu\Programs"))

    # Desktop shortcuts
    userprofile = os.environ.get("USERPROFILE", "")
    if userprofile:
        roots.append(os.path.join(userprofile, "Desktop"))
        roots.append(os.path.join(userprofile, "OneDrive", "Desktop"))

    # Public desktop
    public = os.environ.get("PUBLIC", "")
    if public:
        roots.append(os.path.join(public, "Desktop"))

    for root in roots:
        if not os.path.isdir(root):
            continue

        for dirpath, _, filenames in os.walk(root):
            for fname in filenames:
                if fname.lower().endswith((".lnk", ".url")):
                    name = os.path.splitext(fname)[0].lower().strip()
                    full = os.path.join(dirpath, fname)
                    if name and name not in _app_index:
                        _app_index[name] = full


def _scan_path_executables():
    """Add executables from common install directories."""
    dirs = []

    program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    localappdata = os.environ.get("LOCALAPPDATA", "")

    dirs.append(program_files)
    dirs.append(program_files_x86)

    if localappdata:
        dirs.append(os.path.join(localappdata, "Programs"))

    for base in dirs:
        if not os.path.isdir(base):
            continue

        # Only one level deep — we want the main .exe, not every DLL helper.
        for entry in os.scandir(base):
            if not entry.is_dir():
                continue

            try:
                for child in os.scandir(entry.path):
                    if child.is_file() and child.name.lower().endswith(".exe"):
                        name = os.path.splitext(child.name)[0].lower().strip()
                        if name and name not in _app_index:
                            _app_index[name] = child.path
            except (PermissionError, OSError):
                # WindowsApps and similar protected dirs — skip silently.
                continue


def _build_index():
    """Build the app index in a background thread."""
    start = time.perf_counter()

    _scan_shortcuts()
    _scan_path_executables()

    elapsed = (time.perf_counter() - start) * 1000
    print(f"F.R.I.D.A.Y.: Indexed {len(_app_index)} apps in {elapsed:.0f}ms.")

    _index_ready.set()


# Fire off the indexing on import — it runs while the mic warms up.
_indexer = threading.Thread(target=_build_index, daemon=True)
_indexer.start()


# --------------------------------------------------------- smart matching

def _normalize(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", name.lower())).strip()


# Common ways people mispronounce / Whisper mis-transcribes app names.
# Maps spoken form -> canonical form used in _ALIASES.
_SPOKEN_VARIANTS = {
    # Chrome
    "crome": "chrome", "chrom": "chrome", "krome": "chrome",
    "crom": "chrome", "google crome": "google chrome",
    "google chrom": "google chrome",
    # Firefox
    "fire fox": "firefox", "mozilla": "firefox",
    "fire": "firefox",
    # Edge
    "ej": "edge", "edg": "edge",
    # VS Code
    "v s code": "vs code", "vs cod": "vs code", "viscode": "vs code",
    "visual studio code": "vs code", "v code": "vs code",
    "vscode": "vs code", "vs": "vs code",
    # Notepad
    "note pad": "notepad", "notpad": "notepad", "not pad": "notepad",
    "notepad plus": "notepad++", "notepad plus plus": "notepad++",
    # Calculator
    "calculator": "calculator", "calculater": "calculator",
    "calc": "calculator", "calci": "calculator",
    "kelculator": "calculator", "kalculator": "calculator",
    # Word
    "ms word": "word", "microsoft word": "word",
    # Excel
    "ms excel": "excel", "microsoft excel": "excel", "exel": "excel",
    "excell": "excel",
    # PowerPoint
    "power point": "powerpoint", "ppt": "powerpoint",
    "ms powerpoint": "powerpoint", "ms ppt": "powerpoint",
    "microsoft powerpoint": "powerpoint", "pawer point": "powerpoint",
    "powerpoint": "powerpoint",
    # WhatsApp
    "whats app": "whatsapp", "watsapp": "whatsapp", "wats app": "whatsapp",
    "whatsap": "whatsapp", "what's app": "whatsapp", "watsap": "whatsapp",
    # Telegram
    "tele gram": "telegram", "telgram": "telegram",
    # Discord
    "dis cord": "discord", "diskord": "discord",
    # Spotify
    "spotfy": "spotify", "sportify": "spotify", "spottify": "spotify",
    # VLC
    "vlc player": "vlc", "vlc media player": "vlc",
    # Explorer
    "file explorer": "file explorer", "my computer": "file explorer",
    "this pc": "file explorer", "files": "file explorer",
    # Outlook
    "out look": "outlook", "ms outlook": "outlook",
    # Teams
    "ms teams": "teams", "team": "teams",
    # Slack
    "slak": "slack",
    # Zoom
    "zum": "zoom", "zom": "zoom",
    # Paint
    "ms paint": "paint", "mspaint": "paint",
    # Terminal
    "cmd": "command prompt", "command prompt": "command prompt",
    "terminal": "terminal", "windows terminal": "terminal",
    "power shell": "powershell", "powershell": "powershell",
    # Photoshop
    "photo shop": "photoshop", "ps": "photoshop",
    "adobe photoshop": "photoshop",
    # Blender
    "blendar": "blender",
    # OBS
    "obs studio": "obs", "o b s": "obs",
    # Steam
    "steem": "steam",
    # Brave
    "brav": "brave", "brave browser": "brave",
    # Task Manager
    "task manger": "task manager", "taskmanager": "task manager",
    "task maneger": "task manager",
    # Settings
    "setting": "settings", "system settings": "settings",
    # Figma
    "figmaa": "figma",
    # Postman
    "post man": "postman",
    # Docker
    "doker": "docker", "docker desktop": "docker",
    # Snipping Tool
    "snip": "snipping tool", "snipping": "snipping tool",
    "screenshot": "snipping tool", "screen shot": "snipping tool",
    # Control Panel
    "control penal": "control panel",
    # OneNote
    "one note": "onenote",
    # Audacity
    "audacity": "audacity", "audecity": "audacity",
    # Git Bash
    "git": "git bash", "gitbash": "git bash",
    # Android Studio
    "android": "android studio",
    # IntelliJ
    "intelli j": "intellij", "intellij idea": "intellij",
    # Sublime
    "sub lime": "sublime", "sublime text": "sublime",
    # Camera
    "cam": "camera",
}


def _phonetic_key(word: str) -> str:
    """
    Simplified phonetic key — collapses letters that sound alike so
    'crome' and 'chrome', 'exel' and 'excel' produce the same key.
    """
    w = word.lower().strip()
    # Drop silent/doubled letters and map sound-alikes.
    w = re.sub(r"(.)\1+", r"\1", w)         # collapse doubles
    w = w.replace("ph", "f")
    w = w.replace("ck", "k")
    w = w.replace("gh", "g")
    w = w.replace("wh", "w")
    w = w.replace("wr", "r")
    w = w.replace("kn", "n")
    w = w.replace("qu", "kw")
    w = w.replace("x", "ks")
    w = w.replace("z", "s")
    w = w.replace("c", "k")
    w = w.replace("j", "g")
    # Strip vowels except leading.
    if len(w) > 1:
        w = w[0] + re.sub(r"[aeiou]", "", w[1:])
    return w


def _score_match(query: str, candidate: str) -> float:
    """
    Multi-signal scoring: the higher the score, the better the match.

    Signals combined:
      - Exact match / prefix / contains
      - Token overlap (how many words in common)
      - Phonetic key similarity
      - SequenceMatcher ratio
      - Starts-with bonus
    """
    q = _normalize(query)
    c = _normalize(candidate)

    if not q or not c:
        return 0.0

    # Perfect match.
    if q == c:
        return 1.0

    score = 0.0

    # Prefix match: "note" matches "notepad".
    if c.startswith(q):
        score = max(score, 0.85 + 0.1 * (len(q) / len(c)))
    elif q.startswith(c):
        score = max(score, 0.80 + 0.1 * (len(c) / len(q)))

    # Contains match: "pad" in "notepad".
    if q in c:
        score = max(score, 0.7 + 0.15 * (len(q) / len(c)))
    elif c in q:
        score = max(score, 0.65 + 0.1 * (len(c) / len(q)))

    # Token overlap: how many words match.
    q_tokens = set(q.split())
    c_tokens = set(c.split())
    if q_tokens and c_tokens:
        overlap = q_tokens & c_tokens
        if overlap:
            token_score = len(overlap) / max(len(q_tokens), len(c_tokens))
            score = max(score, 0.6 + 0.35 * token_score)

    # Phonetic match: "crome" ≈ "chrome".
    q_phon = _phonetic_key(q)
    c_phon = _phonetic_key(c)
    if q_phon == c_phon:
        score = max(score, 0.88)
    elif q_phon in c_phon or c_phon in q_phon:
        score = max(score, 0.72)

    # Per-token phonetic: "power point" vs "powerpoint".
    q_phon_tokens = {_phonetic_key(t) for t in q.split() if len(t) > 1}
    c_phon_tokens = {_phonetic_key(t) for t in c.split() if len(t) > 1}
    if q_phon_tokens and c_phon_tokens:
        phon_overlap = q_phon_tokens & c_phon_tokens
        if phon_overlap:
            phon_score = len(phon_overlap) / max(len(q_phon_tokens), len(c_phon_tokens))
            score = max(score, 0.55 + 0.4 * phon_score)

    # SequenceMatcher as a fallback.
    seq_score = SequenceMatcher(None, q, c).ratio()
    score = max(score, seq_score * 0.9)

    return score


def _best_match(query: str, min_score: float = 0.60) -> tuple[str | None, str | None]:
    """
    Find the best matching app for `query` using multi-signal scoring.

    Tries, in order:
      1. Spoken-variant canonical lookup  (instant)
      2. Exact alias lookup               (instant)
      3. Exact index lookup               (instant)
      4. Score every alias + indexed app   (fast, <5ms)
    
    Returns (display_name, launch_path) or (None, None).
    """
    q = _normalize(query)

    if not q:
        return None, None

    # 1. Spoken variant -> canonical alias.
    canonical = _SPOKEN_VARIANTS.get(q)
    if canonical and canonical in _ALIASES:
        display, exe = _ALIASES[canonical]
        return display, exe

    # 2. Exact alias hit.
    if q in _ALIASES:
        display, exe = _ALIASES[q]
        return display, exe

    # 3. Exact index hit.
    if q in _app_index:
        return q.title(), _app_index[q]

    # 4. Score everything and pick the best.
    best_score = 0.0
    best_name = None
    best_path = None

    # Score against aliases (higher priority display names).
    for alias, (display, exe) in _ALIASES.items():
        s = _score_match(q, alias)
        if s > best_score:
            best_score = s
            best_name = display
            best_path = exe

    # Score against indexed apps.
    for name, path in _app_index.items():
        s = _score_match(q, name)
        if s > best_score:
            best_score = s
            best_name = name
            best_path = path

    # Threshold: min_score is safe. Valid fuzzy matches like 'crome' vs 'chrome' score 0.8+,
    # while garbage matches like 'youtube' vs 'my computer' score ~0.5.
    if best_score >= min_score:
        return best_name.title() if best_name else None, best_path

    return None, None


def _get_process_name(query: str, min_score: float = 0.60) -> tuple[str, str]:
    """
    Resolve the process image name and display name to kill.
    Returns (process_name, display_name).
    """
    display, path = _best_match(query, min_score=min_score)
    q = _normalize(query)
    
    # If we found a match via smart matching, try to derive the exe name.
    if display and path:
        # Check if the matched display name is in our process overrides.
        canonical = _normalize(display)
        if canonical in _PROCESS_NAMES:
            return _PROCESS_NAMES[canonical], display
        
        if canonical in _ALIASES:
            return _ALIASES[canonical][1], display
            
        # If the path points to an executable, just grab its filename.
        if path.lower().endswith(".exe"):
            import os
            return os.path.basename(path), display

    # Fallback to direct mapping on the raw query.
    if q in _PROCESS_NAMES:
        return _PROCESS_NAMES[q], q.title()

    if q in _ALIASES:
        return _ALIASES[q][1], _ALIASES[q][0]

    if q.endswith(".exe"):
        return query.strip(), query.strip()

    return q + ".exe", query.strip().title()


# --------------------------------------------------------- open / close

_WEBSITES = {
    "youtube":      "https://www.youtube.com",
    "you tube":     "https://www.youtube.com",
    "utube":        "https://www.youtube.com",
    "google":       "https://www.google.com",
    "gmail":        "https://mail.google.com",
    "g mail":       "https://mail.google.com",
    "netflix":      "https://www.netflix.com",
    "net flix":     "https://www.netflix.com",
    "prime video":  "https://www.primevideo.com",
    "prime":        "https://www.primevideo.com",
    "amazon":       "https://www.amazon.com",
    "twitter":      "https://twitter.com",
    "x":            "https://twitter.com",
    "facebook":     "https://www.facebook.com",
    "face book":    "https://www.facebook.com",
    "fb":           "https://www.facebook.com",
    "instagram":    "https://www.instagram.com",
    "insta":        "https://www.instagram.com",
    "insta gram":   "https://www.instagram.com",
    "linkedin":     "https://www.linkedin.com",
    "linked in":    "https://www.linkedin.com",
    "github":       "https://github.com",
    "git hub":      "https://github.com",
    "chat gpt":     "https://chatgpt.com",
    "chatgpt":      "https://chatgpt.com",
    "claude":       "https://claude.ai",
    "reddit":       "https://www.reddit.com",
    "twitch":       "https://www.twitch.tv",
    "wikipedia":    "https://www.wikipedia.org",
    "wiki":         "https://www.wikipedia.org",
    "yahoo":        "https://www.yahoo.com",
    "bing":         "https://www.bing.com",
    "hotstar":      "https://www.hotstar.com",
    "jio cinema":   "https://www.jiocinema.com",
    "flipkart":     "https://www.flipkart.com",
    "zomato":       "https://www.zomato.com",
    "swiggy":       "https://www.swiggy.com",
    "pinterest":    "https://www.pinterest.com",
    "quora":        "https://www.quora.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
}

def open_app(name: str) -> tuple[bool, str]:
    """
    Open an application or website by name.

    Returns (success: bool, display_name_or_error: str).
    """
    # Wait for index, but not forever (250ms max — it's usually done).
    _index_ready.wait(timeout=0.25)

    q = _normalize(name)
    canonical = _SPOKEN_VARIANTS.get(q, q)

    # Websites.
    if canonical in _WEBSITES:
        try:
            os.startfile(_WEBSITES[canonical])
            return True, canonical.title()
        except Exception as e:
            pass

    # UWP / protocol URI apps.
    if canonical in _UWP_APPS:
        uri = _UWP_APPS[canonical]
        try:
            os.startfile(uri)
            return True, canonical.title()
        except Exception as e:
            pass # Fall back to _best_match if protocol fails

    display, path = _best_match(name)

    if not path:
        return False, name

    try:
        # os.startfile is non-blocking and doesn't create a console window.
        if path.endswith(":"):
            # Protocol URI (ms-settings: etc.)
            os.startfile(path)
        elif path.lower().endswith((".lnk", ".url")):
            os.startfile(path)
        elif path.lower().endswith(".exe"):
            # Use startfile for exe too — faster than subprocess.
            os.startfile(path)
        else:
            os.startfile(path)

        return True, display or name

    except Exception as error:
        # Fallback: try subprocess for robustness.
        try:
            subprocess.Popen(
                path,
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NO_WINDOW,
            )
            return True, display or name

        except Exception:
            return False, str(error)


def close_app(name: str) -> tuple[bool, str]:
    """
    Close an application by killing its process.

    Returns (success: bool, display_name_or_error: str).
    """
    proc, display = _get_process_name(name, min_score=0.70)
    
    if proc.lower() in _PROTECTED_PROCESSES:
        return False, f"{display} is a system process and cannot be closed for safety."

    try:
        result = subprocess.run(
            ["taskkill", "/F", "/IM", proc],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        if result.returncode == 0:
            return True, display

        # Process not found — might be a UWP app or named differently.
        # Try via window title as a fallback.
        result2 = subprocess.run(
            ["taskkill", "/F", "/FI", f"WINDOWTITLE eq {display}*"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        # taskkill /FI returns 0 even if it finds no tasks, so we must check stdout.
        if result2.returncode == 0 and "No tasks running" not in result2.stdout and "not found" not in result2.stderr.lower():
            return True, display

        return False, display

    except Exception as error:
        return False, str(error)


# ---------------------------------------------------------- phrase parsing

# Patterns that mean "open an app", in English, Telugu, and Hindi.
_OPEN_PATTERNS = [
    # Multilingual compound verbs first — "chrome open cheyyi" etc.
    # Must precede the simple English "open X" or it eats the verb.
    r"(.+)\s+(?:open\s+(?:chey|cheyyi|chesuko|kar|karo|kijiye))",
    r"(.+)\s+(?:start\s+(?:chey|cheyyi|kar|karo|kijiye))",
    # Telugu (romanized)
    r"(.+)\s+(?:thiyu|tiyyandi|therivu)",
    r"(?:thiyu|tiyyandi|therivu)\s+(.+)",
    # Hindi (romanized)
    r"(.+)\s+(?:khol|kholo|kholiye|chalao|chalu\s+karo)",
    r"(?:khol|kholo|kholiye|chalao|chalu\s+karo)\s+(.+)",
    # Native script triggers
    r"(.+)\s+(?:ఓపెన్|తెరువు|తియ్యి|స్టార్ట్)\s*(?:చెయ్యి|చేయి|చేయ్)?",
    r"(?:ఓపెన్|తెరువు|తియ్యి|స్టార్ట్)\s*(?:చెయ్యి|చేయి|చేయ్)?\s+(.+)",
    r"(.+)\s+(?:खोल|खोलो|खोलिए|चलाओ|शुरू\s+करो)",
    r"(?:खोल|खोलो|खोलिए|चलाओ|शुरू\s+करो)\s+(.+)",
    # English — simple pattern last.
    r"(?:open|launch|start|run)\s+(.+)",
]

_CLOSE_PATTERNS = [
    # Multilingual compound verbs first.
    r"(.+)\s+(?:close\s+(?:chey|cheyyi|kar|karo|kijiye))",
    r"(.+)\s+(?:band\s+(?:chey|cheyyi|kar|karo|kijiye))",
    # Telugu (romanized)
    r"(.+)\s+(?:aapeyyi|apu|aapeyi)",
    r"(?:aapeyyi|apu|aapeyi)\s+(.+)",
    # Hindi (romanized)
    r"(.+)\s+(?:band\s+kar|band\s+karo|band\s+kijiye|bund\s+karo|hatao)",
    r"(?:band\s+kar|band\s+karo|band\s+kijiye|bund\s+karo|hatao)\s+(.+)",
    # Native script triggers
    r"(.+)\s+(?:క్లోజ్|బంద్|ఆపు|ఆపేయి)\s*(?:చెయ్యి|చేయి|చేయ్)?",
    r"(?:క్లోజ్|బంద్|ఆపు|ఆపేయి)\s*(?:చెయ్యి|చేయి|చేయ్)?\s+(.+)",
    r"(.+)\s+(?:बंद\s+करो|बंद\s+कीजिए|हटाओ)",
    r"(?:बंद\s+करो|बंद\s+कीजिए|हटाओ)\s+(.+)",
    # English — simple pattern last.
    r"(?:close|quit|exit|kill|end|terminate)\s+(.+)",
    r"(.+)\s+(?:close|quit|band)\b",
]

# Compile once.
_OPEN_RE = [re.compile(p, re.IGNORECASE) for p in _OPEN_PATTERNS]
_CLOSE_RE = [re.compile(p, re.IGNORECASE) for p in _CLOSE_PATTERNS]


def _strip_filler(name: str) -> str:
    """Remove common filler words from the extracted app name."""
    fillers = {
        "the", "a", "an", "my", "please", "plz", "pls",
        "can you", "could you", "would you", "will you",
        "for me", "for", "me", "up",
        "friday", "fraiday", "friday's",
        # Telugu particles
        "ni", "lo", "ra", "le", "na", "ki", "ko",
        # Hindi particles
        "ko", "ka", "ki", "ke", "se", "hai", "ho",
    }

    words = name.strip().split()
    cleaned = [w for w in words if w.lower() not in fillers]

    return " ".join(cleaned).strip() if cleaned else name.strip()


# Wake-word patterns to strip from the beginning of commands.
_WAKE_WORD = re.compile(
    r"^(?:hey\s+)?(?:friday|fraiday|fry\s*day|fryday)[,.\s]*",
    re.IGNORECASE,
)


def parse_app_command(text: str) -> tuple[str | None, str | None]:
    """
    Parse an open/close app command from natural language text.

    Returns:
        ("open", app_name)  — if it's an open command
        ("close", app_name) — if it's a close command
        (None, None)        — if it's not an app command
    """
    if not text:
        return None, None

    # Strip the wake word so "friday youtube open chey" becomes
    # "youtube open chey".
    t = _WAKE_WORD.sub("", text).strip()

    # Try close first (so "close chrome" isn't matched by "open" patterns
    # that would extract "close chrome" as the app name).
    for pat in _CLOSE_RE:
        m = pat.search(t)
        if m:
            app = _strip_filler(m.group(1))
            if app:
                return "close", app

    for pat in _OPEN_RE:
        m = pat.search(t)
        if m:
            app = _strip_filler(m.group(1))
            if app:
                return "open", app

    return None, None


import random

_last_opened_app = None

# ------------------------------------------------------------ responses

_OPEN_ACKS_EN = ["Yes, Boss.", "Sure, Boss.", "On it, Boss.", "Right away, Boss.", "Done, Boss."]
_OPEN_ACKS_TE = ["అలాగే బాస్.", "చేస్తున్నాను బాస్.", "వెంటనే బాస్.", "సరే బాస్."]
_OPEN_ACKS_HI = ["जी बॉस.", "अभी करता हूँ बॉस.", "जरूर बॉस.", "ठीक है बॉस."]

def _open_response(app_name: str, language: str) -> str:
    """Execute the open and return a spoken response."""
    global _last_opened_app
    success, display = open_app(app_name)

    if success:
        _last_opened_app = display
        if language == "te":
            return random.choice(_OPEN_ACKS_TE)
        if language == "hi":
            return random.choice(_OPEN_ACKS_HI)
        return random.choice(_OPEN_ACKS_EN)

    if language == "te":
        return f"Sorry Boss, {app_name} కనుగొనలేకపోయాను."
    if language == "hi":
        return f"Sorry Boss, {app_name} नहीं मिल रहा."
    return f"Sorry Boss, I couldn't find {app_name} on this system."


def _close_response(app_name: str, language: str) -> str:
    """Execute the close and return a spoken response."""
    global _last_opened_app
    success, display = close_app(app_name)

    if success:
        if _last_opened_app and _normalize(_last_opened_app) == _normalize(display):
            _last_opened_app = None
            
        if language == "te":
            return f"{display} close చేసేశాను Boss."
        if language == "hi":
            return f"{display} बंद कर दिया Boss."
        return f"Done, {display} has been closed, Boss."

    if language == "te":
        return f"Sorry Boss, {display} run అవుతున్నట్టు లేదు."
    if language == "hi":
        return f"Sorry Boss, {display} चल नहीं रहा लगता है."
    return f"Sorry Boss, {display} doesn't seem to be running."


def handle_app_command(command: str, language: str = "en") -> str | None:
    """
    Try to handle an app open/close command.

    Returns a spoken response string, or None if this isn't an app command.
    """
    global _last_opened_app
    
    # Check for standalone "close it" type phrases before doing full parse
    cmd_norm = _normalize(command)
    context_close = {"close it", "close that", "close this", "close", "quit it", "exit it", "kill it", "stop it", "band karo", "band cheyyi", "close chey", "close cheyyi"}
    
    if cmd_norm in context_close:
        if _last_opened_app:
            return _close_response(_last_opened_app, language)
        else:
            if language == "te":
                return "ఏ యాప్ క్లోజ్ చేయాలో అర్థం కాలేదు బాస్."
            if language == "hi":
                return "समझ नहीं आया कि कौन सा ऐप बंद करना है बॉस."
            return "I'm not sure which app you want me to close, Boss."
            
    action, app_name = parse_app_command(command)

    if action is None:
        return None

    # Handle context pronoun ("open chrome" -> "close it")
    if action == "close":
        if _normalize(app_name) in ("application", "app", "computer", "pc", "system", "program"):
            if _last_opened_app:
                app_name = _last_opened_app
            else:
                if language == "te": return "ఏ యాప్ క్లోజ్ చేయాలో అర్థం కాలేదు బాస్."
                if language == "hi": return "समझ नहीं आया कि कौन सा ऐप बंद करना है बॉस."
                return "Which application should I close, Boss?"

        if app_name in ("it", "this", "that", "the app", "dini", "isey", "isko"):
            if _last_opened_app:
                app_name = _last_opened_app
            else:
                if language == "te":
                    return "ఏ యాప్ క్లోజ్ చేయాలో అర్థం కాలేదు బాస్."
                if language == "hi":
                    return "समझ नहीं आया कि कौन सा ऐप बंद करना है बॉस."
                return "I'm not sure which app you want me to close, Boss."

    if action == "open":
        return _open_response(app_name, language)

    return _close_response(app_name, language)
