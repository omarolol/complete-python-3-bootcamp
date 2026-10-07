"""
Build the browser version of Enemy Alien.

    python build_web.py

Reads story/*.txt with the same parser the terminal game uses and writes
web/enemy_alien.html: one self-contained page that plays the whole story in
any browser, including on a phone.
"""

import json
import os

import enemy_alien as ea

TEMPLATE = os.path.join(ea.HERE, "web", "template.html")
OUTPUT = os.path.join(ea.HERE, "web", "enemy_alien.html")


def cond_json(cond):
    return [[list(test) for test in group] for group in cond] if cond else None


def scene_json(scene):
    return {
        "chapter": scene.chapter,
        "effects": [list(e) for e in scene.effects],
        "paragraphs": [[cond_json(c), text] for c, text in scene.paragraphs],
        "choices": [[cond_json(c), label, target, [list(e) for e in eff]]
                    for c, label, target, eff in scene.choices],
        "gotos": [[cond_json(c), target] for c, target in scene.gotos],
        "end": scene.end,
    }


def main():
    scenes = ea.load_story()
    problems, _ = ea.check_story(scenes)
    if problems:
        raise SystemExit("Story has errors; run: python enemy_alien.py --check")
    data = {
        "start": ea.START_SCENE, "death": ea.DEATH_SCENE, "afterword": ea.AFTERWORD,
        "stats": ea.STATS, "max": ea.STAT_MAX, "note": ea.CONTENT_NOTE.replace("\n", " "),
        "scenes": {sid: scene_json(s) for sid, s in scenes.items()},
    }
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    with open(TEMPLATE, encoding="utf-8") as fh:
        page = fh.read().replace("/*STORY_JSON*/", blob)
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"Wrote {OUTPUT} ({len(page) // 1024} KB, {len(scenes)} scenes)")


if __name__ == "__main__":
    main()
