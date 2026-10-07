"""
Dungeon Delve - a small turn-based roguelike written from scratch.

Only the Python standard library is used, so it runs anywhere:

    python dungeon_delve.py            # play
    python dungeon_delve.py --seed 42  # replay the same dungeon

Goal: descend through 5 randomly generated floors, defeat the dragon
guarding the bottom floor and grab the Amulet of Yendor ("*").
"""

import argparse
import random
import sys

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

MAP_W, MAP_H = 48, 18
MAX_DEPTH = 5
VIEW_RADIUS = 6

WALL, FLOOR, STAIRS = "#", ".", ">"

DIRECTIONS = {"w": (0, -1), "s": (0, 1), "a": (-1, 0), "d": (1, 0)}

# name, symbol, hp, attack, defense, xp, lowest depth it appears on
MONSTER_TYPES = [
    ("rat", "r", 4, 2, 0, 2, 1),
    ("bat", "b", 3, 3, 0, 2, 1),
    ("goblin", "g", 8, 4, 1, 5, 2),
    ("skeleton", "k", 12, 5, 2, 8, 3),
    ("orc", "o", 16, 6, 2, 12, 3),
    ("troll", "T", 26, 8, 3, 20, 4),
]
DRAGON = ("dragon", "D", 60, 11, 4, 100, MAX_DEPTH)

# symbol -> (name, description)
ITEM_TYPES = {
    "!": ("potion", "heals 12 HP"),
    "$": ("gold", "shiny coins"),
    ")": ("weapon", "+1 attack"),
    "[": ("armor", "+1 defense"),
}
AMULET = "*"


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

class Creature:
    def __init__(self, name, symbol, x, y, hp, attack, defense):
        self.name = name
        self.symbol = symbol
        self.x, self.y = x, y
        self.hp = self.max_hp = hp
        self.attack = attack
        self.defense = defense

    @property
    def alive(self):
        return self.hp > 0

    def hit(self, other, rng):
        """Attack another creature and return the damage dealt."""
        damage = max(1, self.attack - other.defense + rng.randint(-1, 1))
        other.hp -= damage
        return damage


class Player(Creature):
    def __init__(self, x, y):
        super().__init__("you", "@", x, y, hp=30, attack=5, defense=1)
        self.level = 1
        self.xp = 0
        self.gold = 0
        self.potions = 1
        self.has_amulet = False

    def xp_to_next(self):
        return self.level * 15

    def gain_xp(self, amount):
        """Add XP and return a list of level-up messages."""
        messages = []
        self.xp += amount
        while self.xp >= self.xp_to_next():
            self.xp -= self.xp_to_next()
            self.level += 1
            self.max_hp += 6
            self.hp = self.max_hp
            self.attack += 1
            if self.level % 2 == 0:
                self.defense += 1
            messages.append(f"You reach level {self.level}! You feel stronger.")
        return messages


class Monster(Creature):
    def __init__(self, kind, x, y):
        name, symbol, hp, attack, defense, xp, _ = kind
        super().__init__(name, symbol, x, y, hp, attack, defense)
        self.xp = xp
        self.awake = False


# ---------------------------------------------------------------------------
# Dungeon generation
# ---------------------------------------------------------------------------

class Room:
    def __init__(self, x, y, w, h):
        self.x1, self.y1 = x, y
        self.x2, self.y2 = x + w, y + h

    def center(self):
        return (self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2

    def intersects(self, other):
        return (self.x1 <= other.x2 + 1 and self.x2 + 1 >= other.x1 and
                self.y1 <= other.y2 + 1 and self.y2 + 1 >= other.y1)

    def random_point(self, rng):
        return rng.randint(self.x1, self.x2), rng.randint(self.y1, self.y2)


class Level:
    def __init__(self, depth, rng):
        self.depth = depth
        self.rng = rng
        self.tiles = [[WALL] * MAP_W for _ in range(MAP_H)]
        self.seen = [[False] * MAP_W for _ in range(MAP_H)]
        self.rooms = []
        self.monsters = []
        self.items = {}  # (x, y) -> symbol
        self._carve_rooms()

    # -- building ----------------------------------------------------------

    def _carve_rooms(self):
        rng = self.rng
        for _ in range(60):
            if len(self.rooms) >= 9:
                break
            w, h = rng.randint(4, 10), rng.randint(3, 5)
            x, y = rng.randint(1, MAP_W - w - 2), rng.randint(1, MAP_H - h - 2)
            room = Room(x, y, w, h)
            if any(room.intersects(r) for r in self.rooms):
                continue
            for ry in range(room.y1, room.y2 + 1):
                for rx in range(room.x1, room.x2 + 1):
                    self.tiles[ry][rx] = FLOOR
            if self.rooms:
                self._connect(self.rooms[-1].center(), room.center())
            self.rooms.append(room)

    def _connect(self, a, b):
        (x1, y1), (x2, y2) = a, b
        if self.rng.random() < 0.5:
            self._h_tunnel(x1, x2, y1)
            self._v_tunnel(y1, y2, x2)
        else:
            self._v_tunnel(y1, y2, x1)
            self._h_tunnel(x1, x2, y2)

    def _h_tunnel(self, x1, x2, y):
        for x in range(min(x1, x2), max(x1, x2) + 1):
            self.tiles[y][x] = FLOOR

    def _v_tunnel(self, y1, y2, x):
        for y in range(min(y1, y2), max(y1, y2) + 1):
            self.tiles[y][x] = FLOOR

    def populate(self, player):
        """Place the player, stairs/amulet, monsters and items."""
        rng = self.rng
        start, *others = self.rooms
        player.x, player.y = start.center()

        last = others[-1]
        goal = last.center()
        if self.depth < MAX_DEPTH:
            self.tiles[goal[1]][goal[0]] = STAIRS
        else:
            self.items[goal] = AMULET
            dx = 1 if goal[0] + 1 <= last.x2 else -1
            self.monsters.append(Monster(DRAGON, goal[0] + dx, goal[1]))

        kinds = [m for m in MONSTER_TYPES if m[6] <= self.depth]
        for room in others:
            for _ in range(rng.randint(0, 1 + self.depth // 2)):
                pos = self._free_spot(room)
                if pos:
                    self.monsters.append(Monster(rng.choice(kinds), *pos))
            for _ in range(rng.randint(0, 2)):
                pos = self._free_spot(room)
                if pos:
                    self.items[pos] = rng.choice("!!$$$)[")

    def _free_spot(self, room):
        for _ in range(20):
            x, y = room.random_point(self.rng)
            if (self.tiles[y][x] == FLOOR and (x, y) not in self.items
                    and self.monster_at(x, y) is None):
                return x, y
        return None

    # -- queries -----------------------------------------------------------

    def walkable(self, x, y):
        return 0 <= x < MAP_W and 0 <= y < MAP_H and self.tiles[y][x] != WALL

    def monster_at(self, x, y):
        for m in self.monsters:
            if m.alive and m.x == x and m.y == y:
                return m
        return None

    def is_edge_wall(self, x, y):
        """True for walls that touch a floor tile (the ones worth drawing)."""
        for ny in range(max(0, y - 1), min(MAP_H, y + 2)):
            for nx in range(max(0, x - 1), min(MAP_W, x + 2)):
                if self.tiles[ny][nx] != WALL:
                    return True
        return False

    def visible(self, px, py, x, y):
        return (x - px) ** 2 + (y - py) ** 2 <= VIEW_RADIUS ** 2

    def reveal(self, px, py):
        for y in range(max(0, py - VIEW_RADIUS), min(MAP_H, py + VIEW_RADIUS + 1)):
            for x in range(max(0, px - VIEW_RADIUS), min(MAP_W, px + VIEW_RADIUS + 1)):
                if self.visible(px, py, x, y):
                    self.seen[y][x] = True


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------

HELP = """\
Commands (press Enter after typing; you can chain moves like "ddds"):
  w a s d   move up / left / down / right (walk into monsters to attack)
  >         go down the stairs when standing on them
  p         drink a healing potion
  .         wait a turn
  h         show this help
  q         quit
Legend:
  @ you   > stairs   ! potion   $ gold   ) weapon   [ armor   * amulet
  r rat  b bat  g goblin  k skeleton  o orc  T troll  D dragon"""


class Game:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.player = Player(0, 0)
        self.messages = ["Welcome to Dungeon Delve! Type h for help."]
        self.turns = 0
        self.over = False
        self.won = False
        self.new_level(1)

    def new_level(self, depth):
        self.level = Level(depth, self.rng)
        self.level.populate(self.player)
        self.level.reveal(self.player.x, self.player.y)

    def log(self, text):
        self.messages.append(text)

    # -- player actions ----------------------------------------------------

    def handle(self, command):
        """Process one line of input. Returns False if the game should stop."""
        command = command.strip().lower()
        if not command:
            return True
        if command in ("q", "quit"):
            self.over = True
            self.log("You flee the dungeon.")
            return False
        if command in ("h", "help", "?"):
            self.log(HELP)
            return True

        for key in command:
            if self.over:
                break
            if key in DIRECTIONS:
                took_turn = self.move(*DIRECTIONS[key])
            elif key == ">":
                took_turn = self.descend()
            elif key == "p":
                took_turn = self.drink()
            elif key == ".":
                took_turn = True
            else:
                self.log(f"Unknown command '{key}'. Type h for help.")
                break
            if took_turn:
                self.end_turn()
            # Stop a chained move as soon as something interesting happens.
            if len(command) > 1 and self.messages:
                break
        return not self.over

    def move(self, dx, dy):
        p, lvl = self.player, self.level
        nx, ny = p.x + dx, p.y + dy
        target = lvl.monster_at(nx, ny)
        if target:
            self.attack(target)
            return True
        if not lvl.walkable(nx, ny):
            return False
        p.x, p.y = nx, ny
        self.pick_up()
        if lvl.tiles[ny][nx] == STAIRS:
            self.log("There are stairs leading down here. Press > to descend.")
        return True

    def attack(self, monster):
        dmg = self.player.hit(monster, self.rng)
        if monster.alive:
            self.log(f"You hit the {monster.name} for {dmg}.")
            return
        self.log(f"You slay the {monster.name}!")
        for msg in self.player.gain_xp(monster.xp):
            self.log(msg)

    def pick_up(self):
        p = self.player
        item = self.level.items.pop((p.x, p.y), None)
        if item == "!":
            p.potions += 1
            self.log("You pick up a healing potion.")
        elif item == "$":
            amount = self.rng.randint(5, 15) * self.level.depth
            p.gold += amount
            self.log(f"You find {amount} gold.")
        elif item == ")":
            p.attack += 1
            self.log("You find a sharper weapon. Attack +1.")
        elif item == "[":
            p.defense += 1
            self.log("You find sturdier armor. Defense +1.")
        elif item == AMULET:
            p.has_amulet = True
            self.won = self.over = True
            self.log("You grab the Amulet of Yendor! You win!")

    def descend(self):
        p = self.player
        if self.level.tiles[p.y][p.x] != STAIRS:
            self.log("There are no stairs here.")
            return False
        self.new_level(self.level.depth + 1)
        if self.level.depth == MAX_DEPTH:
            self.log("The air is hot. Something huge breathes in the dark...")
        else:
            self.log(f"You descend to depth {self.level.depth}.")
        return False

    def drink(self):
        p = self.player
        if p.potions == 0:
            self.log("You have no potions.")
            return False
        if p.hp == p.max_hp:
            self.log("You are already at full health.")
            return False
        p.potions -= 1
        healed = min(12, p.max_hp - p.hp)
        p.hp += healed
        self.log(f"You drink a potion and recover {healed} HP.")
        return True

    # -- world turn --------------------------------------------------------

    def end_turn(self):
        self.turns += 1
        p, lvl = self.player, self.level
        if self.over:
            return
        for m in lvl.monsters:
            if not m.alive:
                continue
            dist = abs(m.x - p.x) + abs(m.y - p.y)
            if dist <= VIEW_RADIUS:
                m.awake = True
            if not m.awake:
                continue
            if dist == 1:
                dmg = m.hit(p, self.rng)
                self.log(f"The {m.name} hits you for {dmg}.")
                if not p.alive:
                    self.over = True
                    self.log(f"You were killed by a {m.name} on depth {lvl.depth}.")
                    return
            else:
                self.step_toward(m, p.x, p.y)
        lvl.monsters = [m for m in lvl.monsters if m.alive]
        if self.turns % 10 == 0 and p.hp < p.max_hp:
            p.hp += 1  # slow natural regeneration
        lvl.reveal(p.x, p.y)

    def step_toward(self, m, tx, ty):
        lvl = self.level
        options = []
        if tx != m.x:
            options.append((m.x + (1 if tx > m.x else -1), m.y))
        if ty != m.y:
            options.append((m.x, m.y + (1 if ty > m.y else -1)))
        self.rng.shuffle(options)
        for nx, ny in options:
            if lvl.walkable(nx, ny) and not lvl.monster_at(nx, ny) and \
                    (nx, ny) != (self.player.x, self.player.y):
                m.x, m.y = nx, ny
                return

    # -- drawing -----------------------------------------------------------

    def render(self):
        p, lvl = self.player, self.level
        rows = []
        for y in range(MAP_H):
            row = []
            for x in range(MAP_W):
                in_view = lvl.visible(p.x, p.y, x, y)
                monster = lvl.monster_at(x, y) if in_view else None
                if (x, y) == (p.x, p.y):
                    ch = "@"
                elif monster:
                    ch = monster.symbol
                elif not lvl.seen[y][x]:
                    ch = " "
                elif lvl.tiles[y][x] == WALL and not lvl.is_edge_wall(x, y):
                    ch = " "
                elif (x, y) in lvl.items:
                    ch = lvl.items[(x, y)]
                else:
                    ch = lvl.tiles[y][x]
                row.append(ch)
            rows.append("".join(row))

        bar_len = 20
        filled = max(0, round(bar_len * p.hp / p.max_hp))
        hp_bar = "[" + "#" * filled + "-" * (bar_len - filled) + "]"
        status = (f"Depth {lvl.depth}/{MAX_DEPTH}  HP {max(p.hp, 0)}/{p.max_hp} {hp_bar}  "
                  f"Lvl {p.level} ({p.xp}/{p.xp_to_next()} xp)\n"
                  f"Atk {p.attack}  Def {p.defense}  Gold {p.gold}  "
                  f"Potions {p.potions}  Turn {self.turns}")
        return "\n".join(rows) + "\n" + status

    def flush_messages(self):
        text = "\n".join(self.messages)
        self.messages = []
        return text


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def play(seed=None, input_fn=input, output_fn=print):
    game = Game(seed)
    clear = "\033[2J\033[H" if sys.stdout.isatty() else "\n"
    while True:
        output_fn(clear + game.render())
        msgs = game.flush_messages()
        if msgs:
            output_fn(msgs)
        if game.over:
            break
        try:
            command = input_fn("> ")
        except (EOFError, KeyboardInterrupt):
            output_fn("\nGoodbye!")
            return game
        game.handle(command)

    p = game.player
    if game.won:
        score = p.gold + 500 + p.level * 50
        output_fn(f"\n*** VICTORY in {game.turns} turns! Score: {score} ***")
    else:
        score = p.gold + game.level.depth * 50 + p.level * 25
        output_fn(f"\n*** GAME OVER - Score: {score} ***")
    return game


def main():
    parser = argparse.ArgumentParser(description="Dungeon Delve - a tiny roguelike.")
    parser.add_argument("--seed", type=int, help="random seed for a repeatable dungeon")
    args = parser.parse_args()
    play(args.seed)


if __name__ == "__main__":
    main()
