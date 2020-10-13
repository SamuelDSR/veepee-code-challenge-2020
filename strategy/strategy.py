#!/usr/bin/env python
# -*- coding: utf-8 -*-
import attr
from random import choice


@attr.s
class Strategy:

    ACTIONS = [
        "up", "down", "left", "right",
        "fire-up", "fire-down", "fire-left", "fire-right"
    ]

    board = attr.ib(init=False)
    current_score = attr.ib(default=0, init=False)
    player_positions = attr.ib(default=[], init=False)
    can_shoot = attr.ib(default=True, init=False)
    is_alive = attr.ib(default=True, init=False)

    tag = attr.ib(tag="random")

    def process_environment(self, env):
        self.update_player(env)
        self.update_board(env)

    def next_move(self):
        pass

    def update_player(self, env):
        player = env["player"]
        self.player_positions.append((
            player["position"]["x"],
            player["position"]["y"]))
