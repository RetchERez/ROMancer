"""What ROMancer knows about the levels of particular games: their enemies, items, secrets, block roles and length.

A profile reads a game's own tables (worked out from the game's code and proven by replaying the game) and turns them
into things on a level map. Edits are exact ROM writes; ROMancer checks each one by replaying the recorded walk with a
watcher the profile gives it. Games without a profile keep the general level map tools.

The interface every profile gives (see Profile):

* where(ram) -> {'part': {...}, 'x': camera x, 'y': camera y} or None: which part of the game a moment is in (a small
  dict such as {'stage': 1, 'floor': 0}) and where its camera is, in the part's own pixels
* objects(part) -> [object]: everything the profile knows in that part. An object is a dict with 'id' (unique in the
  part), 'style' ('enemy', 'item', 'secret' or 'block': how the map draws it), 'type' (for pictures), 'x', 'y' (the
  part's pixels, the object's bottom middle), 'name', optional 'detail' ("drops a dagger"), 'note', 'fields'
  ([{'key', 'label', 'value', 'choices'}], choices being a list of {'value', 'name'} or the name of a shared list in
  choices()) and 'remove' (the label of a remove button, or None)
* choices() -> {name: [{'value', 'name'}]}: lists that many objects share
* edit(part, object id, values, remove) -> {'writes': [(offset, old, new)], 'title', 'watch'}
* watcher(watch) -> Watcher: looks at the replayed game and says whether the change happened
* tile_role(tile) -> 'solid', 'breakable', 'open', or None when the profile has no block roles
* screens(part) -> {'count', 'most'} or None, and resize(part, at, delta) -> {'writes', 'notes', 'watch'}
"""
from __future__ import annotations

import hashlib


class Watcher:
    """Watches a replay of the recorded walk. `compare` asks for the original game to be replayed first as well."""
    every = 4           # frames between looks
    compare = False

    def see(self, ram, frame: int, run: str) -> bool:
        """Look at the game's RAM; True when the answer is known and the replay can stop. run is 'original' or 'changed'."""
        return False

    def result(self) -> dict:
        return {'state': 'warn', 'text': "The recorded walk didn't reach that part of the level, so the change couldn't be watched in the game."}


class Profile:
    name = ''
    sha256s: tuple = ()
    system = 'nes'

    def __init__(self, rom: bytes):
        self.rom = rom

    def where(self, ram):
        raise NotImplementedError

    def part_name(self, part: dict) -> str:
        return ', '.join(f'{k} {v}' for k, v in part.items())

    def objects(self, part: dict) -> list:
        return []

    def choices(self) -> dict:
        return {}

    def edit(self, part: dict, object_id: str, values: dict, remove: bool = False) -> dict:
        raise ValueError('ROMancer cannot change that yet.')

    def watcher(self, watch) -> Watcher:
        return Watcher()

    def tile_role(self, tile: int):
        return None

    def screens(self, part: dict):
        return None

    def resize(self, part: dict, at: int, delta: int) -> dict:
        raise ValueError('ROMancer cannot change the length of this game’s levels yet.')

    # helpers
    def find(self, part: dict, object_id: str) -> dict:
        found = next((o for o in self.objects(part) if o['id'] == object_id), None)
        if found is None:
            raise ValueError('That is not part of this level any more. Reopen the map.')
        return found

    @staticmethod
    def pick(field: dict, choices: dict, value):
        """Check that a value is one of a field's choices; returns the choice."""
        options = field['choices'] if isinstance(field['choices'], list) else choices.get(field['choices'], [])
        for option in options:
            if option['value'] == value:
                return option
        raise ValueError('That choice is not one of the game’s own.')


class Ram(bytes):
    """The game's work RAM (index 0 is the start of work RAM), with every other memory area of the moment in .domains
    (for example 'hram' and 'sram', cartridge RAM, on the Game Boy)."""
    domains: dict = {}


def ram_of(snapshot):
    data = next((snapshot.domains[n].data for n in ('wram', 'ram') if n in snapshot.domains and snapshot.domains[n].data is not None), None)
    if data is None:
        return None
    ram = Ram(data)
    ram.domains = {name: d.data for name, d in snapshot.domains.items() if d.data is not None}
    return ram


# one module per game (or family of games that share an engine); each has PROFILES = [classes]
GAMES = ['capcom_disney', 'castlevania', 'castlevania23', 'gb_adventure', 'megaman', 'smb1', 'smb3', 'sms_classics', 'zelda']


def _registry():
    import importlib
    import os
    games = []
    extra = [m for m in os.environ.get('ROMANCER_EXTRA_PROFILES', '').split(',') if m]    # profiles being written
    for module in GAMES + [m for m in extra if m not in GAMES]:
        games += importlib.import_module(f'.{module}', __name__).PROFILES
    return games


def profile_for(rom: bytes):
    digest = hashlib.sha256(rom).hexdigest()
    for kind in _registry():
        if digest in kind.sha256s:
            return kind(rom)
    return None


def known_games() -> list:
    return [kind.name for kind in _registry()]


# kept for older callers and tests
def __getattr__(name):
    if name in ('Castlevania', 'HEADER_NES'):
        from . import castlevania
        return getattr(castlevania, name)
    raise AttributeError(name)
