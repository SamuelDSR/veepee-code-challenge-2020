#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
from pathlib import Path
from collections import deque
from random import shuffle

import attr
import numpy as np

from common import FIREACTION, MOVEACTION, BoardState, Enemy, Player
from loguru import logger


class Environment():
    def update(self, state):
        pass

    def update_after_player_action(self, action):
        pass


@attr.s
class RecordEnvironement(Environment):
    """
    A environement that just records every response returned by server
    """
    game_frame = attr.ib(default=[], init=False)
    step = attr.ib(default=0, init=False)

    def update(self, state):
        state["step"] = self.step
        self.game_frame.append(state)
        self.step += 1

    def update_after_player_action(self, player_action):
        self.game_frame[-1]["player_action"] = str(player_action)

    def save(self, prefix):
        frame_save_path = Path(prefix) / "game_frames.json"
        json.dump(self.game_frame, frame_save_path.open('w'))


@attr.s
class RecurrentEnvironment(RecordEnvironement):

    # board, NOTE: board[ny][nx], ny before nx in indexing
    board = attr.ib(default=None, init=False)
    board_heatmap = attr.ib(default=None, init=False)
    board_width = attr.ib(default=None, init=False)
    board_height = attr.ib(default=None, init=False)
    board_list = attr.ib(default=[], init=False)

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

    def load_game_from_file(self, path="board.txt"):
        with Path(path).open("r") as f:
            rows = f.readlines()
        board_height = len(rows)
        first_row = rows[0].strip().split("  ")
        board_width = len(first_row)
        board = [[BoardState.UNKNOWN for i in range(board_width)]
                 for j in range(board_height)]

        player = Player(x=0, y=0)
        other_players = []
        enemies = []

        for j in range(board_height):
            row = rows[j].split("  ")
            for i, r in enumerate(row):
                if r == '#':
                    board[j][i] = BoardState.WALL
                elif r == '_':
                    board[j][i] = BoardState.FREE
                elif r == "M":
                    player.x, player.y = i, j
                    board[j][i] = BoardState.FREE
                elif r == "E":
                    enemies.append(Enemy(i, j, is_neutral=False))
                    board[j][i] = BoardState.FREE
                elif r == 'O':
                    enemies.append(Enemy(i, j, is_neutral=True))
                    board[j][i] = BoardState.FREE
                elif r == 'P':
                    other_players.append(Player(i, j))
                    board[j][i] = BoardState.FREE
                else:
                    pass
        self.board = board
        self.player = player
        self.enemies = enemies
        self.other_players = other_players
        self.board_height = board_height
        self.board_width = board_width

    def print_game_board(self):
        def _print_cell(c):
            if c == BoardState.FREE:
                return "_"
            elif c == BoardState.WALL:
                return "#"
            else:
                return "X"

        rows = [list(map(lambda c: _print_cell(c), r)) for r in self.board]
        for p in self.other_players:
            rows[p.y][p.x] = "P"
        for e in self.enemies:
            if e.is_neutral:
                rows[e.y][e.x] = "O"
            else:
                rows[e.y][e.x] = "E"
        rows[self.player.y][self.player.x] = "M"
        rows = ["  ".join(r) for r in rows]
        bb = "\n".join(rows)
        print(bb)
        self.board_list.append(bb + "\n")

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

    def update(self, state):
        logger.info(
            "====================================Step: {}==============================================="
            .format(self.step))
        super().update(state)
        self.update_board(state)
        self.update_other_players(state)
        self.update_enemies(state)
        self.update_player(state)
        self.print_game_board()

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
            self.board = [[BoardState.UNKNOWN for i in range(size["width"])]
                          for j in range(size["height"])]
        if self.board_heatmap is None:
            self.board_heatmap = np.zeros((size["height"], size["width"]))

        # update visible area
        self.varea_x1 = area["x1"]
        self.varea_y1 = area["y1"]
        self.varea_x2 = area["x2"]
        self.varea_y2 = area["y2"]

        # init all visible area as free space
        for x in range(area["x1"], area["x2"] + 1):
            for y in range(area["y1"], area["y2"] + 1):
                self.board[y][x] = BoardState.FREE

        # update board if there are walls in visible area
        for w in wall:
            self.board[w["y"]][w["x"]] = BoardState.WALL

    def update_other_players(self, state):
        players = state["players"]
        self.other_players = [Player(x=p['x'], y=p['y']) for p in players]

    def update_enemies(self, state):
        enemies = state["enemies"]
        self.enemies = [
            Enemy(x=e['x'], y=e['y'], is_neutral=e["neutral"]) for e in enemies
        ]

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

    def can_shoot(self, agent_pos, action, target_pos):
        if not isinstance(action, FIREACTION):
            return False
        # first check if this shot is valid, e.g., two are in the same line
        if not action.can_shoot(agent_pos, target_pos):
            return False
        # then check if any walls between agent_pos and target_pos
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
        logger.info("=================Player position: {}===================".format((self.player.x, self.player.y)))
        self.player.can_shoot = player["fire"]
        self.player.positions.append((self.player.x, self.player.y))
        if self.short_range_x is None:
            self.short_range_x = max([
                abs(self.varea_x1 - self.player.x),
                abs(self.varea_x2 - self.player.x)
            ])
        if self.short_range_y is None:
            self.short_range_y = max([
                abs(self.varea_y1 - self.player.y),
                abs(self.varea_y2 - self.player.y)
            ])
        # update player positions heatmap
        self.board_heatmap += 1
        self.board_heatmap[self.player.y][self.player.x] = 0

    def update_after_player_action(self, action):
        super().update_after_player_action(action)
        self.player.actions.append(action)
        msg = "Player action: {}".format(str(action))
        print(msg)
        self.board_list.append(msg + "\n")

    def save(self, prefix):
        super().save(prefix)
        board_list_file = (Path(prefix) / "board_list.txt").open('w')
        board_list_file.writelines(self.board_list)

    def unknown_in_quadrant(self, position):
        """
        Divide the game board as four quadrant according to position.
        Then calculate how many unknown area in each quadrant
        """
        bx, by = position
        upper_left, upper_right, down_left, down_right = 0, 0, 0, 0
        for y in range(self.board_height):
            for x in range(self.board_width):
                if self.board[y][x] == BoardState.UNKNOWN:
                    if x < bx and y < by:
                        upper_left += 1
                    elif x < bx and y > by:
                        down_left += 1
                    elif x > bx and y < by:
                        upper_right += 1
                    else:
                        down_right += 1
        return [((-1, -1), upper_left), ((1, -1), upper_right),
                ((-1, 1), down_left), ((1, 1), down_right)]

    def bfs_walk(self, current_position, allow_diretion=None, target_position=None):
        """
        Do a breadth-first walk to find the shortest available path
        from <current_position> to <target_position>
        If target_position is None, <the target_position> will be the
        nearest unknown point

        Args:
            current_position: (x, y), base point
            allow_diretions: the allowed move directions for next point
            target_position: the target to reach, default None

        Returns:
            paths (list): a list of path points to reach the target position
            target_position: (x, y), the target position
        """
        seen_positions = set()
        step = 0
        positions_to_visit = deque([])
        positions_to_visit.append((current_position, step))
        # children => parent
        path_dict = {}

        while len(positions_to_visit) > 0:
            (x, y), current_step = positions_to_visit.popleft()
            if (x, y) in seen_positions:
                continue
            seen_positions.add((x, y))
            if target_position is None and self.board[y][x] == BoardState.UNKNOWN:
                # if the nearest target position is in our quadrant, chose it
                if allow_diretion is not None:
                    if (x - current_position[0]) * allow_diretion[0] >= 0 and\
                            (y - current_position[1]) * allow_diretion[1] >= 0:
                        target_position = (x, y)
                        break

            if (x, y) == target_position:
                break

            # add next search targets
            # bugfix: will not search a path with all unknown path
            if self.board[y][x] == BoardState.UNKNOWN:
                continue

            move_actions = list(MOVEACTION)
            shuffle(move_actions)
            for action in move_actions:
                if action == MOVEACTION.INVALID:
                    continue
                nx, ny = action.move(x, y)
                if (nx, ny) not in seen_positions and self.valid_pos(nx, ny):
                    positions_to_visit.append(((nx, ny), current_step + 1))
                    path_dict[(nx, ny)] = (x, y)

        paths = []
        # after reaching the target position,  get the paths
        logger.info("Player current position: {}".format(current_position))
        logger.info("Bfs walk: target position: {}".format(target_position))
        pos = target_position
        while pos != current_position:
            paths.append(pos)
            pos = path_dict[pos]
        logger.info("The paths are: {}".format(paths))
        return paths, target_position


if __name__ == '__main__':
    env = RecurrentEnvironment()
    env.load_game_from_file()
    env.print_game_board()
    env.bfs_walk((env.player.x, env.player.y), (1, -1))
