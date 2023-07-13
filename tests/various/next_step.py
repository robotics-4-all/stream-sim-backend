#!/usr/bin/python
# -*- coding: utf-8 -*-

from commlib.transports.amqp import Publisher
from commlib.transports.amqp import ConnectionParameters
conn_params = ConnectionParameters()
conn_params.credentials.username = 'bot'
conn_params.credentials.password = 'b0t'
conn_params.host = 'tektrain-platform.issel.ee.auth.gr'
conn_params.port = 5672
conn_params.vhost = "sim"

import yaml
import pathlib

import sys
import time

cl = Publisher(conn_params=conn_params, topic=f"{sys.argv[1]}.step_by_step")
cl.publish("")
print(f"Published to {sys.argv[1]}.step_by_step")
time.sleep(1)
