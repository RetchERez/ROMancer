/* ROMancer v7 deterministic mock libretro core.
   This is not an emulator. It exists only to exercise the v7 frontend ABI end-to-end
   without requiring a commercial game, BIOS, or third-party emulator core. */
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>

#define RETRO_API_VERSION 1
#define RETRO_DEVICE_JOYPAD 1
#define RETRO_DEVICE_ID_JOYPAD_B 0
#define RETRO_DEVICE_ID_JOYPAD_Y 1
#define RETRO_DEVICE_ID_JOYPAD_SELECT 2
#define RETRO_DEVICE_ID_JOYPAD_START 3
#define RETRO_DEVICE_ID_JOYPAD_UP 4
#define RETRO_DEVICE_ID_JOYPAD_DOWN 5
#define RETRO_DEVICE_ID_JOYPAD_LEFT 6
#define RETRO_DEVICE_ID_JOYPAD_RIGHT 7
#define RETRO_DEVICE_ID_JOYPAD_A 8
#define RETRO_DEVICE_ID_JOYPAD_X 9
#define RETRO_DEVICE_ID_JOYPAD_L 10
#define RETRO_DEVICE_ID_JOYPAD_R 11
#define RETRO_MEMORY_SAVE_RAM 0
#define RETRO_MEMORY_SYSTEM_RAM 2
#define RETRO_MEMORY_VIDEO_RAM 3
#define RETRO_MEMORY_ROM 4
#define RETRO_ENVIRONMENT_SET_PIXEL_FORMAT 10
#define RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS 11
#define RETRO_PIXEL_FORMAT_RGB565 2

struct retro_game_info { const char *path; const void *data; size_t size; const char *meta; };
struct retro_system_info { const char *library_name; const char *library_version; const char *valid_extensions; bool need_fullpath; bool block_extract; };
struct retro_game_geometry { unsigned base_width, base_height, max_width, max_height; float aspect_ratio; };
struct retro_system_timing { double fps, sample_rate; };
struct retro_system_av_info { struct retro_game_geometry geometry; struct retro_system_timing timing; };
struct retro_input_descriptor { unsigned port, device, index, id; const char *description; };

typedef bool (*retro_environment_t)(unsigned, void *);
typedef void (*retro_video_refresh_t)(const void *, unsigned, unsigned, size_t);
typedef void (*retro_audio_sample_t)(int16_t, int16_t);
typedef size_t (*retro_audio_sample_batch_t)(const int16_t *, size_t);
typedef void (*retro_input_poll_t)(void);
typedef int16_t (*retro_input_state_t)(unsigned, unsigned, unsigned, unsigned);

static retro_environment_t env_cb;
static retro_video_refresh_t video_cb;
static retro_audio_sample_t audio_cb;
static retro_audio_sample_batch_t audio_batch_cb;
static retro_input_poll_t poll_cb;
static retro_input_state_t input_cb;
static uint8_t sysram[256];
static uint8_t saveram[64];
static uint8_t vram[128];
static uint8_t romshadow[64];
static uint16_t framebuf[16 * 16];
static unsigned tick_count;

static const struct retro_input_descriptor input_desc[] = {
 {0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_UP, "Mock Up"},
 {0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_DOWN, "Mock Down"},
 {0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_LEFT, "Mock Left"},
 {0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_RIGHT, "Mock Right"},
 {0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_A, "Mock Action"},
 {0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_START, "Mock Menu"},
 {0,0,0,0,NULL}
};

unsigned retro_api_version(void) { return RETRO_API_VERSION; }
void retro_set_environment(retro_environment_t cb) { env_cb = cb; }
void retro_set_video_refresh(retro_video_refresh_t cb) { video_cb = cb; }
void retro_set_audio_sample(retro_audio_sample_t cb) { audio_cb = cb; }
void retro_set_audio_sample_batch(retro_audio_sample_batch_t cb) { audio_batch_cb = cb; }
void retro_set_input_poll(retro_input_poll_t cb) { poll_cb = cb; }
void retro_set_input_state(retro_input_state_t cb) { input_cb = cb; }
void retro_set_controller_port_device(unsigned port, unsigned device) { (void)port; (void)device; }

void retro_init(void) {
  int fmt = RETRO_PIXEL_FORMAT_RGB565;
  if (env_cb) {
    env_cb(RETRO_ENVIRONMENT_SET_PIXEL_FORMAT, &fmt);
    env_cb(RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS, (void*)input_desc);
  }
}
void retro_deinit(void) {}
void retro_get_system_info(struct retro_system_info *info) {
  info->library_name="ROMancer Mock Core"; info->library_version="1.0";
  info->valid_extensions="bin"; info->need_fullpath=false; info->block_extract=false;
}
void retro_get_system_av_info(struct retro_system_av_info *info) {
  info->geometry.base_width=16; info->geometry.base_height=16;
  info->geometry.max_width=16; info->geometry.max_height=16; info->geometry.aspect_ratio=1.0f;
  info->timing.fps=60.0; info->timing.sample_rate=44100.0;
}
bool retro_load_game(const struct retro_game_info *game) {
  memset(sysram,0,sizeof(sysram)); memset(vram,0,sizeof(vram)); tick_count=0;
#ifdef ROMANCER_V35_TEST
  memset(saveram,0,sizeof(saveram));
#endif
  sysram[0]=8; sysram[1]=8;
  if (game && game->data && game->size) {
    size_t n=game->size < sizeof(romshadow) ? game->size : sizeof(romshadow);
    memcpy(romshadow,game->data,n);
  }
  return true;
}
void retro_unload_game(void) {}
void retro_reset(void) { sysram[0]=8; sysram[1]=8; sysram[2]=0; tick_count=0; }

static void draw_frame(void) {
  unsigned x=sysram[0]&15, y=sysram[1]&15;
  uint16_t bg=0x0000;
  for (unsigned i=0;i<256;i++) framebuf[i]=bg;
  framebuf[y*16+x] = sysram[2] ? 0xF800 : 0xFFFF;
  if (sysram[3]) {
    for (unsigned i=0;i<16;i++) framebuf[i]=0x07E0;
  }
}
void retro_run(void) {
  if (poll_cb) poll_cb();
  if (input_cb) {
    if (input_cb(0,RETRO_DEVICE_JOYPAD,0,RETRO_DEVICE_ID_JOYPAD_LEFT) && sysram[0]>0) sysram[0]--;
    if (input_cb(0,RETRO_DEVICE_JOYPAD,0,RETRO_DEVICE_ID_JOYPAD_RIGHT) && sysram[0]<15) sysram[0]++;
    if (input_cb(0,RETRO_DEVICE_JOYPAD,0,RETRO_DEVICE_ID_JOYPAD_UP) && sysram[1]>0) sysram[1]--;
    if (input_cb(0,RETRO_DEVICE_JOYPAD,0,RETRO_DEVICE_ID_JOYPAD_DOWN) && sysram[1]<15) sysram[1]++;
    if (input_cb(0,RETRO_DEVICE_JOYPAD,0,RETRO_DEVICE_ID_JOYPAD_A)) sysram[2]^=1;
#ifdef ROMANCER_V35_TEST
    if (input_cb(0,RETRO_DEVICE_JOYPAD,0,RETRO_DEVICE_ID_JOYPAD_A)) saveram[0]++;
#endif
    if (input_cb(0,RETRO_DEVICE_JOYPAD,0,RETRO_DEVICE_ID_JOYPAD_START)) sysram[3]^=1;
  }
  tick_count++;
  draw_frame();
  if (video_cb) video_cb(framebuf,16,16,16*2);
#ifdef ROMANCER_V35_TEST
  static const int16_t audio_frames[] = {-32768,32767,-1,1,0,0,4660,-4660};
  if (audio_batch_cb) audio_batch_cb(audio_frames,4);
#endif
}

size_t retro_serialize_size(void) { return sizeof(sysram)+sizeof(saveram)+sizeof(tick_count); }
bool retro_serialize(void *data, size_t size) {
  if (!data || size < retro_serialize_size()) return false;
  uint8_t *p=(uint8_t*)data; memcpy(p,sysram,sizeof(sysram)); p+=sizeof(sysram);
  memcpy(p,saveram,sizeof(saveram)); p+=sizeof(saveram); memcpy(p,&tick_count,sizeof(tick_count)); return true;
}
bool retro_unserialize(const void *data, size_t size) {
  if (!data || size < retro_serialize_size()) return false;
  const uint8_t *p=(const uint8_t*)data; memcpy(sysram,p,sizeof(sysram)); p+=sizeof(sysram);
  memcpy(saveram,p,sizeof(saveram)); p+=sizeof(saveram); memcpy(&tick_count,p,sizeof(tick_count)); draw_frame(); return true;
}
void *retro_get_memory_data(unsigned id) {
  if (id==RETRO_MEMORY_SAVE_RAM) return saveram;
  if (id==RETRO_MEMORY_SYSTEM_RAM) return sysram;
  if (id==RETRO_MEMORY_VIDEO_RAM) return vram;
  if (id==RETRO_MEMORY_ROM) return romshadow;
  return NULL;
}
size_t retro_get_memory_size(unsigned id) {
  if (id==RETRO_MEMORY_SAVE_RAM) return sizeof(saveram);
  if (id==RETRO_MEMORY_SYSTEM_RAM) return sizeof(sysram);
  if (id==RETRO_MEMORY_VIDEO_RAM) return sizeof(vram);
  if (id==RETRO_MEMORY_ROM) return sizeof(romshadow);
  return 0;
}

/* Optional libretro API entry points not used by ROMancer v7 frontend. */
unsigned retro_get_region(void) { return 0; }
void *retro_get_memory_data_dummy(unsigned id) { (void)id; return NULL; }
void retro_cheat_reset(void) {}
void retro_cheat_set(unsigned index, bool enabled, const char *code) { (void)index;(void)enabled;(void)code; }
bool retro_load_game_special(unsigned game_type, const struct retro_game_info *info, size_t num_info) { (void)game_type;(void)info;(void)num_info; return false; }
