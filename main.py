"""Small example OSC server

This program listens to several addresses, and prints some information about
received packets.
"""
from speech_recognition import UnknownValueError, WaitTimeoutError, AudioData
import speech_recognition as sr
import queue
import threading
import datetime
import os
import time
import textwrap
from translator import DeepLTranslator
import argparse
from dotenv import load_dotenv


from pythonosc.dispatcher import Dispatcher
from pythonosc import osc_server, udp_client

load_dotenv()
state = {'selfMuted': True}
state_lock = threading.Lock()

r = sr.Recognizer()
audio_queue = queue.Queue()
translator = DeepLTranslator(os.getenv('DEEPL_API'))
rate_limit = 2000  # milliseconds

'''
STATE MANAGEMENT
This should be thread safe
'''


def get_state(key):
    global state, state_lock
    state_lock.acquire()
    result = None
    if key in state:
        result = state[key]
    state_lock.release()
    return result


def set_state(key, value):
    global state, state_lock
    state_lock.acquire()
    state[key] = value
    state_lock.release()


'''
AUDIO COLLECTION THREAD
'''


def collect_audio():
    global audio_queue, r, config
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", default="127.0.0.1", help="The ip to listen on")
    parser.add_argument("--port", type=int, default=9001, help="The port to listen on")
    parser.add_argument("--send-ip", default="127.0.0.1", help="The ip to listen on")
    parser.add_argument("--send-port", type=int, default=9000, help="The port the OSC server is listening on")

    parser.add_argument("--from-lang", default="en-US", help="The language to translate from")
    parser.add_argument("--to-lang", default="en-US", help="The language to translate to")

    args = parser.parse_args()

    client = udp_client.SimpleUDPClient(args.send_ip, args.send_port)

    def process_sound():
        global audio_queue, r, config, methods
        current_text = ""
        last_text = ""
        last_disp_time = datetime.datetime.now()

        print("[ProcessThread] Starting audio processing!")
        while True:
            ad, final = audio_queue.get()

            if not get_state("selfMuted"):
                return

            print("[ProcessThread] Received audio data, final:", final)
            client.send_message("/chatbox/typing", (not final))
            text = None

            time_now = datetime.datetime.now()
            difference = time_now - last_disp_time
            # if difference.total_seconds() < 1 and not final:
            if not final:
                print("[ProcessThread] Not enough time passed since last message, skipping!")
                continue

            try:
                text = r.recognize_google(ad)
                print("[ProcessThread] Recognized text:", text)
            except UnknownValueError:
                print("[ProcessThread] Could not understand audio!")
                continue
            except TimeoutError:
                print("[ProcessThread] Timeout Error when recognizing speech!")
                continue
            except Exception as e:
                print("[ProcessThread] Exception!", e)
                continue

            if text is None or text == "":
                print("[ProcessThread] No text recognized!")
                continue

            current_text = text

            if last_text == current_text:
                print("[ProcessThread] Text is the same as last time, skipping!")
                continue

            last_text = current_text

            if args.from_lang.lower() != args.to_lang.lower():
                print("[ProcessThread] Translating text:", current_text)
                diff_in_milliseconds = difference.total_seconds() * 1000
                if diff_in_milliseconds < rate_limit:
                    ms_to_sleep = rate_limit - diff_in_milliseconds
                    print("[ProcessThread] Sending too many messages! Delaying by", (ms_to_sleep / 1000.0), "sec to not hit rate limit!")
                    time.sleep(ms_to_sleep / 1000.0)

                try:
                    trans = translator.translate(source_lang=args.from_lang, target_lang=args.to_lang, text=current_text)
                    origin = current_text
                    current_text = trans + " [%s->%s]" % (args.from_lang, args.to_lang)
                    print("[ProcessThread] Recognized:",origin, "->", current_text)
                except Exception as e:
                    print("[ProcessThread] Translating ran into an error!", e)
            else:
                print("[ProcessThread] Recognized:", current_text)

            if len(current_text) > 144:
                current_text = textwrap.wrap(current_text, width=144)[-1]

            last_disp_time = datetime.datetime.now()
            client.send_message("/chatbox/input", [current_text, True])

    def handle_mute(url, is_mute):
        print(f"Received {url}: {is_mute}")
        set_state("selfMuted", is_mute)

        # if emote_id == 2:
        #   client.send_message("/input/Vertical", 1)
        #   print("Sending Vertical 1")
        # elif emote_id == 9:
        #   client.send_message("/input/Vertical", -1)
        #   print("Sending Vertical -1")
        # client.send_message("/input/Vertical", 0)

    dispatcher = Dispatcher()
    dispatcher.map("/avatar/parameters/MuteSelf", handle_mute)

    pst = threading.Thread(target=process_sound)
    pst.start()

    cat = threading.Thread(target=collect_audio)
    cat.start()

    server = osc_server.ThreadingOSCUDPServer((args.ip, args.port), dispatcher)
    print("Serving on {}".format(server.server_address))
    server.serve_forever()

    pst.join()
    cat.join()
