import string
text = "time entha ??"
lower_text = text.lower().strip()
old_text = lower_text
new_text = lower_text.translate(str.maketrans("", "", string.punctuation))
print(f"Original: {lower_text}")
print(f"After strip punctuation: {new_text}")
print(f'"time entha" in old_text: {"time entha" in old_text}')
print(f'"time entha" in new_text: {"time entha" in new_text}')