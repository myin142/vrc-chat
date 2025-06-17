# https://github.com/ikbenjepapa/VRC-transapp
# https://github.com/cyberkitsune/vrc-osc-scripts

import os
import time
from dotenv import load_dotenv
from pythonosc import osc_server, udp_client
from pythonosc.dispatcher import Dispatcher
from tkinter import Tk, Text, Label, Button, ttk, StringVar
import speech_recognition as sr
import threading
import datetime
from translator import DeepLTranslator

load_dotenv()
deepl = DeepLTranslator(os.getenv('DEEPL_API'))

LANGUAGES = [
    'English (US)',
    'Japanese',
    'Chinese (Mandarin)',
    'Korean'
]

LANGUAGE_TEXT = [
    'Typing in English now...',
    '今は日本語を使ってます...',
    '现在用中文写...',
    '한국어...'
]

TRANSLATE_TEXT = [
    'Translating to English...',
    '日本語に翻訳してる...',
    '翻译到中文...',
    '한국어로 번역하세요...'
]

TOGGLE_THRESHOLD = 0.5
VRCHAT_IP = "127.0.0.1"
VRCHAT_PORT = 9000
LISTEN_PORT = 9001
MIC_TIMEOUT = 6
osc_client = udp_client.SimpleUDPClient(VRCHAT_IP, VRCHAT_PORT)

dispatcher = Dispatcher()
server = osc_server.ThreadingOSCUDPServer((VRCHAT_IP, LISTEN_PORT), dispatcher)

language_map = {
    "Chinese (Mandarin)": "zh-CN",
    "English (US)": "en-US",
    "Japanese": "ja-JP",
    "Korean": "ko-KR",
}

recognizer = sr.Recognizer()
last_request_time = datetime.datetime.now() - datetime.timedelta(seconds=5)
received_mute = False

def check_limit():
    """
    Check if the request count exceeds the maximum allowed.
    """
    global last_request_time

    now = datetime.datetime.now()
    diff_in_sec = (now - last_request_time).total_seconds()
    if diff_in_sec < 5:
        return False

    last_request_time = datetime.datetime.now()
    return True

def transcribe_audio(language_code, mic_label):
    """
    Capture and transcribe audio input using SpeechRecognition with a specified language.
    """
    mic_label.config(text="Listening... Speak now!", fg="red")
    mic_label.update()
    try:
        audio = recognizer.listen(source, timeout=MIC_TIMEOUT)
        text = recognizer.recognize_google(audio, language=language_code)
        mic_label.config(text="Microphone ready.", fg="green")
        return text
    except sr.WaitTimeoutError:
        mic_label.config(text="No speech detected. Try again.", fg="orange")
        return None
    except sr.UnknownValueError:
        mic_label.config(text="Could not understand audio.", fg="orange")
        return None
    except Exception as e:
        mic_label.config(text=f"Error: {e}", fg="red")
        return None

def translate_text(text, input_language, target_language):
    """
    Translate text using OpenAI's ChatGPT.
    """
    if not check_limit():
        return "Testing limit reached. Contact the developer for more access."
    try:
        return deepl.translate(input_language, target_language, text)
    except Exception as e:
        print(f"Error during translation: {e}")
        return None

def send_to_chatbox(output_text):
    """
    Send text to VRChat Chatbox via OSC.
    """
    try:
        if not output_text:
            return
        osc_client.send_message("/chatbox/input", [output_text, True])
    except Exception as e:
        print(f"Error sending to Chatbox: {e}")

def start_translation(input_language, target_language, input_text_box, result_label, mic_label, mic=False):
    """
    Start the translation process.
    """
    osc_client.send_message("/chatbox/typing", True)

    if mic:
        input_lang_code = language_map.get(input_language)
        input_text = transcribe_audio(input_lang_code, mic_label)
        if not input_text:
            return
    else:
        input_text = input_text_box.get("1.0", "end").strip()

    if not input_text:
        result_label.config(text="No input provided.")
        osc_client.send_message("/chatbox/typing", False)
        return
    
    send_translation(input_text, input_language, target_language, result_label)

def send_translation(input_text, input_language, target_language, result_label):
    target_lang_code = language_map.get(target_language)
    input_lang_code = language_map.get(input_language)

    if input_lang_code == target_lang_code:
        output_text = f"{input_text}"
        result_label.config(text=output_text, fg="blue")
        send_to_chatbox(output_text)
    else:
        translated_text = translate_text(input_text, input_lang_code, target_lang_code)
        if translated_text:
            output_text = f"{translated_text} ({input_text})"
            result_label.config(text=output_text, fg="blue")
            send_to_chatbox(output_text)
        else:
            result_label.config(text="Translation failed.", fg="red")

    osc_client.send_message("/chatbox/typing", False)

def reset_mute():
    global received_mute

    time.sleep(TOGGLE_THRESHOLD)
    received_mute = False
    print("Resetting mute state.")

def handle_mute(url, is_mute):
    global received_mute
    print(f"Received {url}: {is_mute}")

    if not is_mute and not received_mute:
        received_mute = True
        threading.Thread(target=reset_mute).start()
    elif is_mute and received_mute:
        received_mute = False
        threading.Thread(target=start_translation, args=(
                input_language_var.get(),
                target_language_var.get(),
                input_text_box,
                result_label,
                mic_label,
                True
            )).start()

def set_input_language(value):
    if value < 0 or value >= len(LANGUAGES): return
    print(f"Setting input language to {value}")
    lang = LANGUAGES[value]
    input_language_combo.set(lang)
    target_language_combo.set(lang)
    send_to_chatbox(f'[CHAT] {LANGUAGE_TEXT[value]}')

def set_translate_language(value):
    if value < 0 or value >= len(LANGUAGES): return
    print(f"Setting translate language to {value}")
    lang = LANGUAGES[value]
    target_language_combo.set(lang)
    send_to_chatbox(f'[CHAT] {TRANSLATE_TEXT[value]}')


dispatcher.map("/avatar/parameters/MuteSelf", handle_mute)
dispatcher.map("/avatar/parameters/Language", lambda url, value: set_input_language(value-1))
dispatcher.map("/avatar/parameters/Translate", lambda url, value: set_translate_language(value-1))

print("Serving on {}".format(server.server_address))
server_thread = threading.Thread(target=lambda: server.serve_forever())
server_thread.start()

with sr.Microphone() as source:
    root = Tk()
    root.title("VRChat Translator")
    root.geometry("600x700")
    root.configure(bg="#f5f5f5")

    style = ttk.Style()
    style.configure("TLabel", background="#f5f5f5", font=("Helvetica", 12))
    style.configure("TButton", font=("Helvetica", 12), padding=5)
    style.configure("TCombobox", padding=5)

    # Input Language Selection
    Label(root, text="Select Input Language:", bg="#f5f5f5", font=("Helvetica", 14)).pack(pady=10)
    input_language_var = StringVar()
    input_language_combo = ttk.Combobox(root, textvariable=input_language_var, values=list(language_map.keys()), state="readonly")
    input_language_combo.bind("<<ComboboxSelected>>", lambda e: target_language_combo.set(input_language_var.get()))
    input_language_combo.set("English (US)")
    input_language_combo.pack(pady=5)

    # Target Language Selection
    Label(root, text="Select Target Language:", bg="#f5f5f5", font=("Helvetica", 14)).pack(pady=10)
    target_language_var = StringVar()
    target_language_combo = ttk.Combobox(root, textvariable=target_language_var, values=list(language_map.keys()), state="readonly")
    target_language_combo.set("English (US)")
    target_language_combo.pack(pady=5)

    # Input Text Box
    Label(root, text="Enter Text (or leave blank and use microphone):", bg="#f5f5f5", font=("Helvetica", 14)).pack(pady=10)
    input_text_box = Text(root, height=6, width=50, font=("Helvetica", 12))
    input_text_box.pack(pady=10)

    # Microphone Status Label
    mic_label = Label(root, text="Microphone ready.", bg="#f5f5f5", fg="green", font=("Helvetica", 12))
    mic_label.pack(pady=5)

    # Buttons for Translate and Microphone
    button_frame = ttk.Frame(root)
    button_frame.pack(pady=20)

    translate_button = ttk.Button(button_frame, text="Translate Text", command=lambda: start_translation(
        input_language_var.get(),
        target_language_var.get(),
        input_text_box,
        result_label,
        mic_label,
    ))
    translate_button.pack(side="left", padx=10)

    mic_button = ttk.Button(button_frame, text="Use Microphone", command=lambda: threading.Thread(target=start_translation, args=(
        input_language_var.get(),
        target_language_var.get(),
        input_text_box,
        result_label,
        mic_label,
        True
    )).start())
    mic_button.pack(side="right", padx=10)

    # Result Label
    result_label = Label(root, text="", bg="#f5f5f5", wraplength=400, font=("Helvetica", 12))
    result_label.pack(pady=10)

    root.mainloop()

server.shutdown()