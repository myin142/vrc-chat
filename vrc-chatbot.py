# https://github.com/ikbenjepapa/VRC-transapp
# https://github.com/cyberkitsune/vrc-osc-scripts

import os
import time
from dotenv import load_dotenv
from pythonosc import osc_server, udp_client
from pythonosc.dispatcher import Dispatcher
from tkinter import Tk, Label, Button, ttk, StringVar, Frame
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
server = None

recognizer = sr.Recognizer()
last_request_time = datetime.datetime.now() - datetime.timedelta(seconds=5)
received_mute = False
input_lang = 'en-US'
target_lang = 'en-US'
is_recording = False
continuous_mode = False
continuous_thread = None
continuous_running = False

# GUI variables
root = None
input_lang_var = None
target_lang_var = None
status_label = None
record_button = None
continuous_var = None
continuous_checkbox = None
output_label = None


def check_limit():
    global last_request_time

    now = datetime.datetime.now()
    diff_in_sec = (now - last_request_time).total_seconds()
    if diff_in_sec < 5:
        return False

    last_request_time = datetime.datetime.now()
    return True


def transcribe_audio(language_code, use_timeout=True):
    try:
        print("Listening for audio input...")
        with sr.Microphone() as source:
            if use_timeout:
                audio = recognizer.listen(source, timeout=MIC_TIMEOUT)
            else:
                audio = recognizer.listen(source, timeout=MIC_TIMEOUT, phrase_time_limit=None)
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


def continuous_translation_loop():
    global continuous_running
    
    print("Starting continuous translation loop...")
    
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=1)
        
        while continuous_running:
            try:
                update_status("Listening (Continuous)...")
                print("Continuous mode: Listening for speech...")
                
                # Listen for speech with automatic phrase detection
                audio = recognizer.listen(source, timeout=2, phrase_time_limit=30)
                
                update_status("Processing...")
                print("Continuous mode: Speech detected, processing...")
                
                # Transcribe the audio
                text = recognizer.recognize_google(audio, language=input_lang)
                
                if text:
                    print(f"Continuous mode: Transcribed: {text}")
                    send_translation(text, input_lang, target_lang)
                
                # Small delay before next listen
                time.sleep(0.5)
                
            except sr.WaitTimeoutError:
                # No speech detected, continue listening
                continue
            except sr.UnknownValueError:
                print("Continuous mode: Could not understand audio")
                continue
            except Exception as e:
                print(f"Continuous mode error: {e}")
                time.sleep(1)
        
    print("Continuous translation loop ended.")
    update_status("Ready")

def start_continuous_mode():
    global continuous_running, continuous_thread
    
    if continuous_running:
        return
    
    continuous_running = True
    if record_button:
        record_button.config(state="disabled")
    continuous_thread = threading.Thread(target=continuous_translation_loop, daemon=True)
    continuous_thread.start()
    update_status("Continuous Mode Active")


def stop_continuous_mode():
    global continuous_running
    
    continuous_running = False
    if record_button:
        record_button.config(state="normal")
    update_status("Ready")


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
    global is_recording
    
    osc_client.send_message("/chatbox/typing", True)
    update_status("Recording...")
    input_text = transcribe_audio(input_language)

    if not input_text:
        osc_client.send_message("/chatbox/typing", False)
        is_recording = False
        update_status("Ready")
        if record_button:
            record_button.config(text="Start Recording", bg="green")
        return

    send_translation(input_text, input_language, target_language)


def send_translation(input_text, input_language, target_language):
    global is_recording
    
    if input_language == target_language:
        output_text = f'{input_text}'
        send_to_chatbox(output_text)
    else:
        translated_text = translate_text(input_text, input_language, target_language)
        if translated_text:
            output_text = f'{translated_text} ({input_text})'
            send_to_chatbox(output_text)
        else:
            print("Translation failed.")
            output_text = "Translation failed"

    osc_client.send_message("/chatbox/typing", False)
    is_recording = False
    update_status("Ready")
    update_output(output_text)
    
    # Update button state if in recording mode
    if record_button:
        record_button.config(text="Start Recording", bg="green")


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
    
    # Update GUI
    if input_lang_var:
        input_lang_var.set(LANGUAGE_TEXT[value])
    if target_lang_var:
        target_lang_var.set(LANGUAGE_TEXT[value])
    
    send_to_chatbox(f'[CHAT] {LANGUAGE_TEXT[value]}')


def set_translate_language(value):
    global target_lang

    if value < 0 or value >= len(LANGUAGES):
        return
    lang = LANGUAGES[value]
    print(f"Setting translate language to {lang} with input {input_lang}")

    target_lang = lang
    
    # Update GUI
    if target_lang_var:
        target_lang_var.set(LANGUAGE_TEXT[value])
    
    send_to_chatbox(f'[CHAT] {LANGUAGE_TEXT[LANGUAGES.index(input_lang)]} -> {lang}')


def on_input_lang_change(*args):
    global input_lang, target_lang
    selected = input_lang_var.get()
    if selected in LANGUAGE_TEXT:
        index = LANGUAGE_TEXT.index(selected)
        input_lang = LANGUAGES[index]
        target_lang = LANGUAGES[index]
        print(f"Input language changed to: {input_lang}")
        # Update the target language dropdown to match
        if target_lang_var:
            target_lang_var.set(selected)


def on_target_lang_change(*args):
    global target_lang
    selected = target_lang_var.get()
    if selected in LANGUAGE_TEXT:
        index = LANGUAGE_TEXT.index(selected)
        target_lang = LANGUAGES[index]
        print(f"Target language changed to: {target_lang}")


def toggle_continuous_mode():
    global continuous_mode
    
    continuous_mode = continuous_var.get()
    
    if continuous_mode:
        print("Continuous mode enabled")
        start_continuous_mode()
    else:
        print("Continuous mode disabled")
        stop_continuous_mode()


def toggle_recording():
    global is_recording
    
    if is_recording:
        is_recording = False
        record_button.config(text="Start Recording", bg="green")
        update_status("Ready")
    else:
        is_recording = True
        record_button.config(text="Stop Recording", bg="red")
        threading.Thread(target=start_translation, args=(input_lang, target_lang)).start()


def update_status(text):
    if status_label:
        status_label.config(text=f"Status: {text}")


def update_output(text):
    if output_label:
        output_label.config(text=text)


def start_osc_server():
    global server
    server = osc_server.ThreadingOSCUDPServer((VRCHAT_IP, LISTEN_PORT), dispatcher)
    print(f"OSC Server serving on {server.server_address}")
    server.serve_forever()


def on_closing():
    global server, continuous_running
    print("Shutting down...")
    continuous_running = False
    if server:
        server.shutdown()
    root.destroy()


def create_gui():
    global root, input_lang_var, target_lang_var, status_label, record_button, continuous_var, continuous_checkbox, output_label
    
    root = Tk()
    root.title("VRChat Translation Chatbot")
    root.geometry("400x500")
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    # Title
    title_label = Label(root, text="VRChat Translation Chatbot", font=("Arial", 14, "bold"))
    title_label.pack(pady=10)
    
    # Input Language Selection
    input_frame = Frame(root)
    input_frame.pack(pady=10, padx=20, fill="x")
    
    input_label = Label(input_frame, text="Input Language:", font=("Arial", 10))
    input_label.pack(side="left")
    
    input_lang_var = StringVar(value=LANGUAGE_TEXT[0])
    input_lang_dropdown = ttk.Combobox(
        input_frame,
        textvariable=input_lang_var,
        values=LANGUAGE_TEXT,
        state="readonly",
        width=15
    )
    input_lang_dropdown.pack(side="right")
    input_lang_var.trace("w", on_input_lang_change)
    
    # Translation Language Selection
    target_frame = Frame(root)
    target_frame.pack(pady=10, padx=20, fill="x")
    
    target_label = Label(target_frame, text="Translation Language:", font=("Arial", 10))
    target_label.pack(side="left")
    
    target_lang_var = StringVar(value=LANGUAGE_TEXT[0])
    target_lang_dropdown = ttk.Combobox(
        target_frame,
        textvariable=target_lang_var,
        values=LANGUAGE_TEXT,
        state="readonly",
        width=15
    )
    target_lang_dropdown.pack(side="right")
    target_lang_var.trace("w", on_target_lang_change)
    
    # Continuous Mode Checkbox
    from tkinter import BooleanVar, Checkbutton
    continuous_frame = Frame(root)
    continuous_frame.pack(pady=10, padx=20, fill="x")
    
    continuous_var = BooleanVar(value=False)
    continuous_checkbox = Checkbutton(
        continuous_frame,
        text="Enable Continuous Translation",
        variable=continuous_var,
        command=toggle_continuous_mode,
        font=("Arial", 9)
    )
    continuous_checkbox.pack(anchor="w")
    
    # Recording Button
    record_button = Button(
        root,
        text="Start Recording",
        command=toggle_recording,
        font=("Arial", 12, "bold"),
        bg="green",
        fg="white",
        width=20,
        height=2
    )
    record_button.pack(pady=15)
    
    # Output Display
    output_frame = Frame(root, bg="lightgray", relief="sunken", bd=1)
    output_frame.pack(pady=10, padx=20, fill="both", expand=True)
    
    output_label = Label(
        output_frame,
        text="Output will appear here",
        font=("Arial", 9),
        wraplength=350,
        justify="left",
        bg="lightgray",
        fg="black"
    )
    output_label.pack(padx=5, pady=5, fill="both", expand=True)
    
    # Status Label
    status_label = Label(root, text="Status: Ready", font=("Arial", 10), fg="blue")
    status_label.pack(pady=10)
    
    # Info Label
    info_label = Label(
        root,
        text="OSC Server listening on port 9001",
        font=("Arial", 8),
        fg="gray"
    )
    info_label.pack(side="bottom", pady=5)
    
    return root


def main():
    global dispatcher
    
    # Set up OSC dispatcher
    dispatcher.map("/avatar/parameters/MuteSelf", handle_mute)
    dispatcher.map("/avatar/parameters/Language", lambda url, value: set_input_language(value-1))
    dispatcher.map("/avatar/parameters/Translate", lambda url, value: set_translate_language(value-1))
    
    # Start OSC server in a separate thread
    osc_thread = threading.Thread(target=start_osc_server, daemon=True)
    osc_thread.start()
    
    # Create and run GUI
    gui = create_gui()
    gui.mainloop()


if __name__ == "__main__":
    main()