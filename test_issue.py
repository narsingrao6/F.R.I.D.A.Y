text = "time entha ??"
lower_text = text.lower().strip()
print(f"Lower stripped: {lower_text}")
print(f"time entha in lower_text: {"time entha" in lower_text}")

# Also check what analyze returns
from voice.language import analyze
result = analyze("time entha ??")
print(f"analyze result: code={result.code}, style={result.style}")

# Check handle_local_command
from commands import handle_local_command
answer = handle_local_command("time entha ??", "te")
print(f"handle_local_command answer: {answer}")