#!/usr/bin/env python
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify
from strategy.random import RandomStrategy

USER = "slong"
EMAIL = "slong@veepee.com"
TAG = "Random"

server = Flask("AiServer-{tag}".format(tag=TAG))


@server.route("/name", methods=["POST"])
def get_username():
    jsonify(username=USER, email=EMAIL)


@server.route("/move", methods=["POST"])
def next_move():
    environement = request.get_json()
    strategy = RandomStrategy()
    move = strategy.tick(environement)
    return jsonify(move=move)


if __name__ == '__main__':
    server.run(host="0.0.0.0", port=9090)
