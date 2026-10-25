/* Synthetic native stall used only to test owned worker termination. */
#define retro_run normal_mock_run
#include "mock_libretro.c"
#undef retro_run

void retro_run(void) {
    for (;;) { }
}
