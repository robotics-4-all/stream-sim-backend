#!/usr/bin/python
# -*- coding: utf-8 -*-

import time
import json
import math
import logging
import threading
import random

from colorama import Fore, Style

from commlib.logger import Logger
from stream_simulator.connectivity import CommlibFactory
from stream_simulator.base_classes import BaseThing

class LedsController(BaseThing):
    WAIT_MS = 50

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
        _category = "actuator"
        _class = "visual"
        _subclass = "leds"
        _pack = package["name"]

        info = {
            "type": "LED",
            "brand": "neopx",
            "base_topic": f"{_pack}.{_category}.{_class}.{_subclass}.{name}",
            "name": name,
            "place": conf["place"],
            "id": id,
            "enabled": True,
            "orientation": conf["orientation"],
            "queue_size": 0,
            "mode": package["mode"],
            "speak_mode": package["speak_mode"],
            "namespace": package["namespace"],
            "sensor_configuration": conf["sensor_configuration"],
            "device_name": package["device_name"],
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
        self.base_topic = info["base_topic"]
        self.derp_data_key = info["base_topic"] + ".raw"

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

        self._color = {
                'r': 0.0,
                'g': 0.0,
                'b': 0.0
        }
        self._brightness = 0

        if self.info["mode"] == "real":
            # topic to initialize and publish to the remote led driver 
            self.neopixel_create_client = CommlibFactory.getRPCClient(
                broker="redis",            
                rpc_name = "neopixel.init"
            )

            self.neopixel_pub = CommlibFactory.getPublisher(
                broker = "redis",
                topic = "neopixel.set"
            )
        
        #############################################

        self.get_rpc_server = CommlibFactory.getRPCService(
            broker = "redis",
            callback = self.leds_get_callback,
            rpc_name = info["base_topic"] + ".get"
        )
        self.leds_wipe_server = CommlibFactory.getRPCService(
            broker = "redis",
            callback = self.leds_wipe_callback,
            rpc_name = info["base_topic"] + ".wipe"
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

    def enable_callback(self, message, meta):
        self.info["enabled"] = True
        return {"enabled": True}

    def disable_callback(self, message, meta):
        self.info["enabled"] = False
        return {"enabled": False}

    def start(self):
        self.get_rpc_server.run()
        self.leds_wipe_server.run()
        self.enable_rpc_server.run()
        self.disable_rpc_server.run()
    
        if self.info["mode"] == "real":
            self.neopixel_create_client.call({
                "settings": self.conf
            })

    def stop(self):
        self.get_rpc_server.stop()
        self.leds_wipe_server.stop()
        self.enable_rpc_server.stop()
        self.disable_rpc_server.stop()

    def leds_get_callback(self, message, meta):
        self.logger.info(f"Getting led state!")
        return {
            "color": self._color,
            "luminosity": self._brightness
        }

    def leds_wipe_callback(self, message, meta):
        try:
            response = message

            r = response["r"]
            g = response["g"]
            b = response["b"]
            brightness = response["brightness"]
            wait_ms = response["wait_ms"] if "wait_ms" in response else LedsController.WAIT_MS

            self._color = [r, g, b, brightness]
            self._brightness = brightness

            CommlibFactory.notify_ui(
                type = "robot_effectors",
                data = {
                    "name": self.name,
                    "robot": self.info["device_name"],
                    "value": {
                        'r': r,
                        'g': g,
                        'b': b,
                        'brightness': brightness
                    }
                }
            )

            if self.info["mode"] == "mock":
                pass
            elif self.info["mode"] == "simulation":
                pass
            else: # The real deal
                self.neopixel_pub.publish({
                    "color":self._color,
                    "wait_ms": wait_ms
                })

            r = CommlibFactory.derp_client.lset(
                self.derp_data_key,
                [{
                    "data": {"r": r, "g": g, "b": b, "brightness": brightness},
                    "type": "wipe",
                    "timestamp": time.time()
                }]
            )

            self.logger.info("{}: New leds wipe command: {}".format(self.name, message))

        except Exception as e:
            self.logger.error("{}: leds_wipe is wrongly formatted: {} - {}".format(self.name, str(e.__class__), str(e)))

        return {}
