#!/usr/bin/env python
# -*- coding: utf-8 -*-
from pathlib import Path
import json

import attr

from common import FIREACTION, BoardState, Player, Enemy


class Environment:
    def update_from_state(self, state):
        pass

    def update_from_action(self, action):
        pass

    def save(self):
        pass


@attr.s
class RecordEnvironement(Environment):
    """
    A environement that just records every response returned by server
    """
    saved_game = attr.ib(default={}, init=False)
    step = attr.ib(default=0, init=False)

    def update_from_state(self, state):
        self.saved_game["state"] = state
        self.saved_game["step"] = self.step
        self.step += 1

    def update_from_action(self, player_action):
        self.saved_game["player_action"] = str(player_action)

    def save(self):
        save_path = Path("state-{}.json".format(self.step))
        json.dump(self.saved_game, save_path.open("w"))


@attr.s
class RecurrentEnvironment(Environment):

    # board, NOTE: board[ny][nx], ny before nx in indexing
    board = attr.ib(default=None, init=False)
    board_width = attr.ib(default=None, init=False)
    board_height = attr.ib(default=None, init=False)

    # visible area
    varea_x1 = attr.ib(default=-1, init=False)
    varea_y1 = attr.ib(default=-1, init=False)
    varea_x2 = attr.ib(default=-1, init=False)
    varea_y2 = attr.ib(default=-1, init=False)

    player = attr.ib(default=None, init=False)
    short_range_x = attr.ib(default=None, init=False)
    short_range_y = attr.ib(default=None, init=False)
    other_players = attr.ib(default=[], init=False)
    enemies = attr.ib(default=[], init=False)

    def print_game(self):
        def _print_cell(c):
            if c == BoardState.FREE:
                return "_"
            elif c == BoardState.WALL:
                return "#"
            else:
                return "X"
        rows = [
            list(map(lambda c: _print_cell(c), r))
            for r in self.board
        ]
        for p in self.other_players:
            rows[p.y][p.x] = "P"
        for e in self.enemies:
            rows[e.y][e.x] = "E"
        rows[self.player.y][self.player.x] = "M"
        rows = ["  ".join(r) for r in rows]
        bb = "\n".join(rows)
        print(bb)

    def valid_pos(self, x, y):
        if x < 0 or x > self.board_width - 1 \
                or y < 0 or y > self.board_height - 1 \
                or self.board[y][x] == BoardState.WALL:
            return False
        return True

    def added_exploration_area(self, nx, ny):
        """
        If the next position of player is (nx, ny),
        how much explored area will be added in the board
        """
        x1 = max(0, nx - self.short_range_x)
        x2 = min(self.board_width - 1, nx + self.short_range_x)

        y1 = max(0, ny - self.short_range_y)
        y2 = min(self.board_height - 1, ny + self.short_range_y)

        count = 0
        for i in range(x1, x2 + 1):
            for j in range(y1, y2 + 1):
                if self.board[j][i] == BoardState.UNKNOWN:
                    count += 1
        return count

    def update_from_state(self, state):
        self.update_board(state)
        self.update_other_players(state)
        self.update_enemies(state)
        self.update_player(state)
        self.print_game()

    def update_other_players(self, state):
        players = state["players"]
        self.other_players = [
            Player(x=p['x'], y=p['y'])
            for p in players
        ]

    def update_enemies(self, state):
        enemies = state["enemies"]
        self.enemies = [
            Enemy(x=e['x'], y=e['y'], is_neutral=e["neutral"])
            for e in enemies
        ]


    def update_board(self, state):
        """For a board,
        0: unknown space
        1: free space
        2: wall
        """
        area = state["player"]["area"]
        size = state["board"]["size"]
        wall = state["board"]["walls"]
        self.board_width = size["width"]
        self.board_height = size["height"]

        # init board with all UNKNOWN
        if self.board is None:
            self.board = [
                [BoardState.UNKNOWN for i in range(size["width"])]
                for j in range(size["height"])
            ]

        # update visible area
        self.varea_x1 = area["x1"]
        self.varea_y1 = area["y1"]
        self.varea_x2 = area["x2"]
        self.varea_y2 = area["y2"]

        # init all visible area as free space
        for x in range(area["x1"], area["x2"] + 1):
            for y in range(area["y1"], area["y2"] + 1):
                self.board[y][x] = BoardState.FREE

        # update walls
        for w in wall:
            self.board[w["y"]][w["x"]] = BoardState.WALL


    def inside_visible(self, x, y):
        if self.varea_x1 <= x <= self.varea_x2 and self.varea_y1 <= y <= self.varea_y2:
            return True
        return False

    def can_move_out_visible(self, agent):
        next_positions = agent.next_positions(self)
        # next possible moves are all inside current visible area
        if all(map(lambda m: self.inside_visible(m[0], m[1]), next_positions)):
            return False
        return True

    def has_clear_shoot(self, agent_pos, action, target_pos):
        if not isinstance(action, FIREACTION):
            return False
        # first check if this shot is valid
        if not action.is_valid(agent_pos, target_pos):
            return False
        # then check if any walls between agent_pos and target_pos in shooting direction
        # because shoot cannot go through walls
        ax, ay = agent_pos[0], agent_pos[1]
        tx, ty = target_pos[0], target_pos[1]
        if action == FIREACTION.UP:
            for y in range(ty + 1, ay):
                if self.board[y][ax] == BoardState.WALL:
                    return False
        elif action == FIREACTION.DOWN:
            for y in range(ay + 1, ty):
                if self.board[y][ax] == BoardState.WALL:
                    return False
        elif action == FIREACTION.LEFT:
            for x in range(tx + 1, ax):
                if self.board[ay][x] == BoardState.WALL:
                    return False
        else:
            for x in range(ax + 1, tx):
                if self.board[ay][x] == BoardState.WALL:
                    return False
        return True

    def update_player(self, state):
        if self.player is None:
            self.player = Player(x=0, y=0)
        player = state["player"]
        self.player.x = player["position"]["x"]
        self.player.y = player["position"]["y"]
        self.player.positions.append((self.player.x, self.player.y))
        if self.short_range_x is None:
            self.short_range_x = abs(self.varea_x1 - self.player.x)
        if self.short_range_y is None:
            self.short_range_y = abs(self.varea_y1 - self.player.y)
