"""Reviewed optional Windows native observers, complete source and notices.

Only the patched MesenCE observer is bundled. MAME 0.289 is the unmodified
official build, so it is prepared on first use from its pinned upstream release
(see debugger_provision.py) instead of being redistributed in the portable ZIP."""
OBSERVER_FAMILIES = ['MesenCE 2.2.1 + physical-ppu-access-v2']
OBSERVER_FILES = {'mesence-2.2.1/backend.json': {'size': 551,
                                'sha256': '64ef0ba00af40504f9581b667a210bde12363cb03812ad58da5bd173ca0d170d'},
 'mesence-2.2.1/COPYING': {'size': 35147,
                           'sha256': '8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903'},
 'mesence-2.2.1/corresponding-source.zip': {'size': 4432763,
                                            'sha256': '0f54e859a0a2a1b15469f4c0a1e58af630c268ed344803508f45de0727cb5b90'},
 'mesence-2.2.1/libHarfBuzzSharp.dll': {'size': 1804872,
                                        'sha256': 'eb76238c9e8e41d44b5a5b18167c4c5b39ca5db4277af5dbe92d730f0fc14a7d'},
 'mesence-2.2.1/libSkiaSharp.dll': {'size': 9414216,
                                    'sha256': '9a0d95e8caaa852c70d085af6a40a744242172ad9ea3fd6bc7599875a8a1dbcd'},
 'mesence-2.2.1/Mesen.exe': {'size': 70753792,
                             'sha256': '8ef403d6b9af32075416193914d7993ce8480b347fe1f20a0cfd9815374933e7'},
 'mesence-2.2.1/MesenCore.dll': {'size': 7239680,
                                 'sha256': '62e4c8a1b152e8d94adeb54335e1b0966c38c1f26db2ae4007b1a5e558077445'},
 'mesence-2.2.1/MesenNesDB.txt': {'size': 559276,
                                  'sha256': '200e19903f1b2eeda1f59a7f3bcdacf388d0f8d228f6f842373477ddc2f5a3e1'},
 'mesence-2.2.1/README.txt': {'size': 1488,
                              'sha256': 'bf0e5bacf7fbaee27266680f1292c0b7862e047585bea94444e5174901d0cc8e'},
 'mesence-2.2.1/romancer-graphics.patch': {'size': 6119,
                                           'sha256': 'e70be91b2978fb19e06eb2886d454b5c26d78c4471af8bd5ef390a1e13095c79'},
 'mesence-2.2.1/source-snapshot.zip': {'size': 4423524,
                                       'sha256': 'a16a880173d73c8320ad15203e9e69b59e0789da0fe8cf5358ec33c1b92b2886'}}
