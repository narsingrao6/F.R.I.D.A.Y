import os
import sys
import time
import numpy as np
import speech_recognition as sr

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from voice.audio import mic_hub
from voice import dsp, vad
from voice.speaker_verification import enroll
from voice.speaker import speak, shutdown_audio

def main():
    print("========================================")
    print("   F.R.I.D.A.Y. VOICE ENROLLMENT")
    print("========================================")
    
    speak("Voice enrollment starting.", hint="en")
    speak("Please read the following phrases clearly as they appear on screen.", hint="en")
    
    phrases = [
        "Hey Friday, what time is it in London right now?",
        "Friday, tell me one interesting fact about space.",
        "The meeting was moved to four o'clock.",
        "फ्राइडे मुझे एक मदद चाहिए, आज मौसम कैसा है?",
        "ఫ్రైడే నాకు ఒక సహాయం కావాలి, ఇవాళ వాతావరణం ఎలా ఉంది?"
    ]

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 1.0

    samples_list = []

    for i, phrase in enumerate(phrases):
        print(f"\n[{i+1}/{len(phrases)}] Please say:")
        print(f"  \"{phrase}\"")
        time.sleep(1)
        
        while True:
            with mic_hub.session(recognizer=recognizer, calibrate=0.5) as source:
                print("\nListening...")
                try:
                    audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)
                    samples = dsp.from_audiodata(audio)
                    report = vad.inspect(samples)
                    
                    if not report.ok:
                        print(f"-> Audio rejected ({report.reason}). Please try again.")
                        speak("I didn't quite catch that. Please try again.", hint="en")
                        continue
                        
                    marks = np.flatnonzero(report.active)
                    if marks.size == 0:
                        continue
                        
                    start = marks[0] * dsp.HOP
                    stop = min(marks[-1] * dsp.HOP + dsp.FRAME, samples.size)
                    trimmed = samples[start:stop]
                    
                    if len(trimmed) < dsp.RATE * 1.5:
                        print("-> Audio too short. Please read the full phrase.")
                        speak("That was too short. Please read the full phrase.", hint="en")
                        continue
                        
                    samples_list.append(trimmed)
                    print("-> Sample recorded successfully!")
                    speak(f"Sample {i+1} recorded.", hint="en")
                    break
                    
                except sr.WaitTimeoutError:
                    print("-> Timeout. Please try again.")
                    speak("I didn't hear anything. Please try again.", hint="en")
                except Exception as error:
                    print(f"-> Error: {type(error).__name__}: {error}")
                    speak("Something went wrong. Please try again.", hint="en")

    print("\nProcessing voice profile...")
    enroll(samples_list)
    print("Enrollment complete! F.R.I.D.A.Y. now recognizes your voice.")
    speak("Enrollment complete. I now recognize your voice, Boss.", hint="en")
    
    shutdown_audio()

if __name__ == "__main__":
    main()
