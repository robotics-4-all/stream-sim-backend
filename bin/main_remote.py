#!/usr/bin/python3
# -*- coding: utf-8 -*-

import time
import sys
import os
import threading
import subprocess
import logging
import yaml
from colorama import Fore, Style

from stream_simulator import Simulator

from commlib.logger import Logger

from stream_simulator import ConnParams
if ConnParams.type == "amqp":
    from commlib.transports.amqp import Publisher, RPCService
elif ConnParams.type == "redis":
    from commlib.transports.redis import Publisher, RPCService

from commlib.transports.amqp import RPCService, Subscriber, RPCClient, Publisher

class SimulatorHandler:
    def __init__(self):
        self.logger = Logger("main_remote")
        logging.getLogger("pika").setLevel(logging.WARNING)

        self.timeout = 120

        try:
            self.namespace = os.environ['TEKTRAIN_NAMESPACE']
        except:
            self.logger.warning("No TEKTRAIN_NAMESPACE environmental variable found. Automatically setting it to robot")
            os.environ["TEKTRAIN_NAMESPACE"] = "robot"
            self.namespace = "robot"

        from derp_me.client import DerpMeClient
        self.derp_client = DerpMeClient(conn_params=ConnParams.get("redis"))

        self.simulators_cnt = -1

        self.start = RPCService(
            conn_params=ConnParams.get("amqp"),
            on_request=self.start_callback,
            rpc_name='simulator.start'
        )
        self.logger.info(f"{Fore.RED}Created amqp RPCService simulator.start{Style.RESET_ALL} ")

        self.stop = RPCService(
            conn_params=ConnParams.get("amqp"),
            on_request=self.stop_callback,
            rpc_name='simulator.stop'
        )
        self.logger.info(f"{Fore.RED}Created amqp RPCService simulator.stop{Style.RESET_ALL}")

        self.execution_sub = Subscriber(
            conn_params=ConnParams.get("amqp"),
            topic="*.execution",
            on_message=self.execution_callback
        )
        self.logger.info(f"{Fore.RED}Created amqp Subscriber *.execution{Style.RESET_ALL}")

        self.stop_sim_rpc_client = RPCClient(
            conn_params=ConnParams.get("amqp"),
            rpc_name="thing.simbot.deploy_manager.stop_sim"
        )

        self.start.run()
        self.stop.run()
        self.execution_sub.run()

        # Find my absolute path
        self.configurations_dir = os.path.dirname(os.path.abspath(__file__)) + "/../configurations/"
        self.logger.info(f"Configurations dir is {self.configurations_dir}")

        self.processes = {}
        self.simulations = {}
        self.timestamps = {}

        self.check_thread = threading.Thread(target = self.sims_check)
        self.check_thread.start()

    def execution_callback(self, message, meta):
        if "teksim_device" not in message["device"]:
            return
        self.timestamps[message["device"]] = time.time()

    def sims_check(self):
        while True:
            time.sleep(2.0)
            curr_time = time.time()
            for sim in self.timestamps:
                tt = self.timeout - (time.time() - self.timestamps[sim])
                self.logger.info(f"{sim}: Time for inactivity kill: {tt}")
                if tt < 0:
                    self.logger.warning(f"Stopping simulator {sim} due to inactivity")
                    self.stop_sim_rpc_client.call({"sim_id": sim})
                    kill_pub = Publisher(
                        conn_params=ConnParams.get("amqp"),
                        topic=f"thing.simbot.deploy_manager.{sim}.killed"
                    )
                    self.logger.warning(f"Publishing to thing.simbot.deploy_manager.{sim}.killed")
                    kill_pub.publish({})
                    break

    def print(self):
        self.logger.info("Available simulators:")
        for s in self.simulations:
            self.logger.info(f"{Fore.MAGENTA}{s} : {self.simulations[s]}{Style.RESET_ALL}")
        self.logger.info("Timestamps remaining:")
        for t in self.timestamps:
            self.logger.info(f"{Fore.MAGENTA}{s} : {self.timestamps[t]}{Style.RESET_ALL}")

    def start_callback(self, message, meta):
        try:
            self.simulators_cnt += 1
            name = "teksim_device_" + str(self.simulators_cnt)
            # Write configuration in yaml
            _t = str(time.time())
            _t = _t[:_t.find(".")]
            yaml_file = f"{name}_{_t}"
            _file = f"{self.configurations_dir}{yaml_file}.yaml"
            with open(_file, "w") as f:
                docs = yaml.dump(message, f)

            # Start subprocess
            self.logger.warning(f"Starting subprocess: python3 main.py {yaml_file} {name}")
            proc = subprocess.Popen(f"exec python3 main.py {yaml_file} {name}", shell=True)

            # Memory update
            self.simulations[name] = proc

            # Wait for the process to start
            _started = False
            _time_start = time.time()
            while not _started:
                time.sleep(0.2)
                try:
                    v = self.derp_client.lget("stream_sim/state", 0, 0)['val'][0]
                    self.logger.warning(v)
                    if v['timestamp'] > _time_start and v["device"] == f"{self.namespace}.{name}":
                        _started = True
                        self.logger.warning(f"Simulator {name} started")
                except:
                    self.logger.warning("Derp me has no such key - probably this is the first simulator running")

            # Leftovers
            os.remove(_file)
            self.timestamps[name] = time.time()
            # Show the running simulators
            self.print()
        except Exception as e:
            self.logger.error(e)
            return {"status": False}

        return {"status": True, "name": name}

    def stop_callback(self, message, meta):
        try:
            name = message["device"]
            self.logger.warning(f"Trying to stop device {name}")
            self.simulations[name].kill()
            self.simulations.pop(name)
            self.timestamps.pop(name)
            self.print()
        except Exception as e:
            self.logger.error(f"Could not stop simulator {message['device']}")
            self.print()
            return {'status': False}
        return {"status": True}

if __name__ == "__main__":
    s = SimulatorHandler()
    while True:
        time.sleep(1)
