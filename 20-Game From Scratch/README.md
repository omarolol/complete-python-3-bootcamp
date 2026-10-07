# Dungeon Delve

A small turn-based roguelike written from scratch in plain Python (standard library only).

## Play

```bash
python dungeon_delve.py            # new random dungeon
python dungeon_delve.py --seed 42  # replay the same dungeon
```

Make your way down 5 randomly generated floors, defeat the dragon (`D`) on the last one
and pick up the Amulet of Yendor (`*`) to win.

## Controls

Type a command and press Enter. You can chain moves, e.g. `dddw`. A chain stops as soon
as something happens, such as a fight or finding an item.

| Key | Action |
| --- | --- |
| `w` `a` `s` `d` | Move (walk into a monster to attack it) |
| `>` | Go down the stairs |
| `p` | Drink a healing potion |
| `.` | Wait one turn |
| `h` | Help |
| `q` | Quit |

## Legend

`@` you, `>` stairs, `!` potion, `$` gold, `)` weapon (+1 attack), `[` armor (+1 defense), `*` amulet

Monsters get tougher the deeper you go: `r` rat, `b` bat, `g` goblin, `k` skeleton, `o` orc, `T` troll, `D` dragon.

## What's inside

The whole game lives in `dungeon_delve.py`:

- **Dungeon generation** (`Room`, `Level`): places non-overlapping rooms and joins them with L-shaped corridors
- **Entities** (`Creature`, `Player`, `Monster`): a small class hierarchy with combat, XP and leveling
- **Game loop** (`Game`): handles input, monsters chasing you, fog of war and drawing the map as text
