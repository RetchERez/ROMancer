"""Packaged, searchable task help. No network, model, or executable definitions."""
import copy


def _topic(identifier,title,summary,steps,terms=''):
    return {'id':identifier,'title':title,'summary':summary,'steps':steps,'terms':terms}


TOPICS=(
    _topic('saving','Save, undo and exit','Drafts preserve your work; a build is the playable result.',[
        'Drafts save automatically. Ctrl+S saves them now; Saved in the bottom bar confirms completion. Save failed keeps your edits and offers Retry save.',
        'Undo and Redo target the active sprite or pixel editor, or the last edited field. Text boxes keep normal Ctrl+Z and Ctrl+Y.',
        'Review changes, then Create build before playtesting. Original ROMs are preserved; build history lets you return to an earlier result.',
        'Closing with pending saves, staged ROM edits or an active job asks you to confirm. Cancel closing, save drafts, and create a build if you want a playable result.'], 'save exit close undo redo draft build original patch safety'),
    _topic('terms','What the terms mean','Short explanations also appear beside storage fields on hover or focus.',[
        'Original: your preserved input copy. Draft: an editing proposal. Build: a separate edited ROM. Patch: a file describing changes for an exact original.',
        'Offset: a byte position counted from zero. Capacity: reserved storage. Stride: distance between record starts. A CPU address may need bank mapping to become a file offset.',
        'Tiles store pixels; palettes store colors; tilemaps arrange tiles; sprites may combine several tiles. A declaration describes checked storage, not automatically proven game behavior.',
        'Matched uses an exact reference. Candidate needs confirmation. Unknown means no supported meaning has been established.'], 'glossary offset bank palette tile sprite pointer checksum encoding capacity stride'),
    _topic('sound','Inspect music and sound','Console hardware, driver recognition and sample codecs are separate.',[
        'Open Music & sound to see documented audio hardware and the identified driver, or Unknown.',
        'Load this source in Playtest and reach a useful sound. Record native preview captures its mixed output; use play, pause, seek and loop.',
        'A supported sample definition allows waveform preview and fixed-allocation edits. Quantized re-encoding is lossy.',
        'Sequence editing is enabled only for an implemented, verified driver. Hillside and Mossy Hollow have original note formats.'], 'music audio sample sound engine driver wav brr dpcm'),
    _topic('projects','Create and delete projects','Keep separate work in separate projects.',[
        'Choose New project, enter a name, then Create & import ROM or Create empty project.',
        'Open Projects in the sidebar to switch projects or choose Delete project.',
        'Move to Trash removes the owned project from the list; it leaves your external original files untouched.',
        'Open Projects → Trash → Restore to recover its sources, builds and saved work.'], 'project new delete trash restore recover workspace'),
    _topic('sprites','Edit a whole sprite','Assemble declared tiles into a source-bound editing view.',[
        'Inspect a graphics declaration in Graphics & fonts. In Sprite assembly choose first tile, grid size and tile order.',
        'Choose Assemble tiles and a Brush color index. Drag across tile boundaries or use arrows and Space.',
        'Undo sprite stroke restores the whole stroke. Review asset changes checks every changed tile before building.',
        'The assembly view is explicit: unknown OAM, animations and game-specific metasprite tables require their own mappings.'], 'sprite composite metasprite tile assembly undo preview'),
    _topic('patch-import','Apply a downloaded patch','Create a separate build from BPS or IPS.',[
        'Select the original ROM in the top bar, then open Export → Apply a downloaded patch.',
        'Choose BPS or IPS. For IPS, enter the full-file CRC32 or SHA256 supplied by its author.',
        'Preview compatibility and changed ranges. Name the new build, then create it.',
        'Playtest the build. Your original and downloaded patch stay unchanged.'], 'bps ips apply download checksum reference'),
    _topic('revision','Identify an exact revision','Use your own offline hash catalog.',[
        'Open Resources → ROM health & revision → Identify ROM revision.',
        'Choose whole-file or supported cartridge-payload scope and import local CSV, TSV, JSON or XML DAT.',
        'Identify the selected ROM. Unknown means no reference matched; it does not establish corruption.',
        'Search a specific reference to check an expected revision. A mismatch uses that reference’s scope.'], 'crc32 sha1 sha256 catalog dat unknown matched mismatch'),
    _topic('hex','Edit bytes','Stage exact-byte changes, then review.',[
        'Open Resources, choose a byte cell and enter two hex digits. Arrow keys move between cells. The outline pairs the selected byte with its ASCII character. Underlining marks staged changes.',
        'Search bytes using AB ?? CD, UTF-8 text or an integer with an explicit byte order.',
        'Use the number inspector or bookmark a selected offset.',
        'Review the edits and create a separate build. Overview → Build history compares versions and names builds.'], 'hex endian wildcard bookmark bytes history'),
    _topic('saves','Manage battery saves','Keep ordinary saves separate from emulator states.',[
        'For emulator save states, use Save state and Load state beside Play. Choose a timestamped state for the same ROM, core and setup. Loading refreshes one frame, then pauses.',
        'Load the exact ROM and core setup in Playtest, then open Battery saves.',
        'Back up the exposed RAM, or import a raw .sav/.srm file of the exact reported size.',
        'Download a selected save for a private backup.',
        'Restart with selected save keeps an automatic backup of the current RAM before closing the worker. Wrapped saves and save states require their own export tools.'], 'battery save srm sav backup restore progress'),
    _topic('translation','Translate with a spreadsheet','Edit only the translation column.',[
        'Inspect editable text in Text & layout, then open Translation spreadsheet and download CSV or TSV.',
        'Keep every stable ID, original text and control column. Edit only translation.',
        'Import the same format and review byte-capacity and encoding issues.',
        'Review the translation plan, then create a separate build. Original controls remain protected.'], 'csv tsv overflow encoding spreadsheet localization'),
    _topic('validation','Check a project','Find exact locations and remedies.',[
        'In Overview, choose Check project.',
        'Review errors, warnings and location links. Restore missing owned files or redeclare stale resource definitions.',
        'Declared pointers, overlaps and compressed allocations are checked; unknown game formats remain outside the scope.',
        'Recheck after correcting the issue. Every build still verifies its own input and plan preconditions.'], 'validate pointer overlap dependency missing stale'),
    _topic('support','Create a support report','Review before sharing.',[
        'Open Settings → Diagnostics & support and run diagnostics.',
        'Review the sanitized versions, statuses and counts in the JSON preview.',
        'Download report to share it yourself. No data is sent automatically.',
        'The report excludes ROM/save bytes, credentials, personal paths, project names and raw errors.'], 'diagnostic support privacy error report'),
    _topic('visual-tests','Screenshot checkpoints','Compare a stable region of a measured frame.',[
        'Start recording inputs in Routes, then use Playtest to reach the screen to test.',
        'Pause and capture a frame. In Screenshot checkpoints, drag a region up to 256×256 pixels.',
        'Add screenshot checkpoint to the latest recorded input, then stop and save the recording.',
        'Replay using its recorded checkpoint. A failure shows expected, actual and difference images. Save a cold-start definition to use an original/build suite.'], 'screenshot region rgb regression checkpoint visual'),
    _topic('start','Getting started','Open a workshop or import your own ROM.',[
        'Choose an existing project in the top bar, or choose a system workshop on the start screen.',
        'For your own file, choose Import ROM or drop one file into the window. Name the project and confirm the import.',
        'Choose what to edit in the left menu. Review changes before creating a build.',
        'Use Playtest to check the build, then Export to prepare and verify a patch.'], 'open source build first project'),
    _topic('import','Import a ROM','Work on a project copy while keeping the original.',[
        'Choose Import ROM. Browse for a file or drop one file into the window.',
        'Confirm the project name and file. Files up to 64 MiB can be uploaded; advanced path import supports larger owned images.',
        'Check the detected system and revision in Resources. The filename alone does not establish the system.',
        'If identification is ambiguous, inspect the reported header issues before editing.'], 'drag drop file source header'),
    _topic('discovery','Find resources','Search known formats and inspect candidate matches.',[
        'Import or open a ROM to start automatic offline investigation. ROM investigation lists exact known identities separately from candidate discoveries.',
        'Use Rescan ROM after changes, or open Find resources for a focused range and explicit pointer search.',
        'Inspect candidate previews and their reasons. A possible text or graphics match can also be code or unrelated data.',
        'Confirm the storage format, offset and allocation before declaring an editable resource.',
        'A partial scan reports its range. Continue with the next range when needed.'], 'scan candidate text graphics pointer compression'),
    _topic('text','Edit text','Edit characters while preserving declared controls and allocations.',[
        'Open Text & layout. Use an existing definition or declare the text offset, slot size, encoding and terminator.',
        'Add a pointer table only when its location and mapping are established.',
        'Edit the text or stage replacements. Keep visible control tokens intact.',
        'Choose Review changes. If text is too long, shorten it or correct the declared allocation; a fixed slot cannot grow automatically.',
        'Create the build and test it. Layout preview checks the declared font and dimensions, not every game screen.'], 'dialogue translation overflow terminator encoding control code pointer'),
    _topic('graphics','Edit graphics and fonts','Use the system codec and an explicit resource location.',[
        'Open Graphics & fonts and inspect a declared tile, palette, tilemap or font resource.',
        'Choose a tile and palette index. Drag to paint, or use arrows and Space; Undo pixels restores a whole stroke.',
        'Use editor tools or import a PNG. Paint declared tilemaps with the visual brush; tile and palette proposals appear in the map preview.',
        'Review changes and any declared shared consumers, then create a build.',
        'Playtest the build and export a patch once the result is correct.'], 'tile palette image png font glyph map pixels sprite'),
    _topic('tables','Edit data tables and pointers','Define record layout before changing numeric fields.',[
        'Open Stats & data. Set the table offset, number of records and bytes per record.',
        'Add named fields with their relative offset, numeric type and byte order.',
        'For a linear pointer, declare its base. A resolved file offset does not establish a bank-switched CPU address.',
        'Inspect the rows, edit values or preview a batch change, then review the exact byte changes.',
        'Values outside the field range, overlapping fields and stale source revisions are refused.'], 'integer signed unsigned stride record endian pointer reference'),
    _topic('compression','Edit compressed resources','Extract supported streams and reinsert into a confirmed allocation.',[
        'Select a validated LZ10 or RLE stream in Resources and confirm its codec, offset and allocated capacity.',
        'Extract it into the project. Edit the decoded resource through the normal editors and create an edited build.',
        'Choose the edited decoded build and review recompression into its original parent.',
        'The new stream must fit the confirmed allocation. ROMancer refuses growth that would overwrite neighboring data.',
        'Reinsertion independently decodes the result and compares every decoded byte. Unknown formats stay read-only.'], 'lz77 lz10 rle extract reinsert allocation'),
    _topic('playtest','Playtest a source or build','Use the included engine or a matching saved setup.',[
        'Choose the source or build in the top bar and open Playtest.',
        'The full Windows release selects its included engine automatically. Choose Load game, then Play; custom cores are available in Advanced setup.',
        'Focus the controller area for saved keys or a connected gamepad. Test sound checks local audio output.',
        'Pause and choose Track a value for before and after observations. Use Inspect graphics to select a sprite and trace its source.',
        'Save comparison scene during a fresh run. After editing and building, open Check my hack and choose Test captured scene to replay the same inputs.',
        'Pause before inspecting a frame or restoring a state. A state is tied to the exact core, content, options and system files.',
        'If a required core or BIOS is missing, open System setup and choose its local location. No AI service is used.'], 'audio sound controller keyboard gamepad core DLL BIOS save state muted'),
    _topic('testing','Test a ROM and compare builds','Run startup checks, then use expected results for regression.',[
        'Import your ROM and open Playtest. Use a matching saved local core setup.',
        'Check ROM runs120 frames in a fresh worker, measures video/audio and closes it. It does not certify gameplay.',
        'For regression, open More tools and Routes. Record controller input, add a measured frame or memory assertion, and stop recording.',
        'Save a cold-start test, then open Regression. Choose up to 8 routes, the original and build, then Run suite. The baseline must pass before the build is evaluated.',
        'A failure points to an expected result that changed. Baselines, coverage objectives and correct gameplay still need your definition.'], 'regression test ROM run emulator smoke baseline route crash'),
    _topic('debug','Troubleshoot a change','Compare exact bytes and measured runtime observations.',[
        'Compare the source and build to locate the changed bytes.',
        'Use the explicit system mapping to translate addresses. Supply the bank when the address is ambiguous.',
        'Load a matching Playtest session to inspect supported memory regions or add watches.',
        'Compare observations before and after the same input. A changed value does not identify the instruction that wrote it.',
        'Instruction-level features require a proven matching debugger adapter. Imported traces remain imported information.'], 'memory watch address mapping trace breakpoint reference'),
    _topic('recipes','Repeat edits offline','Save declarative operations and preview every rerun.',[
        'Open More tools, then Recipes & definitions. Select the original source revision.',
        'After reviewing or building edits, choose Save a plan as a recipe. You can also import a recipe JSON file.',
        'Preview the complete changes before building. Wrong source hashes, overlaps and unsupported commands refuse.',
        'Export the recipe or a declared text, graphics or table definition. Imports check the exact source; they cannot execute commands or load native evidence.'], 'automation script batch deterministic definition profile'),
    _topic('export','Export a working patch','Share a patch with exact source and target identities.',[
        'Open Export and select the original source and completed build.',
        'Enter a title and create a BPS patch. Preparation reconstructs the entire target independently.',
        'Use Verify patch for a fresh check against the exact original revision.',
        'Download the patch and instructions or prepare a public package. Sources, BIOS files and private captures are not included.',
        'A patch verified for one source revision must not be applied to another revision.'], 'BPS release publish package checksum verify'),
    _topic('recovery','Backups and recovery','Keep projects, drafts, sources and completed work recoverable.',[
        'Drafts save automatically and Undo draft/Redo draft operate on the last edited field.',
        'If a draft save fails, keep the window open and copy the unsaved text before reloading.',
        'Use Settings to make a complete private backup before moving a project. Restore the backup into the destination workspace.',
        'Legacy project migration saves the original metadata. Recover an abandoned lock only when the old owner is confirmed dead.',
        'Restored native reports and captures remain historical. Run fresh native checks before using them as current evidence.',
        'Rollback changes the active application version and preserves project files. Older versions may not understand newer project features.'], 'backup restore undo redo crash stale source revision lock migration'),
    _topic('shortcuts','Keyboard shortcuts','Use the same controls without a mouse.',[
        'Ctrl+K focuses workspace search. Enter opens the search results.',
        'Tab moves through controls and Enter or Space activates the focused button.',
        'In a tile editor, arrow keys move the pixel cursor and Space paints the selected palette index.',
        'During Playtest, focus the controller area. Default controls are arrows, Z for A, X for B, Enter for Start and Shift for Select.'], 'keys accessibility zoom size'),
    _topic('glossary','Terms used in ROMancer','Short definitions for common editing terms.',[
        'Source: the owned copy imported into the project. Build: a separate edited output. Neither overwrites your original file.',
        'Offset: a byte position within a file. Address: a position in a console memory map; translation may require bank information.',
        'Codec: the rule used to decode stored pixels or data. Palette: stored colors used by pixel indices.',
        'Stride: the number of bytes between records. Pointer: a stored number interpreted through an explicitly declared mapping.',
        'Allocation: the confirmed storage extent available to a resource. Candidate: a possible match that still needs confirmation.',
        'SHA-256: an exact content identity used to prevent edits or patches from being applied to the wrong revision.'], 'pointer endian bank codec source build declaration'),
    _topic('offline','Offline operation','All essential workflows run locally without AI.',[
        'Editing, help, recipes, patch verification and configured native playtests run locally.',
        'No account, API key, subscription or model service is required.',
        'Playtest requires compatible local emulator components and any system files that component needs.',
        'The full Windows release includes credited open-source engines and their source/licenses. Game images, user firmware dumps and private data are excluded. Optional external services are not required.'], 'privacy AI network internet account'),
    _topic('nes','NES system notes','Validated cartridge regions and stored CHR graphics.',[
        'iNES/NES2.0 headers describe PRG and CHR extents. A trainer changes the data offsets.',
        'Stored CHR-ROM uses planar2bpp tiles. CHR-RAM graphics are loaded by game code and are not a stored CHR-ROM region.',
        'Use NROM or an explicit PRG bank window for address translation; ROMancer does not infer every mapper state.'], 'system mapper trainer tile'),
    _topic('snes','SNES system notes','Declare mapping, header prefix and resource format.',[
        'Review LoROM/HiROM header candidates and any512-byte copier prefix.',
        'Graphics templates support paired4bpp tiles and declared palettes. Actual game compression can differ.',
        'Checksum repair requires a supported power-of-two LoROM/HiROM image. Enhancement chips and arbitrary mappings are separate capabilities.'], 'system checksum lorom hirom palette'),
    _topic('genesis','Genesis system notes','Linear cartridge data, packed pixels and RGB333 palettes.',[
        'Use a supported linear cartridge image. Interleaved storage needs a separately supported conversion.',
        'Declare packed4bpp graphics, big-endian palette words and the correct resource location.',
        'The initial linear address window and cartridge checksum are supported. Special hardware and compressed game formats require explicit support.'], 'system GEN megadrive endian'),
    _topic('gb','Game Boy system notes','Explicit ROM banks and paired2bpp tiles.',[
        'Check the DMG/CGB header flags and declared cartridge size.',
        'Game Boy tiles store two bitplanes per row; this differs from the NES tile layout.',
        'The fixed bank-zero window and selected ROM banks can be translated explicitly. Game Boy and Game Boy Color use separate hardware profiles. Original DMG and Color-only drawing programs have measured native state replay; game compatibility still needs its own tests.'], 'system gameboy bank checksum'),
    _topic('scenes','Change colors, pictures and backgrounds in Scenes & colors','Record moments of the game, change a color, a picture or the background, and look at every recorded scene that changes before anything is saved.',[
        'Open Scenes & colors with your ROM selected. A scene is a moment of the game that ROMancer has watched. Record more scenes lets the game play by itself for a few minutes. Play and capture a moment lets you play to the screen you want, then choose Capture this moment.',
        'Choose a scene, then click a pixel in its picture or a swatch under Colors in this scene. Pick the new color. The controls only offer colors the console can show: sliders for most systems, the console color chart on NES, four shades on the original Game Boy.',
        'Under Where should it change?, choose Everywhere this color is used, or Only in this scene when it is offered. Only in this scene gives that scene its own copy of the color data, and ROMancer checks by replay that the other scenes stay as they are.',
        'Choose Show what changes. The Also changes strip shows every recorded scene that uses the same data. Each picture is the real game replayed with your change. Scenes that look different come first; choose one to compare before and after.',
        'Used in N scenes counts recorded scenes only. Scenes you have not recorded cannot be shown, so record the places you care about before you save. A color is often shared by menus, levels and battles.',
        'Keep this change adds it to the Change list; Cancel drops it. Nothing is written yet. Undo removes a kept change, and Show scenes shows its pictures again. A change the replay could not confirm is marked Not confirmed by replay.',
        'Review and save replays every affected scene with all your changes together and lists everything that changes. Save as a new build writes a separate playable copy and updates the cartridge checksum when the game has one. Your original ROM is unchanged.',
        'A color with a lock cannot be changed here; choose it to see why. Either the game works the color out while it runs (a fade or a blend), or ROMancer has not seen where it comes from because it was set before recording started or the slot is unused. Try a scene recorded at a different moment.',
        'Graphics redraws a picture: click it in the scene or choose it from the list, draw pixel by pixel, or save it as a PNG and load your edited copy. Under the pictures, Save pictures as PNG saves every picture of the scene as one PNG and Save background as PNG saves a background layer the way the game lays it out, both with the colors of the scene as the palette; draw on the PNG in any image program, keep its size, and load it back to change many pictures at once. Background changes which picture a background cell shows: choose a picture and paint it into the cells. Both use Show what changes, Keep this change and Review and save in the same way as colors.',
        'Some games keep their pictures packed. ROMancer re-packs them when it recognises the packing. Otherwise the saved build gets a small run-time patch that swaps your picture in as the game loads it, and the editor shows the result both in the scene and from power-on. Super NES replays are slow: with many scenes they can take minutes.',
        'Scenes are kept with the project and are included in a complete private project backup. They belong to the original ROM: to make another version, keep editing the original and save again.',
        'If the screen says the tracing engine is not installed, this copy of ROMancer has no trace-cores folder for that system. The full Windows and Linux packages include it for NES, Super NES, Mega Drive, Master System, Game Boy and Game Boy Color.'], 'scene scenes color colour palette recolor record capture also changes change list review locked lock swatch tracing shared graphics picture tile background cell redraw paint'),

)


def help_topics(query='',topic=''):
    if type(query) is not str or len(query)>160 or type(topic) is not str or len(topic)>160:
        raise ValueError('Keep help searches to 160 characters.')
    query=query.casefold().strip()
    matches=[row for row in TOPICS if not query or query in ' '.join([row['title'],row['summary'],row['terms'],*row['steps']]).casefold()]
    selected=next((row for row in TOPICS if row['id']==topic),None)
    return {'ok':True,'topics':copy.deepcopy(matches),'selected':copy.deepcopy(selected),'offline':True}


def project_readiness(project,exports,profile_configured=False,verified_exports=()):
    sources=project.get('sources',[]);builds=project.get('builds',[])
    checks=[('import','Import a ROM',bool(sources),'resources'),
            ('resource','Choose a resource',any(row.get('descriptors') for row in sources+builds),'resources'),
            ('build','Create a build',bool(builds),'assets'),
            ('setup','Set up playtesting',bool(profile_configured),'playtest'),
            ('verify','Verify a patch',any(row.get('role')=='patch' and row.get('export_id') in verified_exports for row in exports),'release')]
    steps=[{'id':key,'title':title,'complete':complete,'page':page} for key,title,complete,page in checks]
    return {'ok':True,'steps':steps,'next_step':next((row['id'] for row in steps if not row['complete']),None),
            'game_compatibility_claimed':False,'scope':'project workflow facts; no universal game compatibility claim'}
