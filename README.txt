ROMancer v1.0 final
By RetchEWretched

Local ROM editing for NES, SNES, Genesis, Game Boy and GBA.
Everyday use works offline. No AI account, model, API key or subscription is required.

START ON WINDOWS

1. Extract the entire Windows ZIP.
2. Run Install ROMancer.cmd, then open the ROMancer desktop shortcut.
3. Open an original workshop or choose New project and import your own cartridge image.

Python and Pillow are included in the Windows x64 package. Edge provides the
desktop window; Open in browser is available if the window cannot open.
The launchers are unsigned. No emulator cores, games, BIOS files or saves are
included. Choose a compatible local x64 libretro core in Playtest to run a ROM.
Editing and patching do not require an emulator core.

Installed projects: %LOCALAPPDATA%\ROMancer\workspace
Upgrades retain projects and prior versions. Rollback restores the previous
launcher. Uninstall preserves projects and installed versions for recovery.

SET UP PLAYTESTING

Editing works without a core. To play a game, use a Windows x64 libretro DLL
for its system. A standalone emulator EXE is not a libretro core.

1. Obtain and extract the core from its official project or Libretro distribution.
   Keep the DLL in a permanent local folder outside the ROMancer version folder.
2. Open your project and select its source or edited build, then choose Playtest.
3. Choose Find local cores and Use the matching result. If none is found, open
   Advanced setup, choose System, enter the core DLL path, then Save system setup.
4. Choose Check setup, then load the selected content and press Play.
   Setup checks identities; the displayed game confirms the loaded content runs.
5. Pause before saving or loading a state. States belong to the exact ROM build,
   core and runtime setup; start a fresh session after changing those inputs.
   Ordinary battery saves use their separate save controls and backups.

Official core guides:
  NES:      https://docs.libretro.com/library/fceumm/
  SNES:     https://docs.libretro.com/library/snes9x/
  Genesis:  https://docs.libretro.com/library/picodrive/
  Game Boy: https://docs.libretro.com/library/gambatte/
  GBA:      https://docs.libretro.com/library/mgba/

Tested Windows x64 builds (versions reported by the tested DLLs):
  NES       FCEUmm    (SVN) ac0d00a          fceumm_libretro.dll
  SNES      Snes9x    1.63 fae2fea           snes9x_libretro.dll
  Genesis   PicoDrive 2.05-1890c29           picodrive_libretro.dll
  Game Boy  Gambatte  v0.5.0-netlink d9d6cd0 gambatte_libretro.dll
  GBA       mGBA      0.11-212-7a12d6d       mgba_libretro.dll

The Game Boy checks used gambatte_gb_colorization=disabled and
  gambatte_gb_hwmode=GB. Other listed core setups used default options.
These checks used original workshop programs; exact commercial builds have
separate recorded evidence. They do not certify every game or every core build.
Newer downloads can differ. ROMancer measures the selected file and refuses a
saved setup if that file changes; review and save the new setup before use.
No core, game or firmware is included in ROMancer's distribution.

Exact tested DLL SHA-256 fingerprints:
  FCEUmm:    8291db091bc7ededebaf0f42f4e2323f802c5fd6378406f187998252e2a2722f
  Snes9x:    d5e144475deeb22d152d1e28a2649f5a53092a65c9ec204c6f5d97968f30f139
  PicoDrive: fce9f710ef3b49e81121a2b3f4e10ea0780474f0916ecd0e9a4f0d8ace3f5201
  Gambatte:  fd3093a2154e8d11dd470aac8c1e00528cb2fc7ef31a697d02adb87fc5186ac4
  mGBA:      a7e52babbf6b7782615ae1ba6d51038b0938dd3dd1d446b6c4dfe8ac002fa648

YOUR FIRST EDIT

Import creates an owned source copy and starts an offline investigation.
Original files are never edited. Select a known resource, stage a change,
review its exact bytes, and create a separate build. Select that build in the
source/build selector to playtest it. Export a verified BPS patch to share.
Downloaded BPS and IPS patches can also be applied to a separate build.
BPS includes checksums. IPS requires an external original-source reference.

Help -> Tutorials contains short Basic and Advanced lessons. Completed lessons
receive a green check; skipped lessons do not. The first-launch tutorial prompt
can be disabled and the tutorials can always be reopened from Help.

WHAT IS SUPPORTED

- Interactive hex editing, wildcard/text/integer searches and named bookmarks.
- Declared text editing with protected control codes, capacity checks and CSV/TSV.
- Named numeric tables, explicit byte order and reviewed batch/percentage changes.
- Tiles, palettes, fonts, tilemaps and assembled sprites with stroke undo/redo.
- Live original/edited sprite, tile and room comparisons with change markers.
- Palette color picker with before/after swatches and declared color quantization.
- Live text/capacity and numeric comparisons with explicit preview status.
- Explicit animation-frame layouts and shared-tile information.
- Declared fixed-capacity terrain, metatiles, collision values and object fields.
- Tested PCM8/16, Game Boy wave, NES DPCM and standalone SNES BRR sample codecs.
- Sample gain/reverse/silence/WAV replacement and play/pause/seek previews.
- Documented console sound hardware, evidence-scoped driver identification,
  and native mixed-audio recording through a configured core.
- Native playtesting, gamepad/keyboard controls, battery-save backups and states.
- Source/session/core/state-bound RAM narrowing and available video-memory tiles.
- Build history, byte comparisons, recorded tests and screenshot checkpoints.
- ROM health, CRC comparison, supported checksum repair and project validation.
- Local hash-catalog import, source-bound resource relationships and support reports.
- Recoverable project deletion, private backup/restore and persisted editor drafts.

FACTS, DEFINITIONS AND LIMITS

Known: exact revision identity or documented binary/system format.
Declared: a source-bound layout supplied by the user and checked by the editor.
Candidate: a structural or pixel observation whose game use has not been proven.
Unknown: no supported interpretation has been established.

A deep scan cannot understand every game. A regular byte pattern is not proof
of a level, enemy stat, animation or song. A changed RAM value does not identify
the instruction that wrote it or the corresponding ROM location. CPU addresses,
ROM file offsets and core memory-region offsets are different address spaces.
Only explicit supported mappings translate between them.

Preview status distinguishes updated, unchanged and unavailable results. Editing
previews are staged; review the changes and create a separate build to save them.
Generic text comparisons use the system font. An exact game font/window needs a
declared layout or a native playtest. Numeric comparisons show stored values,
not inferred damage or gameplay formulas. Palette colors use the declared bit
ranges; the picker may quantize a chosen color to the supported hardware format.

Sound hardware is not a music driver. The exact original Wario Land 4 US/EU
revision is documented as m4a/MusicPlayer2000, but a commercial sequence decoder
is not implemented. Note editing currently supports only the identified original
Hillside workshop driver. Sample editing requires a declared location, capacity
and codec. DPCM/wave/BRR re-encoding is lossy. Reference previews do not reproduce
hardware filters, envelopes, echo or a game's mixer. Native recordings contain
measured mixed output, not isolated hardware channels.

Declared rooms and object fields use existing fixed storage. They do not add a
game engine, infer collision meanings or allocate new rooms. Unsupported layouts,
compression and drivers remain unavailable. Original workshops are redistributable
practice programs; their behavior is tested separately from commercial games.

CRC32 is calculated for the selected file or payload scope. A mismatch requires
an expected reference for that same scope. Without a reference, comparison is
unknown. Console checksums, CRC32 and SHA-256 serve different purposes.

Save states are tied to exact ROM, core and runtime identities. Battery saves
are separate ordinary game-save data. A core may omit states, saves or video RAM.
Keep backups before changing ROM/core versions. Test results cover only their
recorded inputs and assertions; untested gameplay remains unknown.

SOURCE SETUP

Use 64-bit Python 3.13 or 3.14 and the pinned requirements.

Windows PowerShell, from the source folder:
  py -3.14 -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  .venv\Scripts\python.exe -B -m romancer.workbench_server

Linux, from the source folder:
  python3.14 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
  .venv/bin/python -B -m romancer.workbench_server

The server prints its local address and opens a browser. Keep it running while
using the application. --workspace PATH chooses a project directory. Source mode
otherwise uses ~/Documents/ROMancer Projects. Linux native cores must be x86_64
ELF libraries. macOS and ARM native execution are not supported.

The generated UI is included; Node is not needed to run the application.
For UI development use Node 24: npm ci, npm run build, npm test.
Initial dependency installation requires internet access.

BUILD AND CHECK

Run from the source folder:
  python -B -m unittest discover -s tests
  npm ci
  npm run build
  npm test
  python -B tools/package_source.py . dist/source.zip
  python -B tools/audit_release.py --source dist/source.zip

For the Windows bundle:
  python -B tools/fetch_runtime.py --downloads work_private/runtime-downloads
  python -B tools/package_windows.py --help

The Windows packager uses pinned Python/Pillow archives and verifies their
SHA-256 identities. GitHub CI is included for Windows/Linux and Python 3.13/3.14;
a workflow file is not evidence that a remote Actions run has passed. Consult
the verification receipts shipped with the release for actual tested scope.

AUTOMATION AND CONTRIBUTING

The workbench provides an authenticated local JSON API. system.operations lists
operation names and required fields. Long operations use jobs.submit/jobs.get
and jobs.cancel. Source hashes, document IDs and reviewed plans are required
where appropriate. An API error is a refusal, not an instruction to bypass checks.
Keep the loopback token private. No remote service is needed for normal operation.

Contributions should include a small reproduction and meaningful regression
checks. Do not contribute commercial ROMs, game assets, BIOS files, personal
paths, credentials or private workspace data. Review support reports before
sharing. Include version, platform, steps, expected/actual behavior and the
sanitized report when reporting a bug. Report security issues privately to the
repository maintainer rather than posting credentials or an active exploit.

NATIVE CAPTURE CONFIGURATION (ADVANCED)

The CLI capture-run command uses this JSON layout. Replace both explanatory
hashes with complete measured SHA-256 values. Paths resolve relative to the
configuration file. Register the build first; its game hash must match.

BEGIN CAPTURE JSON
{
  "load": {
    "core": "core.so",
    "game": "game.bin",
    "expected_core_sha256": "COMPLETE_MEASURED_CORE_SHA256",
    "expected_game_sha256": "COMPLETE_REGISTERED_OUTPUT_SHA256",
    "session_dir": "new-private-session"
  },
  "steps": [{"frames": 60, "buttons": [], "port": 0}],
  "initial_state_file": null,
  "timeout": 30
}
END CAPTURE JSON

  python -m romancer capture-run "My Project" BUILD_ID "capture-config.json" --json

This records the final measured software frame after the supplied inputs;
failed or expired runs publish no capture. Use the core for the host platform.
Buttons and expected game behavior must be supplied explicitly.

LICENSES

Project code and original fixtures are MIT licensed; see LICENSE.
THIRD_PARTY_NOTICES.txt describes dependency notices. Bundled Python and Pillow
retain their full upstream license files. Separately supplied emulator cores
retain their own licenses. No commercial game data is distributed.
