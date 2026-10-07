# Enemy Alien

*An interactive story of Paris, 1939–1945.*

You are Emil Brandt, a German bookbinder who fled Hitler in 1933 and lives in Paris
with his French wife Madeleine and their daughter Josette. When war is declared, France
locks you up as an enemy alien. When France falls, the Nazis come looking for you.
Between the two, you have to decide every day what you're willing to risk, and for whom:
your family, your Jewish neighbours the Lewins, your friend Lucien the printer, your
brother Kurt in a Wehrmacht uniform.

The story runs from September 1939 to May 1945 and beyond: internment in the brickworks
at Les Milles, the exodus of June 1940, the occupation, the Vel d'Hiv roundup, the Allied
bombing of Billancourt, the Gestapo, Le Chambon-sur-Lignon, Oradour-sur-Glane, the
liberation of Paris and the return of the deportees.

It is long, about **44,000 words** across **213 scenes**, with dozens of choices that carry
forward. There is one main ending with many possible outcomes depending on who you saved
and what you did, plus five early endings.

> **Content note:** the story depicts internment, hunger, bombing, torture, the deportation
> of Jewish families and the massacre of civilians. The characters are fictional but the
> events are historical.

## Play on a phone or in a browser

Open `web/enemy_alien.html` in any browser. It's a single self-contained page with the
whole story, and it saves your progress in the browser. If you edit the story files,
rebuild it with:

```bash
python build_web.py
```

## Play in a terminal

Only the Python standard library is needed (Python 3.8+).

```bash
python enemy_alien.py          # play, offering to continue a saved game if there is one
python enemy_alien.py --new    # start over
python enemy_alien.py --slow   # typewriter-style text
```

Type the number of a choice. Press `s` to save and `q` to save and quit. The game also
saves automatically at each new chapter.

You track four things: **Health**, **Food**, **Hope** and **francs**. Food runs down as
months pass, and going hungry wears down your health. Hope affects what you can still
bring yourself to do when it matters.

## How it's built

- `enemy_alien.py` is a small engine (parser, game state, terminal UI, save/load) and
  story checker.
- `story/*.txt` holds the whole story, one file per part, in a plain-text format:

```text
== scene_id                 start a scene
## Chapter title            show a chapter heading (autosave point)
@ food-1 hope+2 set:flag    effects applied when the scene is entered
Plain lines are prose. A blank line starts a new paragraph.
? flag & money>=100 : text  a paragraph shown only if the condition holds
* Choice text -> target @ set:other_flag    a choice (optional [condition] before it)
-> [condition] target       automatic continue (first matching line wins)
END                         an ending
```

Conditions use flags (`flag`, `!flag`), stats (`hope>=4`), `&` (and) and `|` (or).

For writers, two commands check the story:

```bash
python enemy_alien.py --check  # broken links, dead ends, typo'd flags, unreachable scenes
python enemy_alien.py --fuzz   # plays 5,000 random games and reports the endings reached
```
