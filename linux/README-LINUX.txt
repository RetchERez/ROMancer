ROMancer v1.3.9 for Linux x86-64
By RetchEWretched

1. Extract the archive:   tar xf ROMancer-v1.3.9-Linux-x86_64.tar.gz
2. Start ROMancer:        ./ROMancer-v1.3.9-Linux-x86_64/ROMancer.sh
   (or double-click ROMancer.sh in your file manager and choose Run)
3. Open the included practice game or import your ROM.

Optional: ./ROMancer.sh --install-desktop adds ROMancer to your application menu.

Requirements: 64-bit x86 Linux with glibc 2.28 or newer (Ubuntu 20.04+,
Debian 10+, Fedora 29+, Linux Mint 20+, SteamOS 3) and a web browser.
ROMancer opens in an app window when Chrome, Chromium, Edge, Brave or Vivaldi
is installed, and otherwise in your default browser.

New in v1.1: Scenes & colors. Change a color, a picture or the background and
see every recorded scene it touches before you save. Open Help and choose the
Scenes & colors topic.

Python, Pillow, the emulator engines and the tracing engines that Scenes &
colors uses are included. Nothing is installed
system-wide. Projects live under ~/.local/share/ROMancer/workspace
(set ROMANCER_WORKSPACE or use --workspace <path> to choose another folder).

Playtest audio and controllers use your browser. Plug in the controller and
press a button with the ROMancer window focused so the browser detects it.

Other options:
  ./ROMancer.sh --check        verify the bundled runtime and exit
  ./ROMancer.sh --no-browser   start the local server only and print its address

The native debuggers (MAME and Mesen captures) are Windows-only;
everything else matches the Windows release.

Keep ROMancer.sh and the "ROMancer Files" folder together.
Engine licenses and corresponding source: ROMancer Files/Runtime/cores.
Tracing engine notices and source changes: ROMancer Files/Runtime/trace-cores.
Open ROMancer Files/Runtime/app/user-guide/index.html for the guide.
