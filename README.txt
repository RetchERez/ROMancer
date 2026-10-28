ROMancer v1.0 final
By RetchEWretched

Local ROM editing for NES, SNES, Genesis, Master System, Game Boy, Game Boy Color.
Master System support covers validated Sega headers, checksums, literal graphics,
declared text/byte edits, checked level layouts, patches and playtesting.
Game-specific collision, music and actor behavior require verified definitions.
Everyday use works offline. No AI account, model, API key or subscription is required.

EDITING TASKS

The Overview reports readiness for the exact selected ROM. A checked graphics
layout does not imply a known palette, music driver or level format. Open the
editing tools directly. The guide provides Basic and Advanced procedures;
concise field help and diagnostics remain available.

Try the original Mossy Hollow editing studio: arrows move, A attacks on contact
and chirps, Start restarts. Edit graphics, dialogue, speeds, visible terrain,
collision rules, actor hitboxes, health, damage, patrol limits and the melody.
Starting sprite/hitbox previews are separate from live Playtest frames. Speeds
are0 through8 pixels per frame. Reference level colors are authored RGB colors.
Older workshop sources remain reproducible for the included patch examples.

Saved verified objects can show staged pixels in a full captured scene. This is
a simulated composite of checked placements and captured colors, not an emulated
frame. Other uses of the same tiles, transparency and priority still need testing.

The compact offline guide puts procedures and illustrations together and pairs
short topics. All Basic/Advanced procedures, glossary and index remain linked.

WHAT WORKS / WHAT NEEDS A DEFINITION

Ready to use in the full Windows edition:
- Open the included original workshops without supplying a game.
- Inspect bytes and checksums, compare files, make reviewed byte edits, and
  apply or export patches into separate builds. Originals stay unchanged.
- Load supported cartridges in Playtest using the included engines. Test
  controller input, pause, and save/load states for the exact selected build.

Connected workbench across all six systems:
- Game view connects checked resources, rooms, named records and saved native
  gameplay traces to editors and exact bytes. It does not require a Pokemon profile.
- Select a captured object to save literal pixel-match candidates and search
  coverage. Matching pixels are evidence, not inferred CPU transfers or ownership.
- Save automatic build checks: original twice/build once, cartridge integrity,
  state replay, clean worker closure and original/build/difference pictures.
  PASS, REVIEW, REGRESSION, INCONCLUSIVE and BLOCKED describe the configured test.
- MCP exposes the same graph, trace and test services with strict schemas and
  compact image previews. Read the Basic and Advanced guide procedures.

Verified graphic sources:
- Save a captured object trace from a fresh cold-start playtest, then choose
  Verify ROM sources. Coded pixel probes recover distinct source origins;
  two independent spatial validations and a restored-ROM control check them.
- Inspect exact source offsets, screen pixel maps and codec-derived byte lanes.
  Open a verified source part in the existing visual editor. Original ROMs stay
  unchanged and diagnostic builds never enter the project build history.
- This works with the tested literal tile formats on all six systems. It does
  not claim recorded CPU/DMA transfers, infer every compression format or label
  a whole sprite's role automatically. Unverified and partial results stay clear.
- GUI and MCP share the source-proof service; traces.origin reads one precise
  pixel-byte map without a large report. See the Basic and Advanced guide.

Connected editing:
- Select verified placements from one captured scene, name them and open the
  whole object. Flips, gaps, captured colors and shared tile uses stay visible.
  Saved layouts reopen from Game view and travel as checked research metadata.
- Record a native graphics access replay for actual source reads, video writes,
  operation details, registers, video memory and the final scene. Full Windows
  packages include reviewed MesenCE/MAME observers and complete matching source.
  A nearby read and write does not prove dataflow; snapshot palettes/banks can
  differ from mid-frame state. Physical ROM mapping stays explicit.
- Test this edit reuses a fresh captured route for a descendant build. The
  original must reproduce twice with the same core setup. See original, build
  and difference pictures; intentional changes require human review.
- Preview recompression reports packed size, free bytes or overflow. Supported
  reserved moves check declared pointers, fill, capacity and bank constraints.
  Reservation and reference completeness are author declarations, never guesses.
- GUI and MCP share these services. Read the Basic and Advanced guide for
  whole-object editing, native graphics trails, captured checks and compression.
  Reviewed tools retain their upstream licenses, matching source and notices.

Editors need an understood layout:
- Text, numeric tables, assembled sprites, palettes, levels and sound need a
  verified definition or an explicit declaration of the format and byte ranges.
- An exact game/revision match can provide named editing controls. A matching
  console header alone does not identify all of a game's resources.

Still unknown until investigated:
- Deep scans provide checks, documented structures and candidates. They do not
  automatically decode every game's compression, scripts, maps or music.
- Unsupported or ambiguous cartridge layouts cannot be imported. A missing game
  definition is not a failed checksum. Read matched,
  mismatched, unsupported and unknown results separately.
- Tested system/data formats cover NES, SNES, Genesis, GB, GBC and
  basic Master System formats.
  This does not certify every commercial game or every edit within a game.

BUILT-IN DOCUMENTED GAME DATA

GB/Color stat-prefix templates use declared table locations and record layouts.
Public format references are distinct from exact-source and native verification.

Resources also imports matching RGBDS GB/GBC .sym listings.
Search names and inspect mapped ROM bytes; RAM labels remain CPU addresses.
These files lack an embedded ROM hash and require source acknowledgement.

HACK EXAMPLES

ROMancer-v1.0-Hack-Examples.zip is the main collection: six selected examples,
one per supported system. Each includes its required original SHA-256 and CRC32.
- NES / Castlevania: a Simon sprite edit.
- SNES / Chrono Trigger: Wood Sword power changed to 30.
- Genesis / The Immortal: a start-prompt text edit with its checked game fix.
- Master System / Rastan: single-blob enemy graphics.
- Game Boy / Final Fantasy Legend II: move the opening bedroom stool.
- Game Boy Color / Deja Vu I & II: change startup palette colors.

Start with these six. Extract the ZIP, then use Export > Apply downloaded patch
with the exact original revision from its README and manifest. Review the result
and create a separate build. The guide explains patching, editing and playtesting.

ROMancer-v1.0-Hack-Archive-Optional.zip preserves the other 41 patches: earlier
versions, original-workshop tests and experiments. You do not need this archive
to use ROMancer or follow the guide. Failed and superseded variants remain
clearly labeled; they are not recommended showcase hacks. All 47 original patch
files are preserved unchanged across the two ZIPs. No commercial ROMs are included.

Rastan-Single-Blob-Enemies.bps is the current Rastan graphics example. It was
created with ROMancer assets.plan and structured.apply, then recreated through
its actual Graphics & fonts interface. The original and edited gameplay captures
come from ROMancer Playtest. See the Rastan guide chapter for the exact tested
revision, tile arrangement, byte summary, limitations and screenshots.

SHORT WALKTHROUGH

Watch ROMancer-v1.0-Walkthrough.mp4, or open Help -> User guide -> Watch the
first-edit walkthrough. The captioned video shows the original NES workshop,
actual editing, undo/redo, a build, native playtesting, states, patch export,
reopening the project and recovering a saved draft. No commercial ROM is used.
The video is inside user-guide/ in source, app/user-guide/ in Windows packages,
and is also supplied separately with the release. It works offline.

START ON WINDOWS

1. Run ROMancer-v1.0-Setup.exe and follow the installation steps.
2. Open the ROMancer desktop or Start menu shortcut.
   The Windows ZIP is also available: extract it fully and run Install ROMancer.cmd.
3. Open an original workshop or choose New project and import your own cartridge image.

Python and Pillow are included in the Windows x64 package. Edge provides the
desktop window; Open in browser is available if the window cannot open.
The launchers are unsigned. The full Windows release includes engines for
NES, SNES, Genesis, Game Boy, Game Boy Color and supported Master System cartridges. Games, user saves and separately supplied
firmware dumps are not distributed. Editing and patching also work without emulation.

The full Windows runtime blocks changed or unreviewed core binaries before loading
native code. Its included open-source engines are FCEUmm (NES), bsnes-mercury
Balanced (SNES), BlastEm (Genesis/Mega Drive and Master System), Gambatte
(Game Boy and Game Boy Color). SHA-256 pins, source revisions and
component licenses are included. Source development retains synthetic test-core
support; custom builds require their own source/license and compatibility review.

Installed projects: %LOCALAPPDATA%\ROMancer\workspace
Upgrades retain projects and prior versions. Rollback restores the previous
launcher. Uninstall preserves projects and installed versions for recovery.

VERIFICATION STATUS

The release verification.json records the exact source commit, source and
bundled-runtime checks, skips, UI checks, native results, guide checks and
package audits. SHA256SUMS identifies each delivered file. Read recorded test
scope separately from whole-game compatibility.

The original NES workshop covers visual editing, undo/redo, separate builds,
native playback, save/load states, verified patch export and draft recovery.
The native system checks cover NES, SNES, Genesis, Master System, Game Boy and
Game Boy Color. Supplied commercial revisions have their own bounded evidence.
The six-example showcase and optional 41-patch archive together retain all 47
distinct patches from 18 exact source identities. Independent reconstruction checks their recorded target hashes;
historical experiments retain their limitations and quarantine status.

These are automated local checks, not a claim that every commercial game or edit
works. An independent beginner trial, a clean Windows VM and a human
screen-reader trial remain separate acceptance checks. Remote CI must be reviewed for the exact
uploaded commit; the local package summary does not assert a remote result. Browser
layout/DPI emulation is not a Windows-wide display-scaling trial.

A file named .7z is not necessarily an archive. Saved HTML download/error pages
are rejected with an explanation; choose a real extracted cartridge file.
The first supplied Rastan.7z was HTML and was rejected. The replacement ZIP
contained a valid unmarked Rastan ROM and a separately marked bad variant; only
the unmarked revision was used. The exact Rastan revision now offers Open first enemy sprites with its
checked 16-by-32 assembly and byte references. The included example is a graphics-only
reskin of the first humanoid enemy into one connected blob. Opening-scene video,
three connected animation-frame shapes, save/load and exact patch reconstruction
were checked. Other enemy types, collisions, enemy AI and full-game correctness
are not certified. Game Gear, headerless SMS inputs and ambiguous Sega layouts
remain outside this release. The SMS A/B interface maps the included BlastEm
engine to its two-button pad: A and B are buttons 1 and 2, and Start sends Pause.

GITHUB RELEASE PREPARATION

Use the tag v1.0.0 for the public ROMancer v1.0 release. The numeric 1.0.45 build
identifier is internal installer/update identity. Lead the release description
with ROMancer-v1.0-Setup.exe, then the portable Windows ZIP, offline guide and
walkthrough. Provide the source, engine pack, component notices and SHA256SUMS.
The Windows packaging workflow downloads ROMancer-v1.0-Engines.zip from the
repository's v1.0.0 release: attach that supplied engine pack to a draft release
before running the trusted Windows packaging job. Uploading source files alone
is not a successful CI run. Publish only after reviewing actual workflow results.

The repository includes a structured bug-report form. Enable private vulnerability
reporting in GitHub before advertising the Security reporting path. User reports
must exclude ROMs, saves, states, credentials and personal paths. The included
patch collection contains ROMancer-created outputs and sanitized indexes;
failed/superseded experiments are separated and clearly labeled. Patch
reconstruction is verified for every included variant;
apply a patch only to the exact original revision named by its SHA-256.

BEGINNER ACCEPTANCE CHECKLIST (YOUR HANDS-ON TRIAL)

Copy this checklist into your own notes, or print it; leave installed program
files unchanged. Do the trial using the original NES workshop. Leave a box
unchecked if you
skip it, need outside help, or cannot tell whether it worked. Note the step,
expected result, observed result and any unclear label. These boxes are not
claims that a human trial has already passed. Using the built-in guide and
the illustrated guide is allowed; record any need for another person to explain the controls.

[ ] Open the app and the NES workshop without manually configuring an engine.
[ ] Find Graphics & fonts. Assemble one tile (1 across, 1 down), choose color
    index 1, focus Editing, press Right Arrow then Space. One pixel changes;
    Original stays unchanged. Fit makes the comparison readable.
[ ] Undo the sprite stroke, then redo it. See the pixel disappear and return.
[ ] Review graphics changes and create a build. Identify it in the top selector
    or Overview -> Build history; distinguish it from the original ROM.
[ ] Choose Playtest build, confirm the top bar says BUILD and shows your output,
    then Load game. Play and pause the original drawing program.
[ ] Save a state and load it for that same build. See the success confirmation.
[ ] Export an independently verified BPS patch and download it. The original
    and the edited build remain separate; the patch is a third file.
[ ] Close the project using Choose a project, then reopen it. Find the same
    source and build without assistance, and identify which one is selected.
[ ] Select the original, make one more small sprite edit, and wait for Saved.
    Reload or reopen the app; confirm any reload prompt only after saving.
    The draft and its staged-change status must return. Saved drafts still
    need review and a new build before their edits can appear in Playtest.
[ ] Complete the steps comfortably at your preferred window size and theme.
    Read the labels and original/edited previews without changing browser zoom.

Pass this trial only when every box is completed without outside assistance.
If a step is confusing, record it as a usability issue even if the operation
technically succeeds. The automated video demonstrates a workflow; it does not
replace this independent human trial.

PLAYTESTING

1. Open your project and select the original ROM or an edited build.
2. Choose Playtest, then Load game. The Windows release selects its included engine.
3. Press Play. Click the game for keyboard input or connect a gamepad.
4. Pause to save or load a state. A state belongs to its exact ROM build,
   engine and runtime setup. Battery saves have separate import/export controls.

Included Windows x64 engines:
  NES:                       FCEUmm                 GPL-2.0
  SNES:                      bsnes-mercury Balanced GPL-3.0
  Genesis:                   BlastEm                GPL-3.0
  Game Boy / Game Boy Color:  Gambatte               GPL-2.0

These are separately licensed third-party engines. Their original notices,
source revisions, DLL hashes and corresponding source archive are in cores/.
The main ROMancer source is MIT licensed. Keep every component's notices and
source distribution together when redistributing the full Windows package.

Game Boy Color is the sixth system choice and shares the included Gambatte engine.
Validated CGB-compatible and Color-only header flags select a separate GBC hardware
profile, independent of the filename extension. Ordinary Game Boy images use DMG.
Color palettes use RGB555; tiles share the paired 2bpp format. Hardware background
attribute planes and game-specific bank behavior require explicit declarations.

ROMancer verifies the bundled engine identities before using them. If the pack
is incomplete or changed, reinstall the release; it will not silently load a
replacement. Saved custom setups take precedence over bundled defaults.

Advanced users and source-only installations can select another compatible
x64 libretro core in Advanced core setup. A standalone emulator EXE is not a
libretro library. Linux uses a Linux x86_64 .so, rather than a Windows DLL.
New or unusual cartridges may need configuration or external system files;
passing the included checks does not certify every game.

USER GUIDE

Help -> User guide opens the included offline manual. It contains Basic and Advanced
workflows, actual editing screenshots, offline topic search, a linked glossary and an
alphabetical index. Search the HTML guide by tool, task or unfamiliar term.
The source and Windows packages also include user-guide/index.html and guide.pdf
(inside app/user-guide in the Windows package). Keep the screenshots folder with it.

New users can follow the complete original NES-workshop exercise: edit one pixel,
create a build, test it, and reconstruct it from a patch. No commercial ROM is
needed for practice. Overview offers task shortcuts. Sprite previews offer Fit and
8x/16x/32x viewing sizes; these do not resize the stored graphics. After creating
a build, Playtest build selects that recorded output and opens Playtest.
The guide also includes a checked MCP editing example and
a checklist for testing and sharing a hack.

The default 100% app size now matches the earlier 75% layout. Browser zoom can stay
at 100%; Settings -> Preferences offers larger interface sizes.
ROMancer is the default theme; Dark and Light are also available.
ROMancer and Dark use deeper menu backgrounds; Light uses grey panels and menu
boxes with dark labels. Theme choices do not change ROM graphics or palettes.
OK saves and closes Settings. Apply saves while staying there. Cancel discards
unapplied preference changes. Restore defaults fills the standard values; use
Apply or OK to save them. Auto deep scan on ROM load is enabled by default.
Automatic gameplay graphics analysis, workspace restore, volume, mute, preview
looping, reduced motion and advanced-tool visibility are configurable. Settings
and workspace restore metadata persist independently of the browser port.

KNOWLEDGE AND INVESTIGATION

Resources -> Resource browser & research lists checked active layouts and
source-bound user range notes. Search by resource kind or words in a note.
Explain selected bytes keeps user research separate from decoded storage facts.
Edit note loads its full text; browser/MCP lists use bounded summaries.

Share or import research exchanges the five supported active definition kinds
and notes as one exact-revision JSON pack, up to 1 MiB. Preview checks every
entry, lists replacements and binds review to the current metadata. Import
commits metadata atomically; changed reviews and wrong ROM revisions are refused.
Existing other notes remain. No ROM bytes are written. Review user text and
definition byte guards before sharing; packs are not sanitized support reports.

Opening a saved resource setup reviews a different existing editor draft first.
Load saved setup stores a source-bound recovery copy before replacement;
Resources -> Previous editor setups restores it. Document-specific editing
drafts remain separate. Recovery storage is bounded and is not a project backup.

Help and Resources -> Popular-game references include pinned primary research
for Pokemon Red/Blue, Crystal, Super Mario Bros.
and Super Mario World. No source code, graphics, music or ROMs from these projects
are bundled. Published RAM labels are not ROM file offsets.

Documented stat-prefix templates cover Red/Blue and Crystal layouts.
You must establish the table offset, full record stride and count for your
matching project. Preview table layout opens a checked numeric proposal; it
does not locate the table or certify an arbitrary modified hack. Check values
and record identities before saving or editing. The illustrated prefix example
uses an original Game Boy Color workshop; it does not certify a Pokemon revision.

These are original factual summaries of public references, pinned in the
application: github.com/pret/pokered, github.com/pret/pokecrystal,
github.com/Xkeeper0/smb1 and github.com/IsoFrieze/SMWDisX.
MCP clients can use references.catalog, references.template, research.inspect,
research.note_get, research.note_save, research.preview and research.apply.
The same source guards and review requirements apply to humans and automation.

Hardware & address help includes standard tile, palette and map storage facts
for all six system choices, with technical sources and explicit format scope.

Automatic cartridge verification includes conservative startup-vector/entry
checks, documented boot-header fingerprints and standard mirrored SNES checksums
for ordinary LoROM/HiROM up to 4 MiB. Warnings and unsupported checks stay distinct
from passed checks. It does not execute startup instructions or certify gameplay.

Overview -> Build history -> Compare files compares original and modified ROMs.
Select a changed range to view both byte columns in Resources. Highlights mark
changes; a dash marks added/removed storage. Independent page controls cover
unequal file lengths, and Follow hex editor restores the editor position.

Automatic scans include system hardware/address context and bounded resource
candidates. Checked format packs use exact-source or explicit guarded matching.

Resources -> ROM health & revision -> Code reference catalog imports local
documented codes as read-only leads. NES/SNES/Genesis/GB/GBC Game Genie formats
are decoded separately from cartridge mapping. Revision mismatches, uncertain
banks, unsupported codes and shortened results remain explicit. Catalogs are
project-owned; no publisher compilation is bundled as MIT application data.
Mixed publication/community TXT extracts keep explicit code formats and source
paths. Action Replay and other unsupported formats are retained without ROM
locations. Duplicate references do not imply additional unique tested effects.

Investigation -> Hardware & address help distinguishes CPU, video and audio
address domains. These descriptions never activate cheats, access devices or
automatically turn a RAM value into a ROM edit. The offline guide explains
these tools and the separate evidence needed before making a build.

UNIVERSAL INVESTIGATION

Investigation records native before/changed/control observations and tests
8/16/24/32-bit binary, signed and packed-BCD values in either byte order.
Hypotheses retain their tested scope; a matching number does not establish meaning.
Investigate accesses derives a physical watch from the pinned engine interface
and replays a short controller route in a separate native debugger from power on.
It does not resume Playtest or convert emulator save states.

Advanced native capture uses reviewed MesenCE (NES/SNES/SMS/GB/GBC) and
MAME (Genesis) observers. The full Windows package includes both, their licenses
and complete matching source. Windows x64 is required; the Genesis observer
requires an x86-64-v2 CPU. Exact binaries and source inventories are checked.
Source-only or smaller custom builds can use Prepare debugger to fetch the
pinned upstream version once. Preparation uploads no ROM. Later captures reuse
the verified cache offline. A bundled observer takes priority over an old cache;
changed or incomplete bundled files are rejected rather than silently replaced.

Capture reports distinguish completed routes, capped samples, mapped source
locations and candidate pattern matches. Genesis instruction and access samples
have separate ordering. Genesis execution-range watches are unavailable; its
global instruction samples do not filter by the watched read/write range. Access width, DMA ownership and game meaning remain
unknown where the backend does not establish them.

Explore ROM structure tests bounded repeated numeric layouts and possible linear
pointer arrays. Open a neutral table editor, then Save this layout to retain it.
Deep scan includes sampled structural tests and reports coverage. A candidate
layout is not a decoded game format or proof that every reference was found.

Resources -> Move declared data (Advanced) can copy or grow declared data into
an explicitly reserved fixed-size cartridge range, update exact linear pointers,
and create a separate build. Fill bytes alone do not establish unused space.
Every required reference and bank constraint must be declared; code relocation,
embedded references and automatic proof of reference completeness are unsupported.
Original data is preserved. Old fixed-offset definitions are not automatically
reused after relocation; a wholly covered neutral numeric table can be rebased,
previewed and saved. Playtest before exporting.

Gameplay graphics can group captured pixel matches into editable sprite-layout
proposals, including flips and repeated observations. Source use and semantic
ownership stay unproven until supported by evidence. Music & sound edits explicit
supported sample codecs and the identified original practice sequence driver.
Unknown commercial music or scripting grammars are not silently reinterpreted.

EVERYDAY CONTROLS

Ctrl+S saves editing drafts; Create build produces the playable ROM.
Ctrl+Z undoes the active editor; Ctrl+Y or Ctrl+Shift+Z redoes it.
Ctrl+K searches the workspace. Press ? outside a text field for the shortcut popup,
or open Help -> Keyboard shortcuts. No operating-system hotkeys are registered.
Text fields keep their native undo/redo; game input and dialogs are left alone.
Closing with pending saves, staged changes or an active job asks for confirmation.
Short field explanations appear on hover or keyboard focus, with more in Help.

- Search for palette, sprite, hex or save state to find tools; matching files
  are clickable and open the exact selected revision in Resources.
- Sprite brush swatches retain their stored indices. Declared, observed and
  unknown grayscale colors are labeled; a missing game palette is not guessed.
- Supported decoded image/palette pairs offer Original, Edited, Changes only,
  Side by side and optional slow blink. Comparisons exclude editor outlines;
  terrain-only views do not measure object or collision records. Reduced motion
  disables blink. Save edited PNG exports the full edited sprite, not a mask.
- Review summaries count exact bytes, including listed checksum/header updates.
  Optional build names and multiline notes preserve the output identity.
- Patch downloads use the release title. Download started means the browser
  handles the save request; check its Downloads list for the resulting file.

YOUR FIRST EDIT

Import creates an owned source copy and starts an offline investigation.
Original files are never edited. Select a known resource, stage a change,
review its exact bytes, and create a separate build. Select that build in the
source/build selector to playtest it. Export a verified BPS patch to share.
Downloaded BPS and IPS patches can also be applied to a separate build.
BPS includes checksums. IPS requires an external original-source reference.

Help opens the offline illustrated guide, topic search and concise tool references.
The guide contains Basic and Advanced procedures, pictures, a glossary and index.

WHAT IS SUPPORTED

- Interactive hex editing, wildcard/text/integer searches and named bookmarks.
- Declared text editing with protected control codes, capacity checks and CSV/TSV.
- Named numeric tables, explicit byte order and reviewed batch/percentage changes.
- Tiles, palettes, fonts, tilemaps and assembled sprites with stroke undo/redo.
- Live original/edited sprite, tile and room comparisons with change markers.
- Palette color picker with before/after swatches and declared color quantization.
  Master System Mode 4 uses checked one-byte RGB222 palettes and its own tilemap
  masks, preserving priority and undeclared bits.
- Live text/capacity and numeric comparisons with explicit preview status.
- Explicit animation-frame layouts and shared-tile information.
- Declared fixed-capacity terrain, metatiles, collision values and object fields.
- Room thumbnails, explicitly declared connections and named object controls.
- Checked level and sound definition exchange for the same source revision.
- Byte explanations for declared tile rows/bitplanes, palette components, room
  cells, object fields and numeric storage.
- Tested PCM8/16, Game Boy wave, NES DPCM and standalone SNES BRR sample codecs.
- Sample gain/reverse/silence/WAV replacement and play/pause/seek previews.
- Documented console sound hardware, evidence-scoped driver identification,
  and native mixed-audio recording through a configured core.
- Native playtesting, gamepad/keyboard controls, battery-save backups and states.
  Live playback starts with fresh step audio after manual frame advancement.
- Source/session/core/state-bound RAM narrowing and available video-memory tiles.
- Build history, byte comparisons, recorded tests and screenshot checkpoints.
- ROM health, CRC comparison, supported checksum repair and project validation.
- Local hash-catalog import, source-bound resource relationships and support reports.
- Recoverable project deletion, private backup/restore and persisted editor drafts.

Exact-revision examples include Rastan SMS first-enemy sprites, Final Fantasy Legend II USA (opening-bedroom
stool placement and a source-bound real-map browser) and Deja Vu I & II USA (startup and first Case Book 1 interface
colors), alongside the four earlier game definitions. Only matched originals or
owned derived builds expose these edits. Different revisions remain unknown.

FACTS, DEFINITIONS AND LIMITS

KNOWN SUPPORT AND UNRESOLVED FORMATS

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

Sound hardware is not a music driver. Original Hillside and Mossy Hollow
sequences support checked note edits. Reference note sketches omit hardware
instruments and effects. Native recordings contain measured mixed output,
not isolated hardware channels.

Declared rooms and object fields use existing fixed storage. They do not add a
game engine, infer collision meanings or allocate new rooms. Unsupported layouts,
compression and drivers remain unavailable. Original workshops are redistributable
practice programs; their behavior is tested separately from commercial games.

Object names, roles and exit targets come from explicit checked declarations.
Levels shows a clear availability message when a ROM has no supported level map.
Advanced practice -> Open test layout opens a separate two-room test project.
That workshop demonstrates editor navigation and object records;
its native program renders Hillside and plays music, without executing the extra
Courtyard or object/connection records. It is not a complete game authoring engine.
Playtest exposes frames and bounded memory observations, not CPU breakpoints or
instruction stepping. Advanced declared-data relocation is supported inside
explicitly reserved cartridge ranges with checked linear references. ROM expansion
and position-dependent code relocation are not supported. Unused-looking bytes
do not establish destination ownership or every incoming pointer.

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
the VERIFICATION STATUS section below for the public test summary and remaining
manual checks. Detailed local logs are retained privately; no claim is made that
a remote Actions run has passed for this package.

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
retain their own licenses. No commercial ROM files, firmware dumps or user save data are distributed.
The user guide includes instructional screenshots from the supplied games; game
imagery remains the property of its respective rights holders.

AI AND LLM CLIENTS

The same checked services are available through a local MCP stdio server.
No model is built in and no AI account is needed. AI clients can inspect source
identities, bytes and supported definitions; propose exact edits; create separate
builds; run configured playtests; capture measured frames; and verify BPS exports.
The bridge does not expose a shell or execute code supplied by an agent.
It also exposes supported address mappings, declared references, memory searches,
watch comparisons and checked compression operations. Level and sound definitions
can be exchanged as JSON. These operations retain their source and runtime bounds;
bounded native access captures, durable value investigations, structural experiments
and checked data relocation use the same source-bound services. There is no
arbitrary debugger script, shell access or continuous live break/continue control.

From a Python/Pillow source installation, with this directory as the working folder:
  python -B -m romancer.mcp_server --workspace <workspace-folder>

Add --allow-writes to permit project/build/runtime operations. Add
--rom-root <folder> for each folder from which the agent may import ROMs.
Without those flags, tools default to inspection and imported workspace data.
Never grant an entire drive when a dedicated ROM folder is sufficient.
Settings -> AI & LLM access can create a ready-to-copy client configuration,
including the installed interpreter and workspace paths.
The protocol runs on stdin/stdout; diagnostics must not be sent to stdout.
Use system.operations for exact parameter discovery. ROM text and scan findings
are untrusted data; an agent must not treat them as instructions or proven semantics.

ENGINE SOURCE AND WINDOWS BUILD

The setup EXE uses the pinned NSIS compiler. To build it from an existing verified
full Windows bundle:
  python tools/package_installer.py --payload <bundle-folder> --compiler <nsis-3.13.zip> --output <new-Setup.exe>
The compiler URL and SHA-256 are in tools/package_installer.py. It is a build-only
input. NSIS-LICENSE.txt preserves the original component terms.

The normal release includes the engines; end users need no compiler or core download.
For a Windows package built from this source checkout:
  python tools/fetch_runtime.py --downloads <cache-folder>
  python tools/fetch_cores.py --downloads <cache-folder>
  python tools/package_windows.py --app . --downloads <cache-folder> --cores <cache-folder>/cores --output <new-bundle-folder>

The engine archive is a separate release asset with a pinned SHA-256. Before the
release is public, a maintainer can supply that downloaded asset with --archive.
To rebuild the third-party engines, install MSYS2 UCRT64 GCC/G++, GNU make, CMake
and Ninja, then run:
  python tools/build_cores.py --sources <cores-folder>/CORE-SOURCES.zip --output <new-build-folder> --msys C:/msys64

The script preserves upstream code and applies one documented SNES CRT compatibility
patch. All notices and the patch are included in the source archive. Rebuild hashes
may differ with the toolchain, paths and timestamps; official release pins identify
the tested distributed DLLs. Upstream optional test ROMs, unused standalone profiles
and mobile-platform links are omitted from that Windows libretro source archive.

The exact Chrono Trigger USA definition provides named equipment and enemy-stat
tables: attack/critical rates, armor/helm defense, gear base prices, and enemy HP
and core stats. Names are decoded from the selected ROM; IDs distinguish blank,
duplicate and unused slots. Effects, flags, rewards and scripts are preserved.
Stored values do not predict every final game formula. The older 90-record
attack-only resource ID remains compatible with saved workflows.

Final Fantasy Legend II USA includes a catalog of 219 header variants, 164 shared
terrain streams and 543 arrivals. Supported opening-atlas edits preserve collision
and trigger bindings for every shared header. NPC conditions and packed flags
remain protected; even an unconditional NPC may participate in the story.
Some map opcodes and unknown palettes remain unavailable or explicitly marked.
Map destinations are inspection-only in the visual editor.

Game edits -> What is known about this game separates supported workflows,
checked reference layouts and research leads, with pinned source links. Public
disassemblies and hack documentation are references, not automatic edit authority.
A binary patch describes differences, not the meaning of every changed byte.
Reference facts are bound to matched originals; external hacks can relocate data.
No research caches, commercial ROMs or upstream editor implementation are bundled.

SAVED BUILDS AND SCENE PREVIEWS
Per-ROM readiness requires writable definitions, including read-only codec checks.
Saved-build Playtest/Export controls survive reopening and keep exact ancestry.
Graphics can replay a checked temporary draft against a saved cold-start trace,
with original/draft/difference emulator frames. It does not publish a project build.
The guide explains bounds, stale results and simulated object-composite differences.
Independent beginner acceptance remains pending; use user-guide/ACCEPTANCE.txt.

UNDERSTANDING THE MAIN WORKFLOW
Start with Try the editing studio for an included playable practice game.
More practice ROMs contains simple system test programs.
Original: your imported ROM; editing keeps it unchanged.
Draft: editor changes saved for later; these are not a playable ROM yet.
Build: a separate ROM containing changes you reviewed and created.
Patch: the changes you share; the recipient supplies the matching original.
Game save: ordinary progress saved by the game, such as a .sav file.
Save state: an emulator snapshot for one exact ROM/build and emulator setup.
Ready to edit means the saved layout is usable; it does not decode every resource.
Playtest: Load game, then Play; click the game screen for controller input.
Unload game closes that session. Your project files and saved states remain.

BUILD 41 WORKBENCH IMPROVEMENTS

Investigation can summarize the complete retained authenticated capture into
mapped writer code, separate source reads and useful next experiments. Partial
or historical evidence keeps its limits; proximity does not prove causation.

Resources has a preview-first editor builder for named tables, graphics and
fixed-slot text. Advanced definitions also accept explicit level, sound and
command grammars. Saving checks the exact source and current metadata; replacing
a setup requires acknowledgement. It does not alter the ROM.

Declared command operands have named controls, before/after review and guarded
build plans. Unknown/truncated commands remain read-only. Game view connects
scripts, collision usage, music events and saved animation arrangements. Saved
frames and timings are author declarations, not automatic animation decoding.

Compressed moves accept multiple explicit references, with a bounded numeric
candidate survey. Candidates do not prove complete references or unused space.

The guide includes illustrated procedures, glossary links and index entries for
these tools. The independent beginner acceptance trial remains unperformed.

FORMAT AND WORKFLOW IMPROVEMENTS
The default theme keeps the original ROMancer teal palette with deeper menus
and input fields. Visual editing and values stay visible; investigation and automation
are grouped under Advanced. Theme and interface size remain saved preferences.

Local format packs can reuse understood layouts with exact-source matching or
explicit protected-region compatibility. Deep scan suggests matches and never
silently applies them. Matching declarations do not prove native game semantics.

Text & layout can move a growing position-independent message into author-reserved
capacity, preserving controls and the original slot, updating all declared
record-start pointers and reopening the checked moved schema. Interior pointers
are refused; their offsets can shift as text grows. Complete consumers must be
investigated before acknowledging a move.

Known command grammars have form controls and a linear sequence editor. Insert,
remove and reorder fully declared commands inside the original allocation.
Branches, pointer-bearing commands, unknown stored bytes and overflow refuse.
A native original NES example exercises an actual command interpreter.

Compression supports LZ10, RLE and explicit SNES LC_LZ2. An independent
original decoder verifies recompression. LC_LZ2 has no unique signature, so scan
does not guess its locations. LC_LZ3 and other variants are separate formats.

Native investigations can stop at a selected occurrence of one explicit access
watch, retaining real registers and execution context. Six original programs
and the six supplied real ROMs passed bounded callback-stop checks. This does
not provide continuous instruction stepping or prove every gameplay path.

The illustrated guide covers these procedures, with glossary and index links.
Independent unfamiliar-user acceptance remains pending in ACCEPTANCE.txt.

RECORDED ROM FACTS DATABASE
The release includes 1,035 independently measured cartridge samples:
NES 273, SNES 314, Genesis 148, Master System 50, Game Boy 149 and Game Boy Color 101.
Names come from supplied filenames and are not canonical-dump certifications.
Every included source SHA-256 and CRC32 was independently recomputed. The catalog
records standard header/layout numbers, cartridge check outcomes and bounded
resource locations. Its 33,120 ASCII-like ranges and 32,907 generic graphics
locations are hypotheses, not identified dialogue or sprites. 213 NES graphics
locations derive from declared CHR-ROM headers. 4,660 LZ10/RLE encoding candidates
passed a separate decoder; this does not prove a game uses those streams.

Automatic deep scan and Check ROM use exact source hash/size matches. Expand
Measured file facts & locations to inspect recorded offsets. A changed build
can be unrecorded while its original still matches. These facts never authorize
writes, invent a game-specific editor or identify every map, stat, script or
music driver. Existing checked definitions, source guards and playtesting remain
the editing workflow.

The six supplied archives contained 1,048 cartridge candidates. 1,035 passed the
current unique-layout admission checks; 13 were excluded for unsupported or
inconsistent layouts. Two FDS disk images and a save file were outside scope.
No excluded file was relabeled as supported. Deep analysis reads the whole file,
but graphics are sampled and compression work/results are bounded. Coverage and
truncation flags are stored per record.

Advanced source-build maintenance:
  python -B tools/scan_rom_archives.py --archives "collection.zip" --output "facts.json" --report "private-report.json" --journal "resume.jsonl" --jobs 2
The tool accepts ZIPs and one nested ZIP level, verifies archive CRCs, bounds
work and temporary extraction, validates its facts-only schema and can resume.
Review the generated data before replacing knowledge/rom_samples.json in a
source build. Keep private reports/journals outside the release. Do not modify
an installed version's verified files. The shipped catalog works offline;
users do not need to run this maintenance script to use its existing records.
API/MCP clients can page rom.samples and read recorded_facts from rom.check and
rom.scan.run. Sample matches do not grant canonical, runtime or edit authority.

DATA PROVENANCE AND REDISTRIBUTION
This catalog was measured independently from locally supplied game files.
It does not copy a third-party hash database, editor definitions or guide prose.
Only hashes, sizes, short filename labels, numeric layout/check facts, offsets,
format identifiers, evidence levels and scan coverage are included. No ROM
images, executable game bytes, dialogue excerpts, pixel data, audio, decoded
resource payloads, personal paths or save contents are included in the catalog.
Own code, schema and original compilation use LICENSE; the underlying games,
trademarks and third-party emulator components retain their respective rights.

US Copyright Office guidance distinguishes individual plain facts from protected
expression and original database compilations:
https://www.copyright.gov/register/tx-databases.html
https://www.copyright.gov/circs/circ33.pdf
The facts-only policy follows that distinction; it is not a worldwide legal
guarantee or permission to redistribute extracted game content. Independent
measurements and conservative export fields are used instead of copying another
author's database or expressive material.

BASIC WORKSPACE AND READABILITY
The main navigation keeps text, graphics, levels, stats, music, playtesting and
export visible. Game view, Resources/hex, investigation, recipes, routes and
regression are under Advanced. Opening those tools from a task opens the group
automatically. Manual table layout starts collapsed. The compact default layout
uses a minimum interface text size of 18 CSS pixels; Settings offers larger
interface sizes without changing game graphics.
