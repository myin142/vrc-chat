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
    'en-US',
    'ja-JP',
    'zh-CN',
    'ko-KR',
]

LANGUAGE_TEXT = [
    'English',
    '日本語',
    '中文',
    '한국어',
]

TOGGLE_THRESHOLD = 0.5
VRCHAT_IP = "127.0.0.1"
VRCHAT_PORT = 9000
LISTEN_PORT = 9001
MIC_TIMEOUT = 6
osc_client = udp_client.SimpleUDPClient(VRCHAT_IP, VRCHAT_PORT)

dispatcher = Dispatcher()
server = osc_server.ThreadingOSCUDPServer((VRCHAT_IP, LISTEN_PORT), dispatcher)

recognizer = sr.Recognizer()
last_request_time = datetime.datetime.now() - datetime.timedelta(seconds=5)
received_mute = False
input_lang = 'en-US'
target_lang = 'en-US'


def check_limit():
    global last_request_time

    now = datetime.datetime.now()
    diff_in_sec = (now - last_request_time).total_seconds()
    if diff_in_sec < 5:
        return False

    last_request_time = datetime.datetime.now()
    return True


def transcribe_audio(language_code):
    try:
        print("Listening for audio input...")
        audio = recognizer.listen(source, timeout=MIC_TIMEOUT)
        text = recognizer.recognize_google(audio, language=language_code)
        return text
    except sr.WaitTimeoutError:
        print("No speech detected within the timeout period.")
        return None
    except sr.UnknownValueError:
        print("Google Speech Recognition could not understand the audio.")
        return None
    except Exception as e:
        print(f"Error during transcription: {e}")
        return None


def translate_text(text, input_language, target_language):
    if not check_limit():
        return "Testing limit reached. Contact the developer for more access."
    try:
        return deepl.translate(input_language, target_language, text)
    except Exception as e:
        print(f"Error during translation: {e}")
        return None


def send_to_chatbox(output_text):
    try:
        if not output_text:
            return
        osc_client.send_message("/chatbox/input", [output_text, True])
        print(f"Sent to Chatbox: {output_text}")
    except Exception as e:
        print(f"Error sending to Chatbox: {e}")


def start_translation(input_language, target_language):
    osc_client.send_message("/chatbox/typing", True)
    input_text = transcribe_audio(input_language)

    if not input_text:
        osc_client.send_message("/chatbox/typing", False)
        return

    send_translation(input_text, input_language, target_language)


def send_translation(input_text, input_language, target_language):
    if input_language == target_language:
        send_to_chatbox(f'{input_text}')
    else:
        translated_text = translate_text(input_text, input_language, target_language)
        if translated_text:
            send_to_chatbox(f'{translated_text} ({input_text})')
        else:
            print("Translation failed.")

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
        threading.Thread(target=start_translation, args=(input_lang, target_lang)).start()


def set_input_language(value):
    global input_lang, target_lang

    if value < 0 or value >= len(LANGUAGES):
        return
    lang = LANGUAGES[value]
    print(f"Setting input language to {lang}")

    input_lang = lang
    target_lang = lang
    send_to_chatbox(f'[CHAT] {LANGUAGE_TEXT[value]}')


def set_translate_language(value):
    global target_lang

    if value < 0 or value >= len(LANGUAGES):
        return
    lang = LANGUAGES[value]
    print(f"Setting translate language to {lang} with input {input_lang}")

    target_lang = lang
    send_to_chatbox(f'[CHAT] {LANGUAGE_TEXT[LANGUAGES.index(input_lang)]} -> {lang}')


dispatcher.map("/avatar/parameters/MuteSelf", handle_mute)
dispatcher.map("/avatar/parameters/Language", lambda url, value: set_input_language(value-1))
dispatcher.map("/avatar/parameters/Translate", lambda url, value: set_translate_language(value-1))

with sr.Microphone() as source:
    print("Serving on {}".format(server.server_address))
    server.serve_forever()
server.shutdown()
