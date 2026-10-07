"""
Enemy Alien - an interactive story of a German civilian in France, 1939-1945.

    python enemy_alien.py            # play (offers to continue a saved game)
    python enemy_alien.py --new      # always start a new game
    python enemy_alien.py --check    # validate the story files
    python enemy_alien.py --fuzz     # play thousands of random games as a test

The story itself lives in story/*.txt, written in a small plain-text format
(see README.md). This file only reads that format and runs it.
"""

import argparse
import json
import os
import random
import re
import shutil
import sys
import textwrap
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STORY_DIR = os.path.join(HERE, "story")
SAVE_FILE = os.path.join(HERE, "savegame.json")

START_SCENE = "start"
DEATH_SCENE = "ending_health"
AFTERWORD = "afterword"  # shown after every ending
STATS = {"health": 10, "food": 6, "hope": 6, "money": 400}
STAT_MAX = {"health": 10, "food": 10, "hope": 10, "money": 99999}

CONTENT_NOTE = """\
Content note: this story is about civilians in the Second World War. It
depicts internment, hunger, bombing, torture, the deportation of Jewish
families and the massacre of civilians. The events are fictional but they
are drawn closely from history. It does not look away."""


# ---------------------------------------------------------------------------
# Story format
# ---------------------------------------------------------------------------

class StoryError(Exception):
    pass


class Scene:
    def __init__(self, sid, where):
        self.id = sid
        self.where = where
        self.chapter = None
        self.effects = []
        self.paragraphs = []  # list of (condition, text)
        self.choices = []     # list of (condition, text, target, effects)
        self.gotos = []       # list of (condition, target)
        self.end = False


COND_FLAG = re.compile(r"^(!?)([a-z][a-z0-9_]*)$")
COND_STAT = re.compile(r"^([a-z]+)(>=|<=|>|<|=)(-?\d+)$")
EFFECT_STAT = re.compile(r"^([a-z]+)([+\-=])(\d+)$")


def parse_condition(text, where):
    """'a & !b | money>=100' -> list of AND-groups (OR between groups)."""
    groups = []
    for part in text.split("|"):
        group = []
        for token in part.split("&"):
            token = token.strip()
            m = COND_STAT.match(token)
            if m and m.group(1) in STATS:
                group.append(("stat", m.group(1), m.group(2), int(m.group(3))))
                continue
            m = COND_FLAG.match(token)
            if m:
                group.append(("flag", m.group(2), m.group(1) == "!"))
                continue
            raise StoryError(f"{where}: bad condition '{token}'")
        groups.append(group)
    return groups


def parse_effects(text, where):
    effects = []
    for token in text.split():
        if token.startswith("set:") or token.startswith("unset:"):
            kind, name = token.split(":", 1)
            effects.append((kind, name))
            continue
        m = EFFECT_STAT.match(token)
        if not m or m.group(1) not in STATS:
            raise StoryError(f"{where}: bad effect '{token}'")
        effects.append(("stat", m.group(1), m.group(2), int(m.group(3))))
    return effects


def split_condition(text, where):
    """Split a leading '[condition]' off a line."""
    text = text.strip()
    if text.startswith("["):
        close = text.find("]")
        if close == -1:
            raise StoryError(f"{where}: missing ']'")
        return parse_condition(text[1:close], where), text[close + 1:].strip()
    return None, text


def load_story(directory=STORY_DIR):
    scenes = {}
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".txt"):
            continue
        with open(os.path.join(directory, name), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        scene = None
        para = None  # [condition, [lines]]

        def flush():
            nonlocal para
            if para and scene is not None:
                scene.paragraphs.append((para[0], " ".join(para[1])))
            para = None

        for num, raw in enumerate(lines, 1):
            where = f"{name}:{num}"
            line = raw.strip()
            if line.startswith("== "):
                flush()
                sid = line[3:].strip()
                if sid in scenes:
                    raise StoryError(f"{where}: duplicate scene '{sid}'")
                scene = scenes[sid] = Scene(sid, where)
                continue
            if line.startswith("#") and not line.startswith("##"):
                continue  # comment
            if scene is None:
                if line:
                    raise StoryError(f"{where}: text outside a scene")
                continue
            if not line:
                flush()
            elif line.startswith("## "):
                flush()
                scene.chapter = line[3:].strip()
            elif line.startswith("@ "):
                flush()
                scene.effects += parse_effects(line[2:], where)
            elif line.startswith("* "):
                flush()
                cond, rest = split_condition(line[2:], where)
                if " -> " not in rest:
                    raise StoryError(f"{where}: choice without '->'")
                label, target = rest.rsplit(" -> ", 1)
                effects = []
                if " @ " in target:
                    target, eff = target.split(" @ ", 1)
                    effects = parse_effects(eff, where)
                scene.choices.append((cond, label.strip(), target.strip(), effects))
            elif line.startswith("-> "):
                flush()
                cond, target = split_condition(line[3:], where)
                scene.gotos.append((cond, target))
            elif line == "END":
                flush()
                scene.end = True
            elif line.startswith("? "):
                flush()
                if " : " not in line:
                    raise StoryError(f"{where}: conditional text needs ' : '")
                cond_text, text = line[2:].split(" : ", 1)
                para = [parse_condition(cond_text, where), [text.strip()]]
            else:
                if para is None:
                    para = [None, []]
                para[1].append(line)
        flush()
    return scenes


# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------

class State:
    def __init__(self):
        self.scene = START_SCENE
        self.stats = dict(STATS)
        self.flags = set()
        self.chapter = None
        self.visited = 0
        self.entered = False  # effects of the current scene applied?

    def check(self, cond):
        if cond is None:
            return True
        for group in cond:
            ok = True
            for test in group:
                if test[0] == "flag":
                    _, name, negate = test
                    if (name in self.flags) == negate:
                        ok = False
                else:
                    _, stat, op, value = test
                    v = self.stats[stat]
                    if not {">=": v >= value, "<=": v <= value, ">": v > value,
                            "<": v < value, "=": v == value}[op]:
                        ok = False
            if ok:
                return True
        return False

    def apply(self, effects):
        for eff in effects:
            if eff[0] == "set":
                self.flags.add(eff[1])
            elif eff[0] == "unset":
                self.flags.discard(eff[1])
            else:
                _, stat, op, value = eff
                v = self.stats[stat]
                v = v + value if op == "+" else v - value if op == "-" else value
                self.stats[stat] = max(0, min(STAT_MAX[stat], v))

    def to_json(self):
        return {"scene": self.scene, "stats": self.stats,
                "flags": sorted(self.flags), "chapter": self.chapter,
                "visited": self.visited, "entered": self.entered}

    @classmethod
    def from_json(cls, data):
        s = cls()
        s.scene = data["scene"]
        s.stats.update(data["stats"])
        s.flags = set(data["flags"])
        s.chapter = data.get("chapter")
        s.visited = data.get("visited", 0)
        s.entered = data.get("entered", False)
        return s


def enter_scene(state, scene):
    """Apply a scene's automatic effects. Returns extra narration lines."""
    notes = []
    state.visited += 1
    state.entered = True
    if scene.chapter:
        state.chapter = scene.chapter
        if scene.chapter.startswith("Part"):
            # Months pass between parts: the larder empties, wounds heal or don't.
            if state.stats["food"] > 0:
                state.stats["food"] -= 1
                if state.stats["food"] >= 4 and state.stats["health"] < 10:
                    state.stats["health"] += 1
                    notes.append("You have eaten well enough to mend a little.")
            else:
                state.stats["health"] = max(0, state.stats["health"] - 2)
                notes.append("Months of hunger have worn you down.")
    state.apply(scene.effects)
    return notes


def next_targets(state, scene):
    """Gotos the state can follow (first one wins) or available choices."""
    gotos = [t for c, t in scene.gotos if state.check(c)]
    choices = [ch for ch in scene.choices if state.check(ch[0])]
    return gotos, choices


# ---------------------------------------------------------------------------
# Terminal interface
# ---------------------------------------------------------------------------

def width():
    return min(78, shutil.get_terminal_size((80, 24)).columns - 2)


def out(text="", slow=False):
    if not slow:
        print(text)
        return
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(0.008)
    print()


def wrap(text):
    return textwrap.fill(text, width())


def bar(value, maximum=10):
    return "█" * value + "·" * (maximum - value)


def status_line(state):
    s = state.stats
    return (f"Health {bar(s['health'])}  Food {bar(s['food'])}  "
            f"Hope {bar(s['hope'])}  {s['money']} francs")


def save(state):
    with open(SAVE_FILE, "w", encoding="utf-8") as fh:
        json.dump(state.to_json(), fh)


def ask(prompt):
    try:
        return input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return "q"


def show_scene(state, scene, notes, slow):
    if scene.chapter:
        w = width()
        out("\n" + "═" * w)
        out(scene.chapter.upper().center(w))
        out("═" * w)
    out()
    for note in notes:
        out(wrap(f"({note})"))
        out()
    for cond, text in scene.paragraphs:
        if state.check(cond):
            out(wrap(text), slow)
            out()


def play(scenes, state, slow=False):
    while True:
        scene = scenes[state.scene]
        notes = []
        if not state.entered:
            notes = enter_scene(state, scene)
            if scene.chapter:
                save(state)
        if state.stats["health"] <= 0 and not scene.end and state.scene != DEATH_SCENE \
                and DEATH_SCENE in scenes:
            show_scene(state, scene, notes, slow)
            state.scene = DEATH_SCENE
            state.entered = False
            continue
        show_scene(state, scene, notes, slow)

        if scene.end:
            if os.path.exists(SAVE_FILE):
                os.remove(SAVE_FILE)
            out("─" * width())
            out("THE END".center(width()))
            out()
            if AFTERWORD in scenes:
                for _, text in scenes[AFTERWORD].paragraphs:
                    out(wrap(text))
                    out()
            return

        gotos, choices = next_targets(state, scene)
        if gotos:
            if ask("[Enter] continue · s save · q quit > ") in ("q", "quit"):
                save(state)
                out("Game saved. Run the game again to continue.")
                return
            state.scene = gotos[0]
            state.entered = False
            continue

        out(status_line(state))
        out()
        for i, (_, label, _, _) in enumerate(choices, 1):
            out(textwrap.fill(f"  {i}. {label}", width(), subsequent_indent="     "))
        while True:
            answer = ask("\nChoose (number · s save · q quit) > ")
            if answer in ("q", "quit"):
                save(state)
                out("Game saved. Run the game again to continue.")
                return
            if answer == "s":
                save(state)
                out("Saved.")
                continue
            if answer.isdigit() and 1 <= int(answer) <= len(choices):
                _, _, target, effects = choices[int(answer) - 1]
                state.apply(effects)
                state.scene = target
                state.entered = False
                break
            out("Type the number of a choice.")


# ---------------------------------------------------------------------------
# Story checks (for writers)
# ---------------------------------------------------------------------------

def check_story(scenes):
    problems, warnings = [], []
    used_flags, set_flags = set(), set()

    def note_cond(cond):
        for group in cond or []:
            for test in group:
                if test[0] == "flag":
                    used_flags.add(test[1])

    def note_eff(effects):
        for eff in effects:
            if eff[0] in ("set", "unset"):
                set_flags.add(eff[1])

    for s in scenes.values():
        note_eff(s.effects)
        for cond, _ in s.paragraphs:
            note_cond(cond)
        for cond, _, target, eff in s.choices:
            note_cond(cond)
            note_eff(eff)
            if target not in scenes:
                problems.append(f"{s.where}: '{s.id}' links to missing scene '{target}'")
        for cond, target in s.gotos:
            note_cond(cond)
            if target not in scenes:
                problems.append(f"{s.where}: '{s.id}' links to missing scene '{target}'")
        if s.end and (s.choices or s.gotos):
            problems.append(f"{s.where}: END scene '{s.id}' also has exits")
        if not s.end and not s.choices and not s.gotos and s.id != AFTERWORD:
            problems.append(f"{s.where}: scene '{s.id}' is a dead end")
        if s.gotos and s.gotos[-1][0] is not None:
            problems.append(f"{s.where}: last '->' in '{s.id}' must be unconditional")
        if s.choices and s.gotos:
            problems.append(f"{s.where}: '{s.id}' mixes choices and '->'")
        if s.choices and all(c[0] is not None for c in s.choices):
            problems.append(f"{s.where}: '{s.id}' needs one unconditional choice")
        if not s.paragraphs:
            warnings.append(f"{s.where}: scene '{s.id}' has no text")

    for flag in sorted(used_flags - set_flags):
        problems.append(f"flag '{flag}' is tested but never set (typo?)")
    for flag in sorted(set_flags - used_flags):
        warnings.append(f"flag '{flag}' is set but never tested")

    if START_SCENE not in scenes:
        problems.append(f"missing start scene '{START_SCENE}'")
    else:
        seen, todo = set(), [START_SCENE, DEATH_SCENE, AFTERWORD]
        while todo:
            sid = todo.pop()
            if sid in seen or sid not in scenes:
                continue
            seen.add(sid)
            s = scenes[sid]
            todo += [t for _, t in s.gotos] + [c[2] for c in s.choices]
        for sid in scenes:
            if sid not in seen:
                warnings.append(f"{scenes[sid].where}: scene '{sid}' is unreachable")
    return problems, warnings


def word_count(scenes):
    return sum(len(t.split()) for s in scenes.values() for _, t in s.paragraphs)


def fuzz(scenes, games=5000, seed=1):
    """Play random games to make sure every path ends and nothing crashes."""
    rng = random.Random(seed)
    endings, seen, longest = {}, set(), 0
    for _ in range(games):
        state = State()
        for step in range(3000):
            scene = scenes[state.scene]
            seen.add(state.scene)
            enter_scene(state, scene)
            if state.stats["health"] <= 0 and not scene.end and state.scene != DEATH_SCENE:
                state.scene = DEATH_SCENE
                continue
            if scene.end:
                endings[state.scene] = endings.get(state.scene, 0) + 1
                break
            gotos, choices = next_targets(state, scene)
            if gotos:
                state.scene = gotos[0]
            elif choices:
                _, _, target, eff = rng.choice(choices)
                state.apply(eff)
                state.scene = target
            else:
                raise StoryError(f"stuck in '{state.scene}' with no available choice")
        else:
            raise StoryError("a game never ended (loop?)")
        longest = max(longest, step)
    return endings, seen, longest


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--new", action="store_true", help="ignore any saved game")
    parser.add_argument("--slow", action="store_true", help="typewriter-style text")
    parser.add_argument("--check", action="store_true", help="validate the story")
    parser.add_argument("--fuzz", action="store_true", help="play random test games")
    args = parser.parse_args()

    scenes = load_story()

    if args.check or args.fuzz:
        problems, warnings = check_story(scenes)
        for w in warnings:
            print("warning:", w)
        for p in problems:
            print("ERROR:", p)
        print(f"{len(scenes)} scenes, {word_count(scenes):,} words.")
        if problems:
            sys.exit(1)
        if args.fuzz:
            endings, seen, longest = fuzz(scenes)
            print(f"Random games reached {len(seen)}/{len(scenes)} scenes; "
                  f"longest game {longest} steps.")
            for name, n in sorted(endings.items(), key=lambda kv: -kv[1]):
                print(f"  {name:28} {n}")
        return

    state = None
    if not args.new and os.path.exists(SAVE_FILE):
        if ask("A saved game was found. Continue it? [Y/n] > ") in ("", "y", "yes"):
            with open(SAVE_FILE, encoding="utf-8") as fh:
                state = State.from_json(json.load(fh))
            if state.scene not in scenes:
                out("The saved game no longer matches the story; starting over.")
                state = None
    if state is None:
        out()
        out("ENEMY ALIEN".center(width()))
        out("A story of Paris, 1939–1945".center(width()))
        out()
        out(CONTENT_NOTE)
        out()
        if ask("[Enter] begin · q quit > ") in ("q", "quit"):
            return
        state = State()
    play(scenes, state, args.slow)


if __name__ == "__main__":
    main()
