from core.nlu import NLUAnalyzer, serialize_intent
from core.context import ContextManager

nlu = NLUAnalyzer()
ctx = ContextManager()

# 1. Open Chrome
res1 = nlu.analyze('open chrome', 'en')
ser1 = serialize_intent(res1, ctx)
print("1.", res1.intent, ser1)

# 2. Close it
res2 = nlu.analyze('close it', 'en')
ser2 = serialize_intent(res2, ctx)
print("2.", res2.intent, ser2)

# 3. Telugu code-mix
res3 = nlu.analyze('brightness penchu', 'hi')
ser3 = serialize_intent(res3, ctx)
print("3.", res3.intent, ser3, "Lang:", res3.language)

# 4. Ambiguous
ctx2 = ContextManager()
res4 = nlu.analyze('open it', 'en')
ser4 = serialize_intent(res4, ctx2)
print("4.", res4.intent, ser4, "Ambiguous?", res4.is_ambiguous, "Clarification:", res4.clarification)
