#!/usr/bin/python
# -*- coding: utf-8 -*-

import time
import json
import math
import logging
import threading
import random
import base64

from commlib_py.logger import Logger

from stream_simulator import ConnParams
if ConnParams.type == "amqp":
    from commlib_py.transports.amqp import ActionServer, RPCServer
elif ConnParams.type == "redis":
    from commlib_py.transports.redis import ActionServer, RPCServer

class SpeakerController:
    def __init__(self, info = None):
        self.logger = Logger(info["name"] + "-" + info["id"])

        self.info = info
        self.name = info["name"]
        self.conf = info["sensor_configuration"]

        self.memory = 100 * [0]

        if self.info["mode"] == "real":
            from pidevices import Speaker
            self.speaker = Speaker(dev_name = self.conf["dev_name"], name = self.name, max_data_length = self.conf["max_data_length"])

            if self.info["speak_mode"] == "espeak":
                from espeakng import ESpeakNG
                self.esng = ESpeakNG()
            elif self.info["speak_mode"] == "google":
                import os
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/home/pi/google_ttsp.json"

                from google.cloud import texttospeech
                self.client = texttospeech.TextToSpeechClient()
                self.audio_config = texttospeech.AudioConfig(
                    audio_encoding = texttospeech.AudioEncoding.LINEAR16,
                    sample_rate_hertz = 44100)

        self.play_action_server = ActionServer(conn_params=ConnParams.get(), on_goal=self.on_goal_play, action_name=info["base_topic"] + "/play")
        self.speak_action_server = ActionServer(conn_params=ConnParams.get(), on_goal=self.on_goal_speak, action_name=info["base_topic"] + "/speak")

        self.enable_rpc_server = RPCServer(conn_params=ConnParams.get(), on_request=self.enable_callback, rpc_name=info["base_topic"] + "/enable")
        self.disable_rpc_server = RPCServer(conn_params=ConnParams.get(), on_request=self.disable_callback, rpc_name=info["base_topic"] + "/disable")

    def on_goal_speak(self, goalh):
        self.logger.info("{} speak started".format(self.name))
        if self.info["enabled"] == False:
            return {}

        try:
            print(goalh.data)
            texts = goalh.data["text"]
            volume = goalh.data["volume"]
            language = goalh.data["language"]
        except Exception as e:
            self.logger.error("{} wrong parameters: {}".format(self.name, ))

        timestamp = time.time()
        secs = int(timestamp)
        nanosecs = int((timestamp-secs) * 10**(9))
        ret = {
            "header":{
                "stamp":{
                    "sec": secs,
                    "nanosec": nanosecs
                }
            }
        }
        if self.info["mode"] == "mock":
            now = time.time()
            while time.time() - now < 5:
                self.logger.info("Speaking...")
                if goalh.cancel_event.is_set():
                    self.logger.info("Cancel got")
                    return ret
                time.sleep(0.1)

        elif self.info["mode"] == "simulation":
            now = time.time()
            while time.time() - now < 5:
                self.logger.info("Speaking...")
                if goalh.cancel_event.is_set():
                    self.logger.info("Cancel got")
                    return ret
                time.sleep(0.1)

        else: # The real deal
            if self.info["speak_mode"] == "espeak":
                path = "/home/pi/manos_espeak.wav"
                self.esng.voice = language
                self.esng._espeak_exe([texts, "-w", path], sync = True)
                self.speaker.volume = volume
                self.speaker.async_write(path, file_flag=True)
                while self.speaker.playing:
                    time.sleep(0.1)
            else: # google
                from google.cloud import texttospeech
                self.voice = texttospeech.VoiceSelectionParams(\
                    language_code = language,\
                    ssml_gender = texttospeech.SsmlVoiceGender.FEMALE)

                synthesis_input = texttospeech.SynthesisInput(text = texts)
                response = self.client.synthesize_speech(input = synthesis_input, voice = self.voice, audio_config = self.audio_config)

                self.speaker.volume = volume
                self.speaker.async_write(response.audio_content, file_flag=False)
                while self.speaker.playing:
                    print("Speaking...")
                    time.sleep(0.1)

        self.logger.info("{} Speak finished".format(self.name))
        return ret

    def on_goal_play(self, goalh):
        self.logger.info("{} play started".format(self.name))
        if self.info["enabled"] == False:
            return {}

        try:
            string = goalh.data["string"]
            volume = goalh.data["volume"]
        except Exception as e:
            self.logger.error("{} wrong parameters: {}".format(self.name, ))

        timestamp = time.time()
        secs = int(timestamp)
        nanosecs = int((timestamp-secs) * 10**(9))
        ret = {
            "header":{
                "stamp":{
                    "sec": secs,
                    "nanosec": nanosecs
                }
            }
        }
        if self.info["mode"] == "mock":
            now = time.time()
            while time.time() - now < 5:
                self.logger.info("Playing...")
                if goalh.cancel_event.is_set():
                    self.logger.info("Cancel got")
                    return ret
                time.sleep(0.1)

        elif self.info["mode"] == "simulation":
            now = time.time()
            while time.time() - now < 5:
                self.logger.info("Playing...")
                if goalh.cancel_event.is_set():
                    self.logger.info("Cancel got")
                    return ret
                time.sleep(0.1)

        else: # The real deal
            source = base64.b64decode(string.encode("ascii"))
            self.speaker.async_write(source, file_flag = False)
            while self.speaker.playing:
                print("Playing...")
                time.sleep(0.1)

        self.logger.info("{} Playing finished".format(self.name))
        return ret

    def enable_callback(self, message, meta):
        self.info["enabled"] = True
        return {"enabled": True}

    def disable_callback(self, message, meta):
        self.info["enabled"] = False
        return {"enabled": False}

    def start(self):
        self.play_action_server.run()
        self.speak_action_server.run()
        self.enable_rpc_server.run()
        self.disable_rpc_server.run()

    def stop(self):
        self.play_action_server._goal_rpc.stop()
        self.play_action_server._cancel_rpc.stop()
        self.play_action_server._result_rpc.stop()
        self.speak_action_server._goal_rpc.stop()
        self.speak_action_server._cancel_rpc.stop()
        self.speak_action_server._result_rpc.stop()
        self.enable_rpc_server.stop()
        self.disable_rpc_server.stop()

    def memory_write(self, data):
        del self.memory[-1]
        self.memory.insert(0, data)
