#!/usr/bin/env python
# -*- coding: utf-8 -*-
from collections import defaultdict
from random import shuffle

import attr

from common import FIREACTION, MOVEACTION, Agent, BoardState, Enemy, Player

MEMORY = 10


@attr.s
class Environment():

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
    other_players = attr.ib(default=[], init=False)
    enemies = attr.ib(default=[], init=False)

    def valid_pos(self, x, y):
        if x < 0 or x > self.board_width - 1 \
                or y < 0 or y > self.board_height - 1 \
                or self.board[y][x] == BoardState.WALL:
            return False
        return True

    def update_from_state(self, state):
        self.update_board(state)
        self.update_other_player_by_positions(state)
        self.update_enemies_by_positions(state)
        self.update_player(state)

    def update_board(self, state):
        """For a board,
        0: unknown space
        1: free space
        2: wall
        """
        area = state["player"]
        size = state["board"]["size"]
        wall = state["board"]["walls"]
        self.board_width = size["width"]
        self.board_height = size["height"]

        # init board with all UNKNOWN
        if self.board is None:
            self.board = [
                [BoardState.UNKNOWN]*size["width"]
            ]*size["height"]

        # update visible area
        self.varea_x1 = area["x1"]
        self.varea_y1 = area["y1"]
        self.varea_y1 = area["x2"]
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

    def clear_shot_moves(self, agent, target):
        """
        minimum moves to take to get a clear shot
        assume that agent and target are all not mobile
        """




    def update_agent_by_positions(self, new_positions, agents, kind="enemy"):
        """Base on the positions of agents in current visible area we recevied,
        try to update the agents that we have seen in last visible area, this enables
        a history tracking of the moves and actions of the agents.
        Args:
            new_positions: new seen positions
            agents: agents last state
            kind: enemy or other players

        Returns:
            _agents: agents current state
        """
        n_pose_to_agent_map = defaultdict(set)

        # store agents for next frame
        _agents = []

        # treat dead or invisible agents
        for ag in agents:
            n_poses = ag.next_positions(self.board)
            # if none of next moves are in new positions, dead or out of invisible
            if not any(map(lambda m: m in new_positions, n_poses)):
                # dead
                if not self._can_move_out_visible(ag):
                    ag.is_dead = True
                # invisible
                else:
                    ag.positions.append((ag.x, ag.y))
                    ag.x = -1
                    ag.y = -1
                # the player is resolved either dead or invisible
                _agents.append(ag)
            else:
                for m in n_poses:
                    n_pose_to_agent_map[m].add(ag)

        tries = 0
        while len(new_positions) != 0:
            # dead loop guard
            tries += 1
            if tries > 20:
                break
            shuffle(new_positions)
            pos = new_positions.pop()
            # only one known player can move to this position
            # in some case, this new pos is at the boundry, and this only known players
            # happens to be killed and a new player fills it. but we don't consider this
            # since it's really rare
            if len(n_pose_to_agent_map.get(pos, set())) == 1:
                ag = n_pose_to_agent_map[pos].pop()
                ag.positions.append((ag.x, ag.y))
                ag.x = pos[0]
                ag.y = pos[1]
                _agents.append(ag)
                # since this agent is resolved, we remove it if appears in other n_moves_to_map
                for k, v in n_pose_to_agent_map.items():
                    if ag in v:
                        v.remove(ag)
            else:
                new_positions.add(pos)

        # if there are still unresolved new pos left, added as new agents
        for pos in new_positions:
            if kind == "enemy":
                _agents.append(Enemy(x=pos[0], y=pos[1]))
            else:
                _agents.append(Player(x=pos[0], y=pos[1]))
        return _agents

    def update_other_player_by_positions(self, state):
        new_positions = set((p['x'], p['y']) for p in state["players"])
        self.other_players = self.update_agent_by_positions(
            new_positions, self.other_players, "other players")

    def update_enemies_by_positions(self, state):
        new_positions = set((p['x'], p['y']) for p in state["enemies"])
        self.enemies = self.update_agent_by_positions(new_positions,
                                                      self.enemies, "enemy")

    def update_player(self, state):
        pass
