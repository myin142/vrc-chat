import threading
import speech_recognition as sr
from speech_recognition import UnknownValueError, WaitTimeoutError, AudioData
import queue

# Initialize recognizer class (for recognizing the speech)
r = sr.Recognizer()
audio_queue = queue.Queue()

def collect_audio():
    mic = sr.Microphone()
    print("[AudioThread] Starting audio collection!")
    did = mic.get_pyaudio().PyAudio().get_default_input_device_info()
    print("[AudioThread] Using", did.get('name'), "as Microphone!")
    with mic as source:
        audio_buf = None
        buf_size = 0
        while True:
            audio = None
            try:
                audio = r.listen(source, phrase_time_limit=1, timeout=0.1)
            except WaitTimeoutError:
                if audio_buf is not None:
                    audio_queue.put((audio_buf, True))
                    audio_buf = None
                    buf_size = 0
                continue

            if audio is not None:
                if audio_buf is None:
                    audio_buf = audio
                else:
                    buf_size += 1
                    if buf_size > 10:
                        audio_buf = audio
                        buf_size = 0
                    else:
                        audio_buf = AudioData(audio_buf.frame_data + audio.frame_data, audio.sample_rate, audio.sample_width)

                audio_queue.put((audio_buf, False))

cat = threading.Thread(target=collect_audio)
cat.start()

while True:
    ad, final = audio_queue.get()
    print("Received audio data, final:", final)
    print(r.recognize_google(ad, language = 'en-US', show_all = True))

with sr.Microphone() as mic:
    print("Please speak something...")
    r.adjust_for_ambient_noise(mic, duration=1)  # Adjust for ambient noise
    audio_data = r.listen(mic, timeout=10)  # Listen for the first 5 seconds

# try:
#     print("\nRecognized Text:")
#     text = r.recognize_google(audio_data)
#     print(text)

# except sr.UnknownValueError:
#     print("Sorry, could not understand the audio.")
# except sr.RequestError:
#     print("Could not connect to Google API.")
