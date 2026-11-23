"""What ROMancer knows about the levels of particular games: their enemies, items, secrets and what their blocks do.

A profile reads the game's own tables (worked out from the game's code and proven by replaying the game) and turns them
into things on a level map. Edits are exact ROM writes; ROMancer checks each one by replaying the game.

Only games with a profile get these; every other game keeps the general level map tools.
"""
from __future__ import annotations

import hashlib

HEADER_NES = 16


class Castlevania:
    """Castlevania (USA). Spawn code: bank 7 $D10D / $D199. Items: $EB46. Collision: $F9B0.

    A stage is cut into zones of 64 pixels. Each zone has two bytes in the stage's zone table: an enemy index and a
    candle index. The indexes pick records from shared pools (enemy records at $D6A1; candle records at $D6A1, or
    $D7A1 for indexes of $80 and up). Records are shared between zones, so a change to one zone points it at another
    record and leaves the record alone.
    """
    name = 'Castlevania'
    sha256 = '55bcab0d9efc33a9d9efc90f2c3c4ab12f3221a44b1f357e6c6202a456399aa8'
    BANK7 = 0x1C000            # ROM offset (no header) of CPU $C000
    ZONE = 64
    ENEMIES = {0x01: 'Zombie', 0x04: 'Panther'}            # spawner types seen and identified in play
    UNSURE = {0x04}                                          # named from where it sits, not yet seen in a picture
    DROPS = {0x0: 'Heart or whip upgrade', 0x1: 'Money bag', 0x4: 'Large heart', 0x8: 'Dagger', 0x9: 'Cross',
             0xA: 'Rosary', 0xB: 'Holy water', 0xC: 'Double or triple shot', 0xD: 'Axe', 0xF: 'Stopwatch'}
    SOLID = range(0x60, 0x6C)
    BREAKABLE = {0x66}

    def __init__(self, rom: bytes):
        self.rom = rom

    # ---- reading
    def _at(self, address: int) -> int:
        return self.rom[HEADER_NES + self.BANK7 + (address - 0xC000)]

    def _word(self, address: int) -> int:
        return self._at(address) | self._at(address + 1) << 8

    def offset(self, address: int) -> int:
        """ROM file offset of a CPU address in the fixed bank."""
        return HEADER_NES + self.BANK7 + (address - 0xC000)

    def zone_table(self, stage: int, floor: int) -> int:
        return self._word(self._word(0xD26B + stage * 2) + floor * 2)

    def enemy_record(self, index: int):
        record = self._word(0xD6A1 + index * 2)
        kind = self._at(record)
        return None if not kind else {'type': kind, 'dx': self._at(record + 1), 'y': self._at(record + 2)}

    def candle_record(self, index: int):
        record = self._word((0xD7A1 if index & 0x80 else 0xD6A1) + ((index << 1) & 0xFF))
        first = self._at(record)
        if not first:
            return None
        drop, y = 0, 0
        if first == 0xFF:
            drop, y, first = self._at(record + 1), 2, self._at(record + 2)
        kind = 0x28 if first == 0xFE else 0x27
        if first == 0xFE:
            y += 1
        return {'type': kind, 'dx': self._at(record + y), 'y': self._at(record + y + 1), 'drop': drop, 'record': record}

    def zones(self, stage: int, floor: int, count: int = 64) -> list:
        table = self.zone_table(stage, floor)
        out = []
        for zone in range(count):
            enemy_index, candle_index = self._at(table + zone * 2), self._at(table + zone * 2 + 1)
            out.append({'zone': zone, 'enemy_index': enemy_index, 'candle_index': candle_index,
                        'enemy_byte': self.offset(table + zone * 2), 'candle_byte': self.offset(table + zone * 2 + 1),
                        'enemy': self.enemy_record(enemy_index), 'candle': self.candle_record(candle_index)})
        return out

    def drop_name(self, drop: int) -> str:
        low = drop & 0x0F
        return self.DROPS.get(low, f'Item {low:#04x}')

    def enemy_name(self, kind: int) -> str:
        name = self.ENEMIES.get(kind)
        if name is None:
            return f'Enemy {kind:#04x}'
        return name + (' (likely)' if kind in self.UNSURE else '')

    def objects(self, stage: int, floor: int, count: int = 64) -> list:
        """Every enemy and candle of a stage, in stage pixels (x from the stage start, y on the screen)."""
        out = []
        for row in self.zones(stage, floor, count):
            base = row['zone'] * self.ZONE
            if row['enemy']:
                e = row['enemy']
                out.append({'kind': 'enemy', 'zone': row['zone'], 'type': e['type'], 'name': self.enemy_name(e['type']),
                            'x': base + e['dx'], 'y': e['y'], 'index': row['enemy_index'], 'byte': row['enemy_byte']})
            if row['candle']:
                c = row['candle']
                out.append({'kind': 'candle', 'zone': row['zone'], 'type': c['type'],
                            'name': 'Candle' if c['type'] == 0x28 else 'Wall candle', 'drop': c['drop'],
                            'drop_name': self.drop_name(c['drop']), 'x': base + c['dx'], 'y': c['y'],
                            'index': row['candle_index'], 'byte': row['candle_byte'],
                            'shared': self.candle_users(stage, floor, row['candle_index'], count)})
        return out

    def candle_users(self, stage: int, floor: int, index: int, count: int = 64) -> int:
        table = self.zone_table(stage, floor)
        return sum(1 for zone in range(count) if self._at(table + zone * 2 + 1) == index)

    def tile_role(self, tile: int) -> str:
        if tile in self.BREAKABLE:
            return 'breakable'
        if tile in self.SOLID:
            return 'solid'
        return 'open'

    # ---- choices for edits (all point a zone at an existing record, so nothing else moves)
    def drop_choices(self, stage: int, floor: int, zone: int, count: int = 64) -> list:
        """Other candle records at the same place in their zone with a different drop: [{'index', 'drop', 'name'}]."""
        here = self.zones(stage, floor, count)[zone]['candle']
        if here is None:
            return []
        found, seen = [], set()
        for index in range(256):
            try:
                other = self.candle_record(index)
            except IndexError:
                continue
            if other and other['type'] == here['type'] and (other['dx'], other['y']) == (here['dx'], here['y']) and other['drop'] not in seen:
                seen.add(other['drop'])
                found.append({'index': index, 'drop': other['drop'], 'name': self.drop_name(other['drop'])})
        return found

    def enemy_choices(self) -> list:
        """Enemy records the game has: [{'index', 'type', 'name', 'dx', 'y'}], one per type and place."""
        found, seen = [], set()
        for index in range(1, 128):
            try:
                record = self.enemy_record(index)
            except IndexError:
                break
            if record and (record['type'], record['dx'], record['y']) not in seen:
                seen.add((record['type'], record['dx'], record['y']))
                found.append({'index': index, **record, 'name': self.enemy_name(record['type'])})
        return found


PROFILES = [Castlevania]


def profile_for(rom: bytes):
    digest = hashlib.sha256(rom).hexdigest()
    for kind in PROFILES:
        if kind.sha256 == digest:
            return kind(rom)
    return None
