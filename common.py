#!/usr/bin/env python
# -*- coding: utf-8 -*-

from enum import Enum
from operator import eq, gt, lt

import attr


class BoardState(Enum):
    UNKNOWN = 0
    FREE = 1
    WALL = 2


class MOVEACTION(Enum):
    """
    x-axis: horizontal, widht
    y-axis: vertical, height
    (x, y) = (move in x-axis, move in y-axis)
    """
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)
    # player can return an invalid reponse so its position can remain unchanged
    INVALID = (100, 100)

    def __getitem__(self, idx):
        return self.value[idx]

    def __str__(self):
        return self.name.lower()

    def move(self, x, y):
        if self.name != "INVALID":
            return (x + self.value[0],
                    y + self.value[1])
        else:
            return (x, y)


class FIREACTION(Enum):
    """ a shoot has two checks:
    e.g., UP :(eq, gt) => eq(actor.x, target.x)
    and gt(actor.x, target.y)
    """
    UP = (eq, gt)
    DOWN = (eq, lt)
    LEFT = (gt, eq)
    RIGHT = (lt, eq)

    def __str__(self):
        return "fire-{}".format(self.name.lower())

    def __getitem__(self, idx):
        return self.value[idx]

    def move(self, pos):
        """
        Fire action doesn't change agent position
        """
        return pos

    def is_valid(self, actor_pos, target_pos):
        op1, op2 = self.value[0], self.value[1]
        if (op1(actor_pos[0], target_pos[0]) and
                op2(actor_pos[0], actor_pos[1])):
            return True
        return False


@attr.s(eq=False)
class Agent:
    x = attr.ib()
    y = attr.ib()
    is_dead = attr.ib(default=False)
    positions = attr.ib(default=[])

    def can_move_to(self, nx, ny, env):
        """
        Return if next postion of the agent could be (nx, ny)
        """
        return env.valid_pos(nx, ny)

    def next_positions(self, env):
        """Return all possible positions in next move
        """
        return [(self.x + a[0], self.y + a[1]) for a in self.next_actions(env)
                if isinstance(a, MOVEACTION)]

    def next_actions(self, env):
        """
        All possible actions that can be taken by agent in next move
        1. invalid actions will not be taken account into
        2. Equal prob of each action

        #TODO: build a behavoir proba distribution
        according to behavoir of agent

        Returns:
            actions, proba: next possible actions and the proba
        """
        actions = []
        for a in list(MOVEACTION):
            if env.valid_pos(self.x + a.value[0], self.y + a.value[1]):
                actions.append(a)
        if len(actions) > 0:
            return actions, [1 / len(actions)] * len(actions)
        else:
            return actions, []


@attr.s(eq=False)
class Player(Agent):
    SHOOT_COOLDOWN_DELAY = 5

    positions = attr.ib(default=[])
    actions = attr.ib(default=[])
    shoot_cd = attr.ib(default=0)

    def next_positions(self, env):
        positions = super().next_positions(env)
        # if a player can shoot, it can be immobile
        if self.shoot_cd == 0:
            positions.append((self.x, self.y))
        return positions

    def next_actions(self, env):
        actions, _ = super().next_actions(env)
        if self.shoot_cd == 0:
            for a in list(FIREACTION):
                actions.append(a)
        if len(actions) > 0:
            return actions, [1 / len(actions)] * len(actions)
        else:
            return actions, []


@attr.s(eq=False)
class Enemy(Agent):
    is_neutral = attr.ib(default=True)
