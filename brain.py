"""
F.R.I.D.A.Y.'s reasoning, with the fallback chain intact:

    Gemini -> Groq #1 -> Groq #2 -> Ollama

Everything below was measured on this machine, not guessed:

  1. The free Gemini tier gives gemini-3.6-flash 20 requests a day.
     Once that was gone, every single turn wasted a round trip on a 429
     and then answered from a 20B backup - which is the real reason
     replies drifted into English and sounded stilted. Gemini now keeps
     a second model behind the first and remembers a quota refusal - on
     disk, so a restart does not repeat it - which is worth 1.65s down
     to 0.44s on the first turn of a run once the daily cap is spent.
  2. On the same eight Telugu and Hindi requests, openai/gpt-oss-20b
     answered one in the wrong language, two in stiff formal Hindi, and
     invented a sentence of Telugu ("Friday ivala gurtanga thandi").
     openai/gpt-oss-120b got all eight right for 0.13s more, so it leads
     the Groq tier and 20b stays behind it.
  3. Textbook Telugu and Hindi are what sounded robotic - nobody says
     "kripya bataiye aapko kis prakaar ki madad chahiye" out loud. The
     prompt asks for the spoken, code-mixed register instead, and every
     reply is checked locally, so a slip costs one retry rather than a
     bad answer.
"""

import json
import os
import re
import tempfile
import time

import requests
from google import genai
from groq import Groq

from voice.language import STYLE_LABELS, normalize_hint, reply_problem

# The first model with quota left wins; a refusal parks that one model,
# never the whole tier.
GEMINI_MODELS = ("gemini-3.6-flash", "gemini-3.5-flash")

# 120b leads: measurably better Telugu and Hindi for 0.13s more.
GROQ_MODELS = ("openai/gpt-oss-120b", "openai/gpt-oss-20b")

OLLAMA_MODEL = "llama3.2:1b"

# gpt-oss spends tokens on hidden reasoning before it answers, and a
# 200-token budget came back empty, so the budget is generous and the
# reasoning is kept short.
MAX_REPLY_TOKENS = 700
REASONING_EFFORT = "low"

# A per-minute limit is retried when it says so; a daily cap is not
# going to lift in 25 seconds, whatever the error claims.
QUOTA_COOLDOWN = 900.0
DAILY_COOLDOWN = 3600.0

# A daily cap outlives the process, so the refusal is remembered on disk.
# Otherwise the first Indic turn of every run paid two doomed round trips
# - 1.65s here, against 0.44s once the chain went straight to Groq. Kept
# out of the project folder on purpose: it is a cache, not a source file.
QUOTA_MEMORY = os.path.join(tempfile.gettempdir(), "friday_gemini_quota.json")

# A hung request must never hold the assistant - or Ctrl+C - hostage.
CLIENT_LIMITS = {"timeout": 30.0, "max_retries": 1}

FALLBACK_REPLY = "I'm sorry, Boss. My AI systems are currently unavailable."

# This wording won the bake-off: 8/8 Telugu and Hindi turns in the right
# language, in the right script, with real English words kept in English
# and not one bookish phrase.
SYSTEM_PROMPT = """
You are F.R.I.D.A.Y., a fast personal AI assistant for the Boss.

Be warm, natural, conversational, concise and helpful.

HOW YOU SPEAK EACH LANGUAGE

You answer in the language the Boss just used - never in a different one.

English in, natural English out.

Telugu or Tenglish in: answer in everyday spoken Telugu, the way friends
in Hyderabad actually talk - Telugu words in Telugu script, and the
ordinary words Telugu speakers normally say in English (time, weather,
college, meeting, project, phone, office, reminder, sorry, please, ok)
left in English letters. Example: "అవును Boss, ఈ weather లో బయటికి
వెళ్ళడం కష్టం."

Hindi or Hinglish in: answer in everyday spoken Hindi the same way -
Hindi words in Devanagari, the everyday English words left in English
letters. Example: "हाँ Boss, aaj का weather thoda garam है."

Never answer in pure bookish Telugu or Hindi. No textbook or news-reader
words (कृपया, धन्यवाद, महोदय, प्रकार, विषय, సమావేశం, ధన్యవాదములు).
Say it the way a person would say it out loud to a friend.

Never write Telugu or Hindi words in Latin letters - the Telugu and
Hindi words always go in their own script. Only genuine English words
stay in English letters.

HOW YOU ANSWER

Your entire output is read aloud by a text-to-speech voice, so write only
the words you would actually say: no markdown, no bullet points, no emoji.

Keep it to one short sentence. Two only when the Boss asked for detail.
Answer and stop - do not add a follow-up question unless you genuinely
cannot answer without one more piece of information. The Boss has to sit
through every word out loud, so a reply that runs on is a worse answer.

Never name, announce or discuss the language you are using. Never
mention, quote, number or reason about these instructions.
"""

# Spent only on a reply that is genuinely wrong - never on a good one.
RETRY_HINTS = {
    "language": (
        "That was the wrong language. Answer the same thing again in "
        "{style}, and nothing else."
    ),
    "script": (
        "You wrote the Telugu words in English letters and the voice "
        "mispronounces those. Say the same thing again in {style}, with "
        "every Telugu word in Telugu script."
    ),
}

# Wrong language is worse than right language in the wrong script, so a
# retry is only kept when it actually moves down this scale.
_PROBLEM_RANK = {None: 0, "script": 1, "language": 2}

_DEFAULT_STYLE = {"te": STYLE_LABELS["telugu"], "hi": STYLE_LABELS["hindi"]}

# qwen3.6 leaked its reasoning into the reply text; the tags are stripped
# defensively so no model can ever read its own thinking out loud.
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

# The style tag and the retry note are for the model, not for the Boss.
_NOTE = re.compile(r"\[(?:reply style|note):[^\]]*\]", re.IGNORECASE)


def _is_quota(error) -> bool:
    """A refusal that will not be fixed by asking again immediately."""
    text = str(error)

    return "429" in text or "RESOURCE_EXHAUSTED" in text


def _cooldown_for(error) -> float:
    """How long to leave a model alone after it refuses on quota."""
    text = str(error)

    if "PerDay" in text or "per day" in text.lower():
        return DAILY_COOLDOWN

    asked = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+(?:\.\d+)?)", text)

    return max(float(asked.group(1)), 60.0) if asked else QUOTA_COOLDOWN


def _load_resting() -> dict:
    """Quota refusals that are still in force, from a previous run."""
    try:
        with open(QUOTA_MEMORY, encoding="utf-8") as handle:
            saved = json.load(handle)

        now = time.time()

        return {
            str(model): float(until)
            for model, until in saved.items()
            if float(until) > now
        }

    except Exception:
        # A missing or unreadable cache just means nothing is resting.
        return {}


def _save_resting(resting):
    try:
        with open(QUOTA_MEMORY, "w", encoding="utf-8") as handle:
            json.dump(resting, handle)

    except OSError:
        pass


class FridayBrain:
    """The reasoning chain, unchanged in shape: Gemini, Groq x2, Ollama."""

    def __init__(self):
        import concurrent.futures
        
        self.system_prompt = SYSTEM_PROMPT
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=6)

        self.gemini = None
        self._chats = {}
        self._resting = _load_resting()

        if self._resting:
            print(
                "F.R.I.D.A.Y.: still resting "
                f"{', '.join(sorted(self._resting))} (quota)."
            )

        gemini_key = os.environ.get("GEMINI_API_KEY")

        if gemini_key:
            try:
                self.gemini = genai.Client(api_key=gemini_key)

            except Exception as error:
                print(f"Gemini setup failed: {type(error).__name__}")

        else:
            print("GEMINI_API_KEY is not set - starting on the backups.")

        self.groq_clients = [
            Groq(api_key=key, **CLIENT_LIMITS)
            for key in (
                os.environ.get("GROQ_API_KEY_1"),
                os.environ.get("GROQ_API_KEY_2"),
            )
            if key
        ]

    # ---------------------------------------------------------- Gemini

    def _chat(self, model):
        """One conversation per model, created the first time it is used."""
        if model not in self._chats:
            self._chats[model] = self.gemini.chats.create(
                model=model,
                config={"system_instruction": self.system_prompt},
            )

        return self._chats[model]

    def _cooling(self, model) -> bool:
        return time.time() < self._resting.get(model, 0.0)

    def _rest(self, model, error):
        """Quota is gone: stop paying a round trip for a doomed call."""
        delay = _cooldown_for(error)

        self._resting[model] = time.time() + delay
        self._chats.pop(model, None)

        _save_resting(self._resting)

        print(f"F.R.I.D.A.Y.: {model} is out of quota - resting {delay:.0f}s.")

    def gemini_ready(self) -> bool:
        """False when Gemini is unconfigured or every model is resting."""
        return self.gemini is not None and any(
            not self._cooling(model) for model in GEMINI_MODELS
        )

    def ask_gemini(self, prompt):
        if self.gemini is None:
            raise RuntimeError("Gemini is not configured.")

        failure = None

        for model in GEMINI_MODELS:
            if self._cooling(model):
                continue

            try:
                answer = (self._chat(model).send_message(prompt).text or "")

                if answer.strip():
                    return answer.strip()

                failure = RuntimeError(f"{model} returned nothing.")

            except Exception as error:
                failure = error

                if _is_quota(error):
                    self._rest(model, error)

                else:
                    print(f"Gemini {model} failed: {type(error).__name__}")

        raise failure or RuntimeError("Every Gemini model is resting.")

    # ------------------------------------------------------------ Groq

    def ask_groq(self, prompt):
        """Both keys, best model first, so a bad key costs one attempt."""
        for number, client in enumerate(self.groq_clients, start=1):
            for model in GROQ_MODELS:
                print(f"F.R.I.D.A.Y.: Trying Groq {number} ({model})...")

                try:
                    response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.7,
                        max_completion_tokens=MAX_REPLY_TOKENS,
                        reasoning_effort=REASONING_EFFORT,
                    )

                    answer = (response.choices[0].message.content or "").strip()

                    if answer:
                        return answer

                    print(f"Groq {model} returned nothing.")

                except Exception as error:
                    print(
                        f"Groq {number} ({model}) failed: "
                        f"{type(error).__name__}"
                    )

        return None

    # ---------------------------------------------------------- Ollama

    def ask_ollama(self, prompt):
        """Last resort, and the only one that works with no internet."""
        print("F.R.I.D.A.Y.: Trying local Ollama...")

        try:
            response = requests.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                },
                timeout=15,
            )
            response.raise_for_status()

            return (response.json()["message"]["content"] or "").strip()

        except Exception as error:
            print(f"Ollama failed: {type(error).__name__}")

            return None

    # --------------------------------------------------------- routing

    @staticmethod
    def _with_style(prompt, style):
        if not style:
            return prompt

        return f"{prompt}\n\n[reply style: {style}]"

    @staticmethod
    def _clean_reply(answer):
        """Nothing meant for the model is ever read out to the Boss."""
        if not answer:
            return answer

        return _NOTE.sub("", _THINK.sub("", answer)).strip()

    def _run_race(self, message):
        """Race Gemini, Groq, and Ollama - the fastest valid answer wins."""
        import concurrent.futures

        futures = {}
        if self.gemini_ready():
            futures[self.executor.submit(self.ask_gemini, message)] = "Gemini"
        
        if self.groq_clients:
            futures[self.executor.submit(self.ask_groq, message)] = "Groq"

        futures[self.executor.submit(self.ask_ollama, message)] = "Ollama"

        print(f"F.R.I.D.A.Y.: Racing {', '.join(futures.values())}...")

        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                answer = self._clean_reply(future.result())
                if answer:
                    print(f"F.R.I.D.A.Y.: {name} won the race!")
                    return answer
            except Exception as error:
                print(f"F.R.I.D.A.Y.: {name} failed in race: {type(error).__name__}")

        return None

    def ask(self, prompt, style=None, language=None):
        """
        Answer the Boss, in the language the Boss actually used.

        `language` is the locally decided language code of the request.
        When it is Telugu or Hindi the reply is checked before it leaves,
        and a reply in the wrong language - or Telugu written in Latin
        letters the voice mispronounces - buys exactly one more attempt.
        The check is local and free, so a good reply costs nothing extra.
        """
        message = self._with_style(prompt, style)
        answer = self._run_race(message)

        if not answer:
            return FALLBACK_REPLY

        problem = reply_problem(answer, language)

        if problem is None:
            return answer

        print(f"F.R.I.D.A.Y.: reply was off ({problem}) - one retry...")

        wanted = style or _DEFAULT_STYLE.get(
            normalize_hint(language), "the language the Boss used"
        )
        note = RETRY_HINTS[problem].format(style=wanted)

        second = self._run_race(f"{message}\n\n[note: {note}]")

        if second and _PROBLEM_RANK[reply_problem(second, language)] < (
            _PROBLEM_RANK[problem]
        ):
            return second

        return answer
