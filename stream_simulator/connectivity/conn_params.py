#!/usr/bin/python
# -*- coding: utf-8 -*-

class ConnParams:
    type = "redis"

    REDIS_SETTINGS = {
        "host": "localhost",
        "port": 6379
    }

    # AMQP_SETTINGS = {
    #     "credentials": {
    #         "username": "bot",
    #         "password": "b0t"
    #     },
    #     "host": "issel08.ee.auth.gr.ddns.net",
    #     "port": 5672,
    #     "vhost": "sim"
    # }
    
    AMQP_SETTINGS = {
        "credentials": {
            "username": "elsa-0",
            "password": "elsa-0"
        },
        "host": "issel08.ee.auth.gr",
        "port": 5782,
        "vhost": "/"
    }

    @staticmethod
    def get(type):
        if type == "amqp":
            from commlib.transports.amqp import ConnectionParameters
            conn_params = ConnectionParameters()
            conn_params.credentials.username = ConnParams.AMQP_SETTINGS["credentials"]["username"]
            conn_params.credentials.password = ConnParams.AMQP_SETTINGS["credentials"]["password"]
            
            conn_params.host = ConnParams.AMQP_SETTINGS["host"]
            conn_params.port = ConnParams.AMQP_SETTINGS["port"]
            conn_params.vhost = ConnParams.AMQP_SETTINGS["vhost"]

            return conn_params
        elif type == "redis":
            from commlib.transports.redis import ConnectionParameters
            conn_params = ConnectionParameters()
            conn_params.host = ConnParams.REDIS_SETTINGS["host"]
            conn_params.port = ConnParams.REDIS_SETTINGS["port"]
            return conn_params

    @staticmethod
    def set(type, settings):
        if type == "redis":
            ConnParams.REDIS_SETTINGS = settings
        elif type == "amqp":
            ConnParams.AMQP_SETTINGS = settings