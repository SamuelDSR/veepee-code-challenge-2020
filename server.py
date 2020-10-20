#!/usr/bin/env python
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify
from ai import RandomStrategy
from env import RecordEnvironement

USER = "slong"
EMAIL = "slong@veepee.com"
TAG = "MaxReward"

server = Flask("AiServer-{tag}".format(tag=TAG))

env = RecordEnvironement()
strategy = RandomStrategy(env)


@server.route("/name", methods=["POST"])
def get_username():
    return jsonify(username=USER, email=EMAIL)


@server.route("/move", methods=["POST"])
def next_move():
    state = request.get_json()
    env.update_from_state(state)
    best_move = strategy.best_action()
    env.update_from_action(best_move)
    env.save()
    return jsonify(move=best_move)


if __name__ == '__main__':
    server.run(host="0.0.0.0", port=9090)
