"""Documented console hardware is distinct from identified game music drivers."""
import copy

HARDWARE={'nes': {'name': '2A03 / 2A07 APU', 'nominal_channels': 5, 'channels': ['Pulse 1', 'Pulse 2', 'Triangle', 'Noise', 'DMC'], 'sample_formats': ['nes-dpcm'], 'notes': 'Region affects timing. Cartridge expansion audio requires separate mapper/core support.', 'references': ['https://www.nesdev.org/wiki/APU_Status', 'https://www.nesdev.org/wiki/APU_DMC']}, 'snes': {'name': 'SPC700 / S-SMP + S-DSP', 'nominal_channels': 8, 'channels': ['Sample voice ' + str(i + 1) for i in range(8)], 'sample_formats': ['snes-brr'], 'notes': 'Music driver runs on the SPC700. BRR samples alone do not describe notes, instruments or songs.', 'references': ['https://snes.nesdev.org/wiki/S-SMP', 'https://snes.nesdev.org/wiki/BRR_samples']}, 'genesis': {'name': 'YM2612 FM/DAC + VDP PSG', 'nominal_channels': 10, 'channels': ['FM ' + str(i + 1) for i in range(6)] + ['PSG tone 1', 'PSG tone 2', 'PSG tone 3', 'PSG noise'], 'sample_formats': ['pcm-u8', 'pcm-s8'], 'notes': 'DAC playback replaces FM channel 6. PCM signedness and packing depend on the driver; they are not inferred.', 'references': ['https://www.plutiedev.com/ym2612-registers', 'https://plutiedev.com/psg']}, 'gb': {'name': 'Game Boy APU', 'nominal_channels': 4, 'channels': ['Pulse 1', 'Pulse 2', 'Wave', 'Noise'], 'sample_formats': ['gb-wave4'], 'notes': 'Wave RAM stores 32 four-bit samples. Music sequencing and wave storage in ROM are driver-specific.', 'references': ['https://gbdev.io/pandocs/Audio.html', 'https://gbdev.io/pandocs/Audio_Registers.html']}}


HARDWARE['sms']={'name':'Master System PSG','nominal_channels':4,'channels':['Tone 1','Tone 2','Tone 3','Noise'],'sample_formats':[],'notes':'Four PSG channels are standard. Optional YM2413 FM hardware adds nine melodic voices, or six melodic voices plus five rhythm sounds. Its presence depends on console hardware and software detection; no game sequence decoder is implied.','optional_expansions':[{'name':'YM2413 FM','ports':[0xf0,0xf1,0xf2],'present_in_every_console':False}],'references':['https://www.smspower.org/Development/SN76489','https://www.smspower.org/Development/YM2413','https://github.com/mamedev/mame/blob/f34f02505e32c1993c6a782b6814232cbfc74e36/src/mame/sega/sms.cpp']}

HARDWARE['gbc']={**HARDWARE['gb'],'name':'Game Boy Color APU'}


def audio_system_info(system, source_sha256):
    if system not in HARDWARE:
        raise ValueError('audio knowledge is limited to NES, SNES, Genesis, Game Boy, Game Boy Color and Master System')
    driver = {'status': 'UNKNOWN', 'id': None, 'name': 'Unidentified game driver', 'reference': None}
    return {'ok': True, 'system_id': system, 'hardware': copy.deepcopy(HARDWARE[system]), 'driver': driver, 'sequence_edit_supported': False, 'native_mixed_audio_preview': True, 'limits': ['Console identification does not identify a music driver.', 'Sample codec support does not establish sample locations, playback rate, loops or instrument metadata.', 'Native mixed audio is not separated hardware channels.']}
