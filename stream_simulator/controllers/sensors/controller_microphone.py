#!/usr/bin/python
# -*- coding: utf-8 -*-

import time
import json
import math
import logging
import threading
import random
import base64
import wave
import socket

from colorama import Fore, Style

from commlib.logger import Logger
from stream_simulator.connectivity import CommlibFactory
from stream_simulator.base_classes import BaseThing
from stream_simulator.functionality import VAD

class MicrophoneController(BaseThing):
    def __init__(self, conf = None, package = None):
        if package["logger"] is None:
            self.logger = Logger(conf["name"])
        else:
            self.logger = package["logger"]

        super(self.__class__, self).__init__()
        id = "d_" + str(BaseThing.id)
        name = id
        if 'name' in conf:
            name = conf['name']
        _category = "sensor"
        _class = "audio"
        _subclass = "microphone"
        _pack = package["name"]

        info = {
            "type": "MICROPHONE",
            "brand": "usb_mic",
            "base_topic": f"{_pack}.{_category}.{_class}.{_subclass}.{name}",
            "name": name,
            "place": conf["place"],
            "id": "id_" + str(id),
            "enabled": True,
            "orientation": conf["orientation"],
            "queue_size": 0,
            "mode": package["mode"],
            "speak_mode": package["speak_mode"],
            "namespace": package["namespace"],
            "sensor_configuration": conf["sensor_configuration"],
            "device_name": package["device_name"],
            "actors": package["actors"],
            "categorization": {
                "host_type": "robot",
                "place": _pack.split(".")[-1],
                "category": _category,
                "class": _class,
                "subclass": [_subclass],
                "name": name
            }
        }

        self.info = info
        self.name = info["name"]
        self.conf = info["sensor_configuration"]

        # tf handling
        tf_package = {
            "type": "robot",
            "subtype": {
                "category": _category,
                "class": _class,
                "subclass": [_subclass]
            },
            "pose": conf["pose"],
            "base_topic": info['base_topic'],
            "name": self.name
        }
        tf_package['host'] = package['device_name']
        tf_package['host_type'] = 'robot'
        if 'host' in conf:
            tf_package['host'] = conf['host']
            tf_package['host_type'] = 'pan_tilt'
        package["tf_declare"].call(tf_package)

        self.blocked = False

        # merge actors
        self.actors = []
        for i in info["actors"]:
            for h in info["actors"][i]:
                k = h
                h["type"] = i
                self.actors.append(k)
        
        from pidevices import PyAudioMic
        self.vad = VAD()
        self.sensor = PyAudioMic(channels=self.conf["channels"],
                                 framerate=self.conf["framerate"],
                                 name=self.name,
                                 max_data_length=self.conf["max_data_length"])

        self.logger.warning("Using Default Microphone Driver")
        self.sensor.start()

        self.record_action_server = CommlibFactory.getActionServer(
            broker = "redis",
            callback = self.on_goal,
            action_name = info["base_topic"] + ".record"
        )
        self.listen_action_server = CommlibFactory.getActionServer(
            callback = self.on_goal_listen,
            action_name = info["base_topic"] + ".listen"
        )
        self.event_emmiter = CommlibFactory.getEventEmmiter(
            broker = "redis"
        )
        self.event_start_listenning = CommlibFactory.getEvent(
            name = "StartListenning",
            event_name = "event.listenning.started"
        )
        self.event_stop_listenning = CommlibFactory.getEvent(
            name = "StopListenning",
            event_name = "event.listenning.stopped"
        )
        self.enable_rpc_server = CommlibFactory.getRPCService(
            broker = "redis",
            callback = self.enable_callback,
            rpc_name = info["base_topic"] + ".enable"
        )
        self.disable_rpc_server = CommlibFactory.getRPCService(
            broker = "redis",
            callback = self.disable_callback,
            rpc_name = info["base_topic"] + ".disable"
        )

        self.vad_training_rpc = CommlibFactory.getRPCService(
            broker = "redis",
            callback = self.vad_training_callback,
            rpc_name = info["base_topic"] + ".train_vad"
        )

        listen_text_topic = f"thing.{socket.gethostname()}.streamsim.microphone.listen"
        self.listen_text_pub = CommlibFactory.getPublisher(
            broker = "amqp",
            topic = listen_text_topic
        )

        self.record_pub = CommlibFactory.getPublisher(
            topic = info["base_topic"] + ".record.notify"
        )

        self.detect_speech_sub = CommlibFactory.getSubscriber(
            topic = info["base_topic"] + ".speech_detected",
            callback = self.speech_detected
        )
        self.detect_speech_sub.run()

    def speech_detected(self, message, meta):
        source = message["speaker"]
        text = message["text"]
        language = message["language"]
        self.logger.info(f"Speech detected from {source} [{language}]: {text}")

    def load_wav(self, path):
        # Read from file
        import wave
        import os
        from pathlib import Path
        dirname = Path(__file__).resolve().parent
        fil = str(dirname) + '/../../resources/' + path
        self.logger.info("Reading sound from " + fil)
        f = wave.open(fil, 'rb')
        channels = f.getnchannels()
        framerate = f.getframerate()
        sample_width = f.getsampwidth()
        data = bytearray()
        sample = f.readframes(256)
        while sample:
            for s in sample:
                data.append(s)
            sample = f.readframes(256)
        f.close()
        source = base64.b64encode(data).decode("ascii")
        return source

    def on_goal(self, goalh):
        self.logger.info("{} recording started".format(self.name))
        if self.info["enabled"] == False:
            return {}

        # Concurrent speaker calls handling
        while self.blocked:
            time.sleep(0.1)
        self.logger.info("Microphone unlocked")
        self.blocked = True

        try:
            duration = goalh.data["duration"]
        except Exception as e:
            self.logger.error("{} goal had no duration as parameter".format(self.name))

        self.record_pub.publish({
            "duration": duration
        })

        timestamp = time.time()
        secs = int(timestamp)
        nanosecs = int((timestamp-secs) * 10**(9))
        ret = {
            "header":{
                "stamp":{
                    "sec": secs,
                    "nanosec": nanosecs
                }
            },
            "record": "",
            "volume": 0
        }

        self.event_emmiter.send_event(self.event_start_listenning)
        self.logger.info("Emmiting event: {}!".format(
            self.event_start_listenning.name
        ))

        if self.info["mode"] == "mock":
            now = time.time()
            while time.time() - now < duration:
                self.logger.info("Recording...")
                if goalh.cancel_event.is_set():
                    self.logger.info("Cancel got")
                    self.blocked = False
                    return ret
                time.sleep(0.1)

            ret["record"] = base64.b64encode(b'0x55').decode("ascii")
            ret["volume"] = 100

        elif self.info["mode"] == "simulation":
            while CommlibFactory.get_tf_affection == None:
                time.sleep(0.1)
            # Ask tf for proximity sound sources or humans
            res = CommlibFactory.get_tf_affection.call({
                'name': self.name
            })
            # Get the closest:
            clos = None
            clos_d = 100000.0
            for x in res:
                if res[x]['distance'] < clos_d:
                    clos = x
                    clos_d = res[x]['distance']

            if clos in res:
                if res[clos]['type'] == 'sound_source':
                    if res[clos]['info']['language'] == 'EL':
                        wav = "greek_sentence.wav"
                    else:
                        wav = "english_sentence.wav"
                elif res[clos]['type'] == "human":
                    if res[clos]['info']["sound"] == 1:
                        if res[clos]['info']["language"] == "EL":
                            wav = "greek_sentence.wav"
                        else:
                            wav = "english_sentence.wav"

                self.logger.info(f"Recording... {res[clos]['type']}, {res[clos]['info']}")
            else:
                wav = "Silent.wav"
                
                self.logger.info(f"Nothing to record... Silence everywhere!")

            now = time.time()
            
            while time.time() - now < duration:
                if goalh.cancel_event.is_set():
                    self.logger.info("Cancel got")
                    self.blocked = False
                    return ret
                time.sleep(0.1)
            self.logger.info("Recording done")

            try:
                ret["record"] = self.load_wav(wav)
            except OSError as e:
                self.logger.error(f"No such file of directory {e}")
                ret["record"] = base64.b64encode(b'0x55').decode("ascii") # return mock in case of error

            ret["volume"] = 100

        else: # The real deal
            try:
                self.sensor.async_read(secs = duration)
                
                while not self.sensor.recording:
                    time.sleep(0.1)
                
                now = time.time()
                while time.time() - now < (duration + 0.5) and self.sensor.recording:
                    if goalh.cancel_event.is_set():
                        self.blocked = False
                        self.sensor.cancel()

                        self.logger.info("Cancel got")
                        return ret

                    time.sleep(0.1)

                self.logger.info("Microphone unlocked")
                
                record = self.sensor.record

                if self.sensor.record:
                    record = {
                        "data": base64.b64encode(self.sensor.record).decode("ascii"),
                        "channels": self.sensor._channels,
                        "framerate": self.sensor._framerate,
                        "sample_width": self.sensor._sample_width
                    }

                    ret["record"] = record
            except Exception as e:
                self.logger.error("{} problem in driver during recording".format(self.name))

        self.event_emmiter.send_event(self.event_stop_listenning)
        self.logger.info("Emmiting event: {}!".format(
            self.event_stop_listenning.name
        ))
        
        self.logger.info("{} recording finished".format(self.name))
        self.blocked = False
        return ret

    def on_goal_listen(self, goalh):
        self.logger.info("{} listening started".format(self.name))
        if self.info["enabled"] == False:
            return {}

        self.event_emmiter.send_event(self.event_start_listenning)
        self.logger.info("Emmiting event: {}!".format(
            self.event_start_listenning.name
        ))

        # ELSA stuff
        import os
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/home/pi/google_ttsp.json"

        # Concurrent speaker calls handling
        while self.blocked:
            time.sleep(0.1)
        self.logger.info("Microphone unlocked")
        self.blocked = True

        try:
            duration = goalh.data["duration"]

            if duration < 0:
                self.logger.warning("{} listen duration should be a positive number".format(self.name))
                raise ValueError

        except Exception as e:
            duration = 10
            self.logger.error("{} goal had no duration as parameter".format(self.name))

        try:
            language = goalh.data["language"]
        except Exception as e:
            language = 'EL'
            self.logger.error("{} goal had no language as parameter".format(self.name))
        
        try:
            vad = goalh.data["vad"]
        except Exception as e:
            vad = True
            self.logger.error("{} goal had no vad as parameter".format(self.name))

        
        if self.info["mode"] == "real": # The real deal
            try:
                if vad: 
                    self.vad.reset()
                    self.sensor.async_read(secs=100, stream_cb=self.vad.update)         

                    timer = time.time()
                    voice_was_detected = False
                    while not self.vad.has_spoken() and (time.time() - timer) < duration:
                        if self.vad.voice_detected() and not voice_was_detected:
                            voice_was_detected = True
                            self.logger.info("Voice Detected! Start Recording...")
                        if goalh.cancel_event.is_set():
                            self.sensor.cancel()
                            self.logger.info("Goal Cancelled")
                            break
                        time.sleep(0.1)

                    time.sleep(0.3)

                    self.sensor.cancel()
                    
                    self.logger.info("No voice during last: {} sec. Stop Recording!".format(self.vad.speech_timeout))
                else:
                    self.sensor.async_read(secs=duration)

                    while not self.sensor.recording:
                        time.sleep(0.1)

                    now = time.time()
                    while time.time() - now < (duration + 0.1) and self.sensor.recording:
                        if goalh.cancel_event.is_set():
                            self.sensor.cancel()
                            self.logger.info("Goal Cancelled")
                            break
                        time.sleep(0.1)

                rec = base64.b64encode(self.sensor.record).decode("ascii")
                rec = base64.b64decode(rec)
            except Exception as e:
                self.logger.error("{} problem in driver during recording: {}".format(self.name, e))

            self.blocked = False
            self.logger.info("Microphone unlocked")

            self.event_emmiter.send_event(self.event_stop_listenning)
            self.logger.info("Emmiting event: {}!".format(
                self.event_stop_listenning.name
            ))

            result = ''

            try:
                from google.cloud import speech

                self.client = speech.SpeechClient()
                speech_config = speech.RecognitionConfig(
                    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                    sample_rate_hertz=self.conf['framerate'],
                    language_code='el-GR'
                )

                text = self.client.recognize(
                    config = speech_config,
                    audio = speech.RecognitionAudio(content=rec)
                )
                
                if len(text.results):
                    result = text.results[0].alternatives[0].transcript
                else:
                    result = ''
            
            except Exception as e:
                result = ''

                self.logger.error("{} Problem with google text-to-speech".format(self.name))

        self.listen_text_pub.publish({
            "text": result 
        })

        self.logger.info("Listening finished: " + str(result))
        return {'text': result}

    def enable_callback(self, message, meta):
        self.info["enabled"] = True
        return {"enabled": True}

    def disable_callback(self, message, meta):
        self.info["enabled"] = False
        return {"enabled": False}

    def vad_training_callback(self, message, meta):
        self.logger.info("{} VAD training started".format(self.name))

        status = False
        
        if self.info["enabled"] == False:
            return {"status": status}
        
        try:
            if not "duration" in message:
                raise KeyError("Wrong parameters: Require <duration>")

            if message['duration'] <= 0:
                raise ValueError("Duration must be a positive number!")

            self.vad.start_train()
            self.sensor.read(secs=message['duration'], stream_cb=self.vad.train)
            self.vad.finish_train()
            status = True
            self.logger.info("VAD training completed succesfully!")
        except Exception as e:
            self.logger.error("VAD training error occured: {}!".format(e))
            
        return {"status": status}

    def start(self):
        self.record_action_server.run()
        self.listen_action_server.run()
        self.enable_rpc_server.run()
        self.disable_rpc_server.run()
        self.vad_training_rpc.run()

    def stop(self):
        self.record_action_server._goal_rpc.stop()
        self.record_action_server._cancel_rpc.stop()
        self.record_action_server._result_rpc.stop()
        self.listen_action_server._goal_rpc.stop()
        self.listen_action_server._cancel_rpc.stop()
        self.listen_action_server._result_rpc.stop()
        self.enable_rpc_server.stop()
        self.disable_rpc_server.stop()
        self.vad_training_rpc.stop()