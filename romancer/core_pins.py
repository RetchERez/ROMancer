"""Reviewed Windows x64 engines, sources, licenses and archive identities."""
CORE_ARCHIVE = {'file': 'ROMancer-v1.0.0-Engines.zip',
 'url': 'https://github.com/RetchERez/ROMancer/releases/download/v1.0.0/ROMancer-v1.0.0-Engines.zip',
 'sha256': 'f1f4684bdd8cf0d80a4bc377f5027faf66c2524092f3d05e63e41301d4217337'}
CORE_PINS = {'nes': {'name': 'FCEUmm',
         'file': 'fceumm_libretro.dll',
         'sha256': 'a1e86a7b82ecd153967b95cdb638126f2d0a2aba22cc698bacccf303a4296e40',
         'license': 'GPL-2.0',
         'source_url': 'https://github.com/libretro/libretro-fceumm',
         'source_commit': 'ac0d00a7fc01166f84c7bac01d1084ebfd2b865e',
         'source_directory': 'fceumm',
         'options': {}},
 'snes': {'name': 'bsnes-mercury Balanced',
          'file': 'bsnes_mercury_balanced_libretro.dll',
          'sha256': '9b790e5045a8807e8f6f36600015ce5fa1268c5f1267574144b6e8a3135365b0',
          'license': 'GPL-3.0',
          'source_url': 'https://github.com/libretro/bsnes-mercury',
          'source_commit': '79d7f9de218b6ffa65a80bbdc5828532bc239232',
          'source_directory': 'bsnes-mercury',
          'options': {'bsnes_chip_hle': 'HLE'}},
 'snes-dsp4': {'name': 'bsnes-mercury Balanced (DSP-4 states)',
               'file': 'bsnes_mercury_dsp4_libretro.dll',
               'sha256': 'f43b2c9de406f038482198dbc67848fdc27a1edf7145779fecbe3e5f9579c09d',
               'license': 'GPL-3.0',
               'source_url': 'https://github.com/libretro/bsnes-mercury',
               'source_commit': '79d7f9de218b6ffa65a80bbdc5828532bc239232',
               'source_directory': 'bsnes-mercury',
               'options': {'bsnes_chip_hle': 'HLE'},
               'romancer_patch': 'dsp4-state-v1'},
 'genesis': {'name': 'BlastEm',
             'file': 'blastem_libretro.dll',
             'sha256': '5f10162c6b2712454eedc564aaea924b588c8081f8ef592584f5703f9c0e5b63',
             'license': 'GPL-3.0',
             'source_url': 'https://github.com/libretro/blastem',
             'source_commit': 'ab743653ed110eeb7b1fe64d00cc5f9279c2bfec',
             'source_directory': 'blastem',
             'options': {},
             'romancer_patch': 'sms-input-state-v2'},
 'gb': {'name': 'Gambatte',
        'file': 'gambatte_libretro.dll',
        'sha256': 'eca7440670035fa1429d9903b20132ce0f964197341d3355979576a628234ead',
        'license': 'GPL-2.0',
        'source_url': 'https://github.com/libretro/gambatte-libretro',
        'source_commit': 'd9d6cd06382d1ced30de34d56d3609452323dab1',
        'source_directory': 'gambatte',
        'options': {'gambatte_gb_colorization': 'disabled', 'gambatte_gb_hwmode': 'GB'}},
 'gbc-tilt': {'name': 'mGBA (Game Boy Color tilt)',
              'file': 'mgba_gbc_libretro.dll',
              'sha256': 'eae97901714894e39ef03c940d7c8498bc15a330aa7e92575f5d78f3699320c3',
              'license': 'MPL-2.0',
              'source_url': 'https://github.com/libretro/mgba',
              'source_commit': '7a12d6d4b9acb14c0ae62c9166b6a2f3d08007f6',
              'source_directory': 'mgba',
              'options': {},
              'romancer_patch': 'gb-only-libretro-v1'}}
CORE_FILES = {'CORE-ORIGINS.json': {'size': 2575,
                       'sha256': '158d6a779f25a4dd70dcf48d237bd111f2ac8b69bbb6899adffebc8997ec8667'},
 'CORE-SOURCES.zip': {'size': 19204573,
                      'sha256': '3b2fc299d133d8e45c00e9a5360927387a92adf6b1a1631f56381e1f01adc2d5'},
 'THIRD_PARTY_NOTICES.txt': {'size': 3581,
                             'sha256': 'f85c7c2f23c946626fb689bd3ee68e7c3ea048d497ef67c08e1c802c5245cd22'},
 'blastem_libretro.dll': {'size': 11940158,
                          'sha256': '5f10162c6b2712454eedc564aaea924b588c8081f8ef592584f5703f9c0e5b63'},
 'bsnes_mercury_balanced_libretro.dll': {'size': 5505677,
                                         'sha256': '9b790e5045a8807e8f6f36600015ce5fa1268c5f1267574144b6e8a3135365b0'},
 'bsnes_mercury_dsp4_libretro.dll': {'size': 5521127,
                                     'sha256': 'f43b2c9de406f038482198dbc67848fdc27a1edf7145779fecbe3e5f9579c09d'},
 'fceumm_libretro.dll': {'size': 4096512,
                         'sha256': 'a1e86a7b82ecd153967b95cdb638126f2d0a2aba22cc698bacccf303a4296e40'},
 'gambatte_libretro.dll': {'size': 4598018,
                           'sha256': 'eca7440670035fa1429d9903b20132ce0f964197341d3355979576a628234ead'},
 'licenses/blastem.txt': {'size': 35821,
                          'sha256': '0b383d5a63da644f628d99c33976ea6487ed89aaa59f0b3257992deac1171e6b'},
 'licenses/bsnes-mercury.txt': {'size': 35793,
                                'sha256': '6b837c7a5f07d14add009cc2795823f47925a53dd59197eccb868bd520227c91'},
 'licenses/fceumm.txt': {'size': 18351,
                         'sha256': '1cfece9336f04ba05cd3b0d735599c090d38ea8d76ce56cc154c7faf84490599'},
 'licenses/gambatte.txt': {'size': 18326,
                           'sha256': '9f2e250993c6206fac643824e05e5a0d7d3e0895d9e09a5ce4b12bc2610afc11'},
 'licenses/mgba.txt': {'size': 17099,
                       'sha256': 'cde215e5b42363eb28ca2462c4558ff4807b38f383c537624c31e44657ac58f4'},
 'licenses/toolchain-crt-COPYING.MinGW-w64-runtime.txt.txt': {'size': 12155,
                                                              'sha256': '1db8da07b436c68833c0673ffee3d9fcb2526047f3820b81661865dfedc79a1f'},
 'licenses/toolchain-crt-COPYING.MinGW-w64.txt.txt': {'size': 5905,
                                                      'sha256': 'f38e6194bd3bfa1b654f118e5acefe0aead437bbe669eee43957ccc65a7127f1'},
 'licenses/toolchain-crt-COPYING.txt': {'size': 2326,
                                        'sha256': '99a69660981156c21336fdb5661f89341b013c94e4bf9e1c7467b4745718397f'},
 'licenses/toolchain-libgcc-COPYING.RUNTIME.txt': {'size': 3324,
                                                   'sha256': '9d6b43ce4d8de0c878bf16b54d8e7a10d9bd42b75178153e3af6a815bdc90f74'},
 'licenses/toolchain-libgcc-COPYING3.txt': {'size': 35147,
                                            'sha256': '8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903'},
 'licenses/toolchain-winpthreads-COPYING.txt': {'size': 2883,
                                                'sha256': '63263614cdd29f2f93cba85e992f041b31f9fc7b4033692f31269489a8a1b177'},
 'mgba_gbc_libretro.dll': {'size': 3179055,
                           'sha256': 'eae97901714894e39ef03c940d7c8498bc15a330aa7e92575f5d78f3699320c3'}}

# The catalog's recorded playtest proofs were measured with the Windows engines.
WINDOWS_CORE_PINS = CORE_PINS
WINDOWS_CORE_FILES = CORE_FILES


def _linux_engine_pack():
    """True only inside the Linux x86-64 release, whose engine folder carries its own marker."""
    import os
    import platform
    from pathlib import Path
    if os.name == 'nt' or platform.machine().lower() not in ('x86_64', 'amd64'):
        return False
    return (Path(__file__).resolve().parents[2] / 'cores' / 'LINUX-ENGINES.json').is_file()


if _linux_engine_pack():
    from .core_pins_linux import CORE_PINS, CORE_FILES  # noqa: F811
