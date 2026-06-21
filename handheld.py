                      

import os

import sys

import time

import struct

import threading

import random

import json

import base64

import builtins

import re



def print(*args, **kwargs):

    builtins.print(*args, **kwargs)

    try:

        with open("/home/user/trans/execute/handheld.log", "a") as f:

            builtins.print(*args, **kwargs, file=f)

    except:

        pass



                         

M0_PIN = 23

M1_PIN = 24

AUX_PIN = 25



SIMULATION_MODE = False

SIMULATED_PACKET_LOSS = 0.0

SIMULATED_TX_DELAY = 50                                      

CURRENT_AIR_RATE = 0.3



                      

DEFAULT_LCD_ADDR = 0x3f

LCD_PORT = 1



                         

telemetry_log = []

telemetry_lock = threading.Lock()



incoming_messages = []

msg_lock = threading.Lock()



active_handshake_state = None

state_lock = threading.Lock()



pending_responses = {}

pending_lock = threading.Lock()

BEST_EFFORT_RX = False

outbound_lock = threading.Lock()

EMG_TST_MODE = True

last_heartbeat_time = time.time()

last_other_activity_time = 0.0

active_cmd_output = []

cmd_output_lock = threading.Lock()

command_eof_received = False

active_tickets = {}

current_command_ticket_id = None

cmd_output_dirty = False

option_index = 0

typed_command = ""

typed_cmd_input = ""

has_connected_to_base = False





pending_pings = {}

ping_lock = threading.Lock()



pending_config_proposals = {}



active_rx_sessions = {}

rx_sessions_lock = threading.Lock()



virtual_rx_sessions = {}

rx_count = 0

tx_count = 0

ui_state = "MENU"

msg_to_read = ""

msg_prompt_start_time = 0.0

msg_prompt_index = 0



                    

try:

    import RPi.GPIO as GPIO

    import serial

except ImportError:

    SIMULATION_MODE = True



lcd_lock = threading.RLock()



                                       

class I2CLCD:

    def __init__(self, addr=DEFAULT_LCD_ADDR, port=LCD_PORT):

        import fcntl

        I2C_SLAVE = 0x0703

        self.addr = addr

        self.enabled = False

        self.line_cache = {1: "", 2: "", 3: "", 4: ""}

        try:

                                                            

            import subprocess

            try:

                subprocess.run(["pinctrl", "set", "2", "a0"], check=False)

                subprocess.run(["pinctrl", "set", "3", "a0"], check=False)

            except:

                pass



                                                                    

            self.fd = os.open(f"/dev/i2c-{port}", os.O_RDWR)

                                                                             

            fcntl.ioctl(self.fd, I2C_SLAVE, self.addr)

            self.bl_state = 0x08               



                                                    

            self.pulse_nibble(0x30)

            time.sleep(0.005)

            self.pulse_nibble(0x30)

            time.sleep(0.001)

            self.pulse_nibble(0x30)

            self.pulse_nibble(0x20)                                           



                                           

            self.send_byte(0x28, 0)                           

            self.send_byte(0x0C, 0)                               

            self.send_byte(0x06, 0)                       

            self.send_byte(0x01, 0)                                     

            time.sleep(0.002)



            self.enabled = True

            print(f"LCD successfully initialized at I2C address {hex(addr)}")

        except Exception as e:

            print(f"LCD Init failed: {e}. Emulating LCD in stdout.")

            self.enabled = False



    def write_raw_bus(self, value):

        if not hasattr(self, 'fd'): return

        os.write(self.fd, bytes([value | self.bl_state]))



    def pulse_enable(self, value):

        self.write_raw_bus(value | 0x04)             

        time.sleep(0.00005)

        self.write_raw_bus(value & ~0x04)

        time.sleep(0.00005)



    def pulse_nibble(self, nibble_value):

        upper = nibble_value & 0xF0

        self.write_raw_bus(upper)

        self.pulse_enable(upper)



    def send_byte(self, byte_value, mode_bit=0):

                                                       

        if byte_value == 0x01 and mode_bit == 0:

            self.line_cache = {1: "", 2: "", 3: "", 4: ""}

            

                                                                                  

        hi_nibble = (byte_value & 0xF0) | mode_bit

        lo_nibble = ((byte_value << 4) & 0xF0) | mode_bit

        

        with lcd_lock:

            self.write_raw_bus(hi_nibble)

            self.pulse_enable(hi_nibble)

            self.write_raw_bus(lo_nibble)

            self.pulse_enable(lo_nibble)



    def display_text(self, text, line):

        line_offsets = {1: 0x80, 2: 0xC0, 3: 0x94, 4: 0xD4}

        if line not in line_offsets: return

        

        formatted = text[:20].ljust(20, " ")

        if self.line_cache.get(line) == formatted:

            return                       

            

        self.line_cache[line] = formatted

        if self.enabled:

            with lcd_lock:

                self.send_byte(line_offsets[line], 0)

                for char in formatted:

                    self.send_byte(ord(char), 0x01)              

        else:

                                          

            pass



    def set_backlight(self, state_on=True):

        with lcd_lock:

            self.bl_state = 0x08 if state_on else 0x00

            self.write_raw_bus(0x00)



    def close(self):

        if self.enabled:

            os.close(self.fd)



    def load_custom_char(self, slot, pattern):

        """Load a custom 5x8 bitmap into CGRAM slot (0-7)."""

        if not self.enabled or slot < 0 or slot > 7: return

        with lcd_lock:

            self.send_byte(0x40 + (slot * 8), 0)                     

            for row in pattern:

                self.send_byte(row, 0x01)                      

            self.send_byte(0x80, 0)                  



    def load_char_page(self, page_name):

        """Load a set of 8 custom characters by page name."""

        if not self.enabled: return

        if hasattr(self, '_current_char_page') and self._current_char_page == page_name:

            return                  

        self._current_char_page = page_name

        chars = CHAR_PAGES.get(page_name, {})

        with lcd_lock:

            for slot, pattern in chars.items():

                self.load_custom_char(slot, pattern)



    def write_char_at(self, line, col, char_code):

        """Write a single character at a specific position without touching cache."""

        line_offsets = {1: 0x80, 2: 0xC0, 3: 0x94, 4: 0xD4}

        if line not in line_offsets or col < 0 or col > 19: return

        if self.enabled:

            with lcd_lock:

                self.send_byte(line_offsets[line] + col, 0)

                self.send_byte(char_code, 0x01)



    def write_line_raw(self, line, text):

        """Write a full line directly to LCD, bypassing cache. Used for transitions."""

        line_offsets = {1: 0x80, 2: 0xC0, 3: 0x94, 4: 0xD4}

        if line not in line_offsets: return

        formatted = text[:20].ljust(20, " ")

        if self.enabled:

            with lcd_lock:

                self.send_byte(line_offsets[line], 0)

                for char in formatted:

                    self.send_byte(ord(char), 0x01)

                               

        self.line_cache[line] = formatted



                 

lcd = I2CLCD()



                                                                 

                                                                 

                                                                 



                                                          

_CHAR_BAR_EMPTY = [0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b11111]

_CHAR_BAR_1     = [0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b11111]

_CHAR_BAR_2     = [0b11000, 0b11000, 0b11000, 0b11000, 0b11000, 0b11000, 0b11000, 0b11111]

_CHAR_BAR_3     = [0b11100, 0b11100, 0b11100, 0b11100, 0b11100, 0b11100, 0b11100, 0b11111]

_CHAR_BAR_4     = [0b11110, 0b11110, 0b11110, 0b11110, 0b11110, 0b11110, 0b11110, 0b11111]

_CHAR_BAR_FULL  = [0b11111, 0b11111, 0b11111, 0b11111, 0b11111, 0b11111, 0b11111, 0b11111]

_CHAR_SPINNER   = [

    [0b00000, 0b00000, 0b00000, 0b00100, 0b00000, 0b00000, 0b00000, 0b00000],                                

    [0b00000, 0b00000, 0b00100, 0b01010, 0b00100, 0b00000, 0b00000, 0b00000],                                          

    [0b00000, 0b00100, 0b01010, 0b10001, 0b01010, 0b00100, 0b00000, 0b00000],                                          

    [0b00000, 0b00000, 0b00100, 0b01010, 0b00100, 0b00000, 0b00000, 0b00000]                                         

]





                                                   

_CHAR_CIRCLE    = [0b00000, 0b00100, 0b01110, 0b01110, 0b01110, 0b00100, 0b00000, 0b00000]

_CHAR_ARROW     = [0b00000, 0b01000, 0b01100, 0b11111, 0b01100, 0b01000, 0b00000, 0b00000]

_CHAR_WAVE_1    = [0b00000, 0b00000, 0b00100, 0b01010, 0b00100, 0b00000, 0b00000, 0b00000]

_CHAR_WAVE_2    = [0b00000, 0b00100, 0b01010, 0b10001, 0b01010, 0b00100, 0b00000, 0b00000]

_CHAR_WAVE_3    = [0b00100, 0b01010, 0b10001, 0b00000, 0b10001, 0b01010, 0b00100, 0b00000]

_CHAR_LOCK      = [0b01110, 0b10001, 0b10001, 0b11111, 0b11011, 0b11011, 0b11111, 0b00000]

_CHAR_CHECK     = [0b00000, 0b00000, 0b00001, 0b00010, 0b10100, 0b01000, 0b00000, 0b00000]

_CHAR_CROSS     = [0b00000, 0b10001, 0b01010, 0b00100, 0b01010, 0b10001, 0b00000, 0b00000]

_CHAR_ANTENNA   = [0b00100, 0b01110, 0b00100, 0b11111, 0b00100, 0b00100, 0b01110, 0b11111]

_CHAR_MAIL      = [0b00000, 0b11111, 0b10001, 0b10101, 0b11011, 0b10001, 0b11111, 0b00000]



CHAR_PAGES = {

    "progress": {

        0: _CHAR_BAR_EMPTY,

        1: _CHAR_BAR_1,

        2: _CHAR_BAR_2,

        3: _CHAR_BAR_3,

        4: _CHAR_BAR_4,

        5: _CHAR_BAR_FULL,

        6: _CHAR_SPINNER[0],                         

        7: _CHAR_SPINNER[1],

    },

    "menu": {

        0: _CHAR_CIRCLE,

        1: _CHAR_WAVE_1,

        2: _CHAR_WAVE_2,

        3: _CHAR_WAVE_3,

        4: _CHAR_CHECK,

        5: _CHAR_CROSS,

        6: _CHAR_ANTENNA,

        7: _CHAR_MAIL,

    }

}



_ping_pong_indicator = " "

_indicator_timer = None

refresh_lcd_global = None



def set_ping_pong_indicator(char_str):

    global _ping_pong_indicator, _indicator_timer

    _ping_pong_indicator = char_str

    if ui_state == "MENU" and refresh_lcd_global:

        refresh_lcd_global()

    if char_str == chr(0x00):          

        if _indicator_timer:

            _indicator_timer.cancel()

        def clear_ind():

            global _ping_pong_indicator

            _ping_pong_indicator = " "

            if ui_state == "MENU" and refresh_lcd_global:

                refresh_lcd_global()

        _indicator_timer = threading.Timer(1.0, clear_ind)

        _indicator_timer.daemon = True

        _indicator_timer.start()



                                                                 

                  

                                                                 



_anim_state = {

    "spinner_frame": 0,

    "spinner_active": False,

    "spinner_line": 4,

    "spinner_col": 19,

    "progress_pct": 0.0,

    "progress_active": False,

    "progress_line": 4,

    "wave_frame": 0,

    "wave_active": False,

}

_pending_transition = "none"

_anim_lock = threading.Lock()



def start_spinner(line=4, col=19):

    with _anim_lock:

        _anim_state["spinner_active"] = True

        _anim_state["spinner_frame"] = 0

        _anim_state["spinner_line"] = line

        _anim_state["spinner_col"] = col

    lcd.load_char_page("progress")



def stop_spinner():

    with _anim_lock:

        _anim_state["spinner_active"] = False

                                          

    with lcd_lock:

        lcd.write_char_at(_anim_state["spinner_line"], _anim_state["spinner_col"], ord(' '))



def set_progress_bar(pct, line=4):

    """Set progress bar percentage (0.0 to 1.0). Uses 16 cells (cols 2-17)."""

    with _anim_lock:

        _anim_state["progress_pct"] = max(0.0, min(1.0, pct))

        _anim_state["progress_active"] = True

        _anim_state["progress_line"] = line

    lcd.load_char_page("progress")

    _render_progress_bar()



def stop_progress_bar():

    with _anim_lock:

        _anim_state["progress_active"] = False



def _render_progress_bar():

    """Render the progress bar using custom characters on the configured line."""

    with _anim_lock:

        pct = _anim_state["progress_pct"]

        line = _anim_state["progress_line"]

        if not _anim_state["progress_active"]:

            return

    

    bar_width = 16                                 

    total_units = bar_width * 5                            

    filled_units = int(pct * total_units)

    

    bar_chars = []

    for i in range(bar_width):

        cell_start = i * 5

        cell_fill = min(5, max(0, filled_units - cell_start))

        bar_chars.append(cell_fill)                                

    

    pct_str = f"{int(pct * 100):3d}%"

                                                            

                                                       

    with lcd_lock:

        line_offsets = {1: 0x80, 2: 0xC0, 3: 0x94, 4: 0xD4}

        if line not in line_offsets or not lcd.enabled:

            return

        lcd.send_byte(line_offsets[line], 0)

                                                

        for ch in bar_chars:

            lcd.send_byte(ch, 0x01)                                             

                                                   

        for c in pct_str:

            lcd.send_byte(ord(c), 0x01)

                      

                                                                               

        cache_str = ''.join([chr(ch) for ch in bar_chars]) + pct_str

        lcd.line_cache[line] = cache_str

        current_lcd_status[f"line{line}"] = cache_str



def start_wave_animation():

    with _anim_lock:

        _anim_state["wave_active"] = True

        _anim_state["wave_frame"] = 0

    lcd.load_char_page("menu")



def stop_wave_animation():

    with _anim_lock:

        _anim_state["wave_active"] = False



def _lcd_animation_thread():

    """Background thread that drives spinner rotation and wave animation."""

    tick = 0

    while True:

        try:

            time.sleep(0.125)        

            tick += 1

            

            with _anim_lock:

                spinner_on = _anim_state["spinner_active"]

                wave_on = _anim_state["wave_active"]

            

                                                

            if spinner_on:

                with _anim_lock:

                    frame = _anim_state["spinner_frame"]

                    _anim_state["spinner_frame"] = (frame + 1) % 4

                    s_line = _anim_state["spinner_line"]

                    s_col = _anim_state["spinner_col"]

                

                                                            

                with lcd_lock:

                    lcd.load_custom_char(6, _CHAR_SPINNER[frame])

                    lcd.write_char_at(s_line, s_col, 6)                         

            

                                                      

            if wave_on and (tick % 4 == 0):

                with _anim_lock:

                    wf = _anim_state["wave_frame"]

                    _anim_state["wave_frame"] = (wf + 1) % 3

                    new_wf = _anim_state["wave_frame"]

                

                                                                           

                with lcd_lock:

                    lcd.write_char_at(1, 0, new_wf + 1)                             

        except Exception:

            pass



                        

threading.Thread(target=_lcd_animation_thread, daemon=True).start()



                                                                 

                           

                                                                 



def lcd_transition(style, new_l1, new_l2, new_l3, new_l4):

    """Perform a visual transition to new screen content."""

    if not lcd.enabled or style == "none":

                                               

        with lcd_lock:

            lcd.display_text(new_l1, 1)

            lcd.display_text(new_l2, 2)

            lcd.display_text(new_l3, 3)

            lcd.display_text(new_l4, 4)

        return

    

    new_lines = [

        new_l1[:20].ljust(20),

        new_l2[:20].ljust(20),

        new_l3[:20].ljust(20),

        new_l4[:20].ljust(20),

    ]

    old_lines = [

        lcd.line_cache.get(1, " " * 20),

        lcd.line_cache.get(2, " " * 20),

        lcd.line_cache.get(3, " " * 20),

        lcd.line_cache.get(4, " " * 20),

    ]

    

    if style == "wipe_right":

                                                    

        for col in range(0, 20, 2):                                      

            with lcd_lock:

                for i, line_num in enumerate([1, 2, 3, 4]):

                    lcd.write_char_at(line_num, col, ord(new_lines[i][col]))

                    if col + 1 < 20:

                        lcd.write_char_at(line_num, col + 1, ord(new_lines[i][col + 1]))

            time.sleep(0.018)

                    

        with lcd_lock:

            for i, line_num in enumerate([1, 2, 3, 4]):

                lcd.line_cache[line_num] = new_lines[i]

    

    elif style == "wipe_left":

                                                    

        for col in range(18, -1, -2):                       

            with lcd_lock:

                for i, line_num in enumerate([1, 2, 3, 4]):

                    lcd.write_char_at(line_num, col, ord(new_lines[i][col]))

                    if col + 1 < 20:

                        lcd.write_char_at(line_num, col + 1, ord(new_lines[i][col + 1]))

            time.sleep(0.018)

        with lcd_lock:

            for i, line_num in enumerate([1, 2, 3, 4]):

                lcd.line_cache[line_num] = new_lines[i]

    

    elif style == "flash":

                                       

        with lcd_lock:

            for line_num in [1, 2, 3, 4]:

                lcd.write_line_raw(line_num, " " * 20)

        time.sleep(0.08)

        with lcd_lock:

            for i, line_num in enumerate([1, 2, 3, 4]):

                lcd.write_line_raw(line_num, new_lines[i])

    

    elif style == "scroll_up":

                                                                               

        with lcd_lock:

            lcd.write_line_raw(1, old_lines[1])

            lcd.write_line_raw(2, old_lines[2])

            lcd.write_line_raw(3, old_lines[3])

            lcd.write_line_raw(4, new_lines[0])

        time.sleep(0.04)

        with lcd_lock:

            lcd.write_line_raw(1, old_lines[2])

            lcd.write_line_raw(2, old_lines[3])

            lcd.write_line_raw(3, new_lines[0])

            lcd.write_line_raw(4, new_lines[1])

        time.sleep(0.04)

        with lcd_lock:

            lcd.write_line_raw(1, old_lines[3])

            lcd.write_line_raw(2, new_lines[0])

            lcd.write_line_raw(3, new_lines[1])

            lcd.write_line_raw(4, new_lines[2])

        time.sleep(0.04)

        with lcd_lock:

            lcd.write_line_raw(1, new_lines[0])

            lcd.write_line_raw(2, new_lines[1])

            lcd.write_line_raw(3, new_lines[2])

            lcd.write_line_raw(4, new_lines[3])

    else:

                                

        with lcd_lock:

            lcd.display_text(new_l1, 1)

            lcd.display_text(new_l2, 2)

            lcd.display_text(new_l3, 3)

            lcd.display_text(new_l4, 4)



                                                                      

                                                            

_STATE_CATEGORIES = {

    "MENU": "menu",

    "SEND_OPTION": "submenu", "SEND_MSG": "submenu", "RATE_MENU": "submenu",

    "CHAN_MENU": "submenu", "POWER_MENU": "submenu", "VIEW_LOGS": "submenu",

    "LOG_DETAIL": "submenu", "VIEW_INBOX": "submenu", "INBOX_DETAIL": "submenu",

    "WIFI_LIST": "submenu", "WIFI_PASSWORD": "submenu", "COMMAND_INPUT": "submenu",

    "SENDING": "action", "PINGING": "action", "RECEIVING": "action",

    "WIFI_SCANNING": "action", "WIFI_CONNECTING": "action", "RADIO_CONFIG": "action",

    "COMMAND_RUNNING": "action",

    "SEND_RESULT": "result", "PING_RESULT": "result", "CONFIG_TOGGLED": "result",

    "WIFI_CONNECT_RESULT": "result", "COMMAND_FINISHED": "result",

    "MSG_PROMPT": "alert", "MSG_READ": "submenu",

    "EMG_TST_SEARCH": "alert", "BASE_FOUND": "alert",

    "COMMAND_INPUT_PROMPT": "submenu",

}



def _get_transition_style(old_state, new_state):

    """Determine the transition style for a state change."""

    old_cat = _STATE_CATEGORIES.get(old_state, "menu")

    new_cat = _STATE_CATEGORIES.get(new_state, "menu")

    

                                                                         

    if old_state == new_state:

        return "none"

    

                                 

    if old_cat == "menu" and new_cat == "submenu":

        return "wipe_right"

                                

    if new_cat == "menu" and old_cat in ("submenu", "result", "action"):

        return "wipe_left"

                                           

    if old_cat == "submenu" and new_cat == "submenu" and old_state != new_state:

        return "wipe_right"

                               

    if new_cat == "action":

        return "flash"

                               

    if new_cat == "result":

        return "flash"

                                                

    if new_cat == "alert":

        return "scroll_up"

    

    return "none"



                 

lcd = I2CLCD()





                    

current_lcd_status = {

    "line1": "WackNet Handheld",

    "line2": "R:2.4k C:15 D:50",

    "line3": "Status: Link Idle",

    "line4": "Ping: -- ms  Rx: 0"

}

                                                



def print_terminal_backup():

    print("\033[H\033[2J", end="")                

    print("========================================")

    print("    WACKNET LORA HANDHELD TRANSCEIVER   ")

    print("========================================")

    print(f" [Link Mode] {'SIMULATOR' if SIMULATION_MODE else 'HARDWARE'}")

    print(f" [Air Rate]  {CURRENT_AIR_RATE} kbps")

    print(f" [TX Delay]  {SIMULATED_TX_DELAY} ms")

    print(f" [Channel]   {CURRENT_CHANNEL} ({410 + CURRENT_CHANNEL} MHz)")

    power_names = ["Max", "Med-High", "Med-Low", "Min"]

    p_str = power_names[CURRENT_POWER] if CURRENT_POWER < len(power_names) else str(CURRENT_POWER)

    print(f" [Tx Power]  {p_str}")

    print(f" [Counters]  TX: {tx_count} / RX: {rx_count}")

    print(f" [UI State]  {ui_state}")

    print("----------------------------------------")

    print(" LCD Display:")

    print(f"  [{current_lcd_status['line1']}]")

    print(f"  [{current_lcd_status['line2']}]")

    print(f"  [{current_lcd_status['line3']}]")

    print(f"  [{current_lcd_status['line4']}]")

    print("----------------------------------------")

    print(" Navigate list using Arrow keys / W/S. ")

    print(" Press Enter to select/confirm/detail. ")

    print(" Press Esc/Backspace to return/back.    ")

    print("========================================")

    sys.stdout.flush()



def update_lcd(l1=None, l2=None, l3=None, l4=None, from_ui=False):

    global ui_state

    with lcd_lock:

        if l1 is not None: current_lcd_status["line1"] = l1

        if l2 is not None: current_lcd_status["line2"] = l2

        if l3 is not None: current_lcd_status["line3"] = l3

        if l4 is not None: current_lcd_status["line4"] = l4

        

                                                                                      

        if from_ui or ui_state in ("RECEIVING", "SENDING", "PINGING"):

            lcd.display_text(current_lcd_status["line1"], 1)

            lcd.display_text(current_lcd_status["line2"], 2)

            lcd.display_text(current_lcd_status["line3"], 3)

            lcd.display_text(current_lcd_status["line4"], 4)

            

        print_terminal_backup()



def scan_wifi():

    global SIMULATION_MODE

    if SIMULATION_MODE:

        return [

            {"ssid": "TWIN", "signal": 95, "security": "WPA2"},

            {"ssid": "Tactical_Net", "signal": 75, "security": "WPA2"},

            {"ssid": "Guest_Wifi", "signal": 40, "security": "--"}

        ]

    import subprocess

    try:

        subprocess.run(["nmcli", "device", "wifi", "rescan"], capture_output=True, check=False)

        out = subprocess.check_output(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"], text=True)

        networks = []

        for line in out.splitlines():

            temp_line = line.replace("\\:", "__COLON__")

            parts = temp_line.split(":")

            if len(parts) >= 3:

                ssid = parts[0].replace("__COLON__", ":")

                signal = parts[1]

                security = parts[2].replace("__COLON__", ":")

                if not ssid:

                    continue

                networks.append({"ssid": ssid, "signal": int(signal) if signal.isdigit() else 0, "security": security})

        dedup = {}

        for net in networks:

            ssid = net["ssid"]

            if ssid not in dedup or net["signal"] > dedup[ssid]["signal"]:

                dedup[ssid] = net

        return sorted(list(dedup.values()), key=lambda x: x["signal"], reverse=True)

    except Exception as e:

        print(f"Error scanning WiFi: {e}")

        return []



def connect_wifi(ssid, password):

    global SIMULATION_MODE

    if SIMULATION_MODE:

        if ssid == "Tactical_Net" and password != "tactical123":

            return {"status": "error", "message": "Incorrect password"}

        return {"status": "success", "message": f"Successfully connected to mock WiFi: {ssid}"}

    import subprocess

    try:

        if password:

            cmd = ["sudo", "nmcli", "device", "wifi", "connect", ssid, "password", password]

        else:

            cmd = ["sudo", "nmcli", "device", "wifi", "connect", ssid]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

        if res.returncode == 0:

            return {"status": "success", "message": res.stdout.strip()}

        else:

            return {"status": "error", "message": res.stderr.strip()}

    except subprocess.TimeoutExpired:

        return {"status": "error", "message": "Connection attempt timed out"}

    except Exception as e:

        return {"status": "error", "message": str(e)}





def parse_keys(b):

    keys = []

    i = 0

    while i < len(b):

        if b[i] == 0x1b:

            if i + 2 < len(b) and b[i+1] == 0x5b:          

                j = i + 2

                while j < len(b) and not (0x40 <= b[j] <= 0x7E):

                    j += 1

                if j < len(b):

                    seq = b[i:j+1]

                    if seq == b'\x1b[A': keys.append('UP')

                    elif seq == b'\x1b[B': keys.append('DOWN')

                    elif seq == b'\x1b[C': keys.append('RIGHT')

                    elif seq == b'\x1b[D': keys.append('LEFT')

                    else: keys.append('\x1b')

                    i = j + 1

                    continue

            keys.append('\x1b')

            i += 1

        else:

            char_code = b[i]

            if char_code in (0x7f, 0x08):

                keys.append('\x7f')

            elif char_code in (0x0d, 0x0a):

                keys.append('\n')

            else:

                try:

                    char = b[i:i+1].decode('utf-8')

                    keys.append(char)

                except:

                    pass

            i += 1

    return keys



def update_lcd_ui(l1=None, l2=None, l3=None, l4=None):

    global _pending_transition

    style = _pending_transition

    _pending_transition = "none"

    if style != "none":

                               

        lcd_transition(style,

            l1 if l1 is not None else current_lcd_status["line1"],

            l2 if l2 is not None else current_lcd_status["line2"],

            l3 if l3 is not None else current_lcd_status["line3"],

            l4 if l4 is not None else current_lcd_status["line4"]

        )

        with lcd_lock:

            if l1 is not None: current_lcd_status["line1"] = l1

            if l2 is not None: current_lcd_status["line2"] = l2

            if l3 is not None: current_lcd_status["line3"] = l3

            if l4 is not None: current_lcd_status["line4"] = l4

        print_terminal_backup()

    else:

        update_lcd(l1, l2, l3, l4, from_ui=True)



                                           

class MockGPIO:

    OUT = 1

    IN = 0

    LOW = 0

    HIGH = 1

    def setmode(self, mode): pass

    def setwarnings(self, val): pass

    def setup(self, pin, mode): pass

    def input(self, pin): return 1

    def output(self, pin, val): pass



class MockSerial:

    def __init__(self):

        self.in_buffer = bytearray()

        self.lock = threading.Lock()

        

    @property

    def in_waiting(self):

        with self.lock:

            return len(self.in_buffer)

            

    def write(self, data):

        threading.Thread(target=virtual_esp_processor, args=(data,), daemon=True).start()

        

    def read(self, size=1):

        with self.lock:

            res = self.in_buffer[:size]

            del self.in_buffer[:size]

            return bytes(res)

            

    def flush(self):

        pass



    def feed_rx(self, data):

        with self.lock:

            self.in_buffer.extend(data)



                     

GPIO = MockGPIO()



                                           

                                           

def virtual_esp_processor(frame):

    global SIMULATED_PACKET_LOSS

    if len(frame) < 58:

        return

        

    p_type = frame[1]

    payload_id = struct.unpack_from(">I", frame, 2)[0]

    

                                              

    if random.random() < SIMULATED_PACKET_LOSS:

        print(f"[SIMULATOR RX DROP] Dropped frame type {p_type:#x} for ID {payload_id}")

        return

        

                                            

    time.sleep(0.01)

    

    if p_type == 0x02:       

                               

        pong = bytearray(58)

        pong[0] = 0xAA

        pong[1] = 0x03       

        pong[2:6] = frame[2:6]          

        pong[6:14] = frame[6:14]                 

        

             

        crc = 0

        for b in pong[:57]: crc ^= b

        pong[57] = crc

        

                                    

        if random.random() < SIMULATED_PACKET_LOSS:

            print(f"[SIMULATOR TX DROP] Dropped PONG reply for ID {payload_id}")

            return

        time.sleep(0.015)

        hw.feed_mock_rx(bytes(pong))

        

    elif p_type == 0x01:            

        stage = frame[6]

        proposed_delay = frame[7]

        total_chunks = frame[8]

        data_type = frame[9]

        

        reply = bytearray(58)

        reply[0] = 0xAA

        reply[1] = 0x01            

        struct.pack_into(">I", reply, 2, payload_id)

        

        if stage == 1:      

            total_length = struct.unpack_from(">I", frame, 10)[0]

            virtual_rx_sessions[payload_id] = {

                "total_chunks": total_chunks,

                "total_length": total_length,

                "chunks": {},

                "type": data_type,

                "delay_ms": max(proposed_delay, 15),

                "best_effort": (frame[14] == 1)

            }

            reply[6] = 2          

            reply[7] = max(proposed_delay, 15)

            reply[8] = total_chunks

            reply[9] = data_type

            

        elif stage == 3:            

            return                                                 

            

        elif stage == 5:      

            session = virtual_rx_sessions.get(payload_id)

            status = 0          

            is_malformed = False

            if not session:

                status = 1          

            else:

                received = len(session["chunks"])

                if received < session["total_chunks"]:

                    status = 1          

                    is_malformed = True

                    print(f"[SIMULATOR VERIFY FAIL] Got {received}/{session['total_chunks']} chunks")

                else:

                    print(f"[SIMULATOR VERIFY SUCCESS] Payload {payload_id} fully received by virtual node")

                    

            reply[6] = 6          

            reply[7] = status

            

                                                                    

            if status == 1:

                bitmask = bytearray(49)

                if session:

                    for i in range(session["total_chunks"]):

                        if i not in session["chunks"]:

                            byte_idx = i // 8

                            bit_idx = i % 8

                            bitmask[byte_idx] |= (1 << bit_idx)

                else:

                    bitmask = bytearray([0xFF] * 49)

                reply[8:57] = bitmask

            

            best_effort = session.get("best_effort") if session else False

                                                                                                         

            if (status == 0 or (is_malformed and best_effort)) and session:

                ordered = [session["chunks"][i] for i in sorted(session["chunks"].keys())]

                full_b64_or_raw = b"".join(ordered)

                decoded_payload = wacknet_decompress(full_b64_or_raw)

                full_b64 = decoded_payload.decode('utf-8', errors='ignore')

                try:

                    raw_data = base64.b64decode(full_b64).decode('utf-8', errors='ignore')

                except:

                    raw_data = f"[Binary data: {len(full_b64)} chars]"

                if is_malformed:

                    raw_data = f"[MALFORMED/PARTIAL] {raw_data}"

                print(f"[SIMULATOR RECEIVER PROCESSOR] Reassembled message: {raw_data}")

                

                                 

        crc = 0

        for b in reply[:57]: crc ^= b

        reply[57] = crc

        

        if random.random() < SIMULATED_PACKET_LOSS:

            print(f"[SIMULATOR TX DROP] Dropped Handshake Stage {reply[6]} response for ID {payload_id}")

            return

        time.sleep(0.02)

        hw.feed_mock_rx(bytes(reply))

        

    elif p_type in (0x00, 0x04, 0x05, 0x06, 0x07, 0x08):       

        idx = frame[6]

        session = virtual_rx_sessions.get(payload_id)

        if session:

                                

            chunk_len = 49

            if idx == session["total_chunks"] - 1:

                chunk_len = session.get("total_length", 49 * session["total_chunks"]) - idx * 49

            chunk = frame[8:8+chunk_len]

            session["chunks"][idx] = bytes(chunk)



class WackNetHardwareBridge:

    def __init__(self, port='/dev/serial0'):

        global SIMULATION_MODE, GPIO

        self.lock = threading.RLock()

        self.mock_ser = None

        self.last_tx_time = 0

        

        if not SIMULATION_MODE:

            try:

                import RPi.GPIO as rgpio

                GPIO = rgpio

                GPIO.setmode(GPIO.BCM)

                GPIO.setwarnings(False)

                GPIO.setup(M0_PIN, GPIO.OUT)

                GPIO.setup(M1_PIN, GPIO.OUT)

                GPIO.setup(AUX_PIN, GPIO.IN)

                

                self.ser = serial.Serial(port=port, baudrate=9600, timeout=0.1)

                self.wait_aux()

                GPIO.output(M0_PIN, GPIO.LOW)

                GPIO.output(M1_PIN, GPIO.LOW)

                time.sleep(0.05)

                self.wait_aux()

            except Exception as e:

                print(f"Fallback to simulation: {e}")

                SIMULATION_MODE = True

                

        if SIMULATION_MODE:

            self.mock_ser = MockSerial()

            self.ser = self.mock_ser



    def wait_aux(self):

        if SIMULATION_MODE: return

        while GPIO.input(AUX_PIN) == GPIO.LOW:

            time.sleep(0.001)

        time.sleep(0.002)



    def write_raw_frame(self, frame):

        with self.lock:

            self.wait_aux()

            self.ser.write(bytes(frame))

            self.ser.flush()

            self.last_tx_time = time.time()

            if len(frame) >= 2 and frame[0] == 0xAA and frame[1] not in (0x02, 0x03):

                global last_other_activity_time

                last_other_activity_time = time.time()



    def feed_mock_rx(self, data):

        if self.mock_ser:

            self.mock_ser.feed_rx(data)



             

hw = WackNetHardwareBridge()



def add_telemetry(frame_hex, direction, p_type, payload_id, index, count):

    print(f"[TELEMETRY] {direction} {p_type} Stage={index} ID={payload_id}")

    with telemetry_lock:

        telemetry_log.append({

            "timestamp": int(time.time() * 1000),

            "hex": frame_hex,

            "direction": direction,

            "type": p_type,

            "payload_id": payload_id,

            "index": index,

            "count": count

        })

        if len(telemetry_log) > 50: telemetry_log.pop(0)



CURRENT_CHANNEL = 15

CURRENT_POWER = 0                                           



BACKUP_CONFIG = None

revert_timer = None



def revert_config():

    global CURRENT_AIR_RATE, CURRENT_CHANNEL, CURRENT_POWER, BACKUP_CONFIG, revert_timer

    if BACKUP_CONFIG:

        print(f"[REVERT] Reverting config to: {BACKUP_CONFIG}")

        configure_e32(rate=BACKUP_CONFIG["rate"], channel=BACKUP_CONFIG["channel"], power=BACKUP_CONFIG["power"], local_only=True)

        BACKUP_CONFIG = None



def initiate_config_change(rate=None, channel=None, power=None):

    global CURRENT_AIR_RATE, CURRENT_CHANNEL, CURRENT_POWER, BACKUP_CONFIG, revert_timer, tx_count

    

    t_rate = rate if rate is not None else CURRENT_AIR_RATE

    t_channel = channel if channel is not None else CURRENT_CHANNEL

    t_power = power if power is not None else CURRENT_POWER

    

    if t_rate == CURRENT_AIR_RATE and t_channel == CURRENT_CHANNEL and t_power == CURRENT_POWER:

        return True

        

    payload_id = random.randint(100000, 999999)

    

    rate_code = 0

    if t_rate == 2.4: rate_code = 1

    elif t_rate == 9.6: rate_code = 2

    elif t_rate == 19.2: rate_code = 3

    

                                                 

    prop_frame = bytearray(58)

    prop_frame[0] = 0xAA

    prop_frame[1] = 0x01

    struct.pack_into(">I", prop_frame, 2, payload_id)

    prop_frame[6] = 10           

    prop_frame[7] = rate_code

    prop_frame[8] = t_channel

    prop_frame[9] = t_power

    

    crc = 0

    for b in prop_frame[:57]: crc ^= b

    prop_frame[57] = crc

    

    with pending_lock:

        pending_responses[payload_id] = None

        

    agreed = False

    for retry in range(3):

        print(f"[CONFIG_NEG] Sending PROPOSE (Stage 10), retry {retry}...")

        hw.write_raw_frame(prop_frame)

        tx_count += 1

        add_telemetry(prop_frame.hex().upper(), "TX", "HANDSHAKE", payload_id, 10, 0)

        

        start_wait = time.time()

        while time.time() - start_wait < 4.0:

            with pending_lock:

                resp = pending_responses.get(payload_id)

                if resp and resp[1] == 0x01 and resp[6] == 11:

                    agreed = True

                    break

            time.sleep(0.01)

        if agreed:

            break

            

    if not agreed:

        print("[CONFIG_NEG] Remote did not agree. Aborting.")

        with pending_lock:

            if payload_id in pending_responses: del pending_responses[payload_id]

        return False

        

    print("[CONFIG_NEG] AGREE received! Sending CONFIRM (Stage 12) on current channel...")

    

                                                                                   

    confirm_frame = bytearray(58)

    confirm_frame[0] = 0xAA

    confirm_frame[1] = 0x01

    struct.pack_into(">I", confirm_frame, 2, payload_id)

    confirm_frame[6] = 12           

    confirm_frame[7] = rate_code

    confirm_frame[8] = t_channel

    confirm_frame[9] = t_power

    

    ccrc = 0

    for b in confirm_frame[:57]: ccrc ^= b

    confirm_frame[57] = ccrc

    

    for i in range(3):

        hw.write_raw_frame(confirm_frame)

        tx_count += 1

        add_telemetry(confirm_frame.hex().upper(), "TX", "HANDSHAKE", payload_id, 12, 0)

        if i < 2:

            time.sleep(0.15)

    

                                         

    print("[CONFIG_NEG] Waiting for CONFIRM to fully transmit, then switching...")

    BACKUP_CONFIG = {

        "rate": CURRENT_AIR_RATE,

        "channel": CURRENT_CHANNEL,

        "power": CURRENT_POWER

    }

    

    confirm_air_time = (3 * 58 * 8) / (CURRENT_AIR_RATE * 1000.0)

    switch_delay = max(1.0, confirm_air_time + 0.5)

    print(f"[CONFIG_NEG] Waiting {switch_delay:.2f}s for CONFIRM to fully transmit, then switching...")

    time.sleep(switch_delay)

    configure_e32(rate=t_rate, channel=t_channel, power=t_power, local_only=True)

    

                                      

    if revert_timer: revert_timer.cancel()

    revert_timer = threading.Timer(30.0, revert_config)

    revert_timer.start()

    

                                            

    print("[CONFIG_NEG] Switched! Sending VERIFY (Stage 13) on new channel...")

    with pending_lock:

        pending_responses[payload_id] = None

        

    verify_frame = bytearray(58)

    verify_frame[0] = 0xAA

    verify_frame[1] = 0x01

    struct.pack_into(">I", verify_frame, 2, payload_id)

    verify_frame[6] = 13          

    

    vcrc = 0

    for b in verify_frame[:57]: vcrc ^= b

    verify_frame[57] = vcrc

    

    verified = False

    for retry in range(4):

        print(f"[CONFIG_NEG] Sending VERIFY (Stage 13), retry {retry}...")

        time.sleep(0.2)

        hw.write_raw_frame(verify_frame)

        tx_count += 1

        add_telemetry(verify_frame.hex().upper(), "TX", "HANDSHAKE", payload_id, 13, 0)

        

        start_wait = time.time()

        while time.time() - start_wait < 3.0:

            with pending_lock:

                resp = pending_responses.get(payload_id)

                if resp and resp[1] == 0x01 and resp[6] == 14:

                    verified = True

                    break

            time.sleep(0.01)

        if verified:

            break

            

    with pending_lock:

        if payload_id in pending_responses: del pending_responses[payload_id]

    

    if verified:

        print("[CONFIG_NEG] VERIFY_ACK received! Config change successful.")

        if revert_timer:

            revert_timer.cancel()

            revert_timer = None

        BACKUP_CONFIG = None

        return True

    else:

        print("[CONFIG_NEG] VERIFY failed on new channel. Reverting...")

        if revert_timer:

            revert_timer.cancel()

            revert_timer = None

        revert_config()

        

        with pending_lock:

            if payload_id in pending_responses: del pending_responses[payload_id]

        return False

def read_e32_config():

    """Read current E32 module configuration. Returns dict or None."""

    global SIMULATION_MODE

    if SIMULATION_MODE:

        return {"rate": CURRENT_AIR_RATE, "channel": CURRENT_CHANNEL, "power": CURRENT_POWER}

    

    with hw.lock:

        try:

            orig_baud = hw.ser.baudrate

            hw.ser.baudrate = 9600

            time.sleep(0.01)

            

            elapsed = time.time() - hw.last_tx_time

            if elapsed < 0.8:

                time.sleep(0.8 - elapsed)

            hw.wait_aux()

            time.sleep(0.05)

            

            GPIO.output(M0_PIN, GPIO.HIGH)

            GPIO.output(M1_PIN, GPIO.HIGH)

            time.sleep(0.05)

            hw.wait_aux()

            

            hw.ser.read(hw.ser.in_waiting)

            hw.ser.write(bytes([0xC1, 0xC1, 0xC1]))

            hw.ser.flush()

            

            start = time.time()

            reply = bytearray()

            while time.time() - start < 0.3:

                if hw.ser.in_waiting > 0:

                    reply.extend(hw.ser.read(1))

                    if len(reply) == 6:

                        break

                time.sleep(0.005)

            

            GPIO.output(M0_PIN, GPIO.LOW)

            GPIO.output(M1_PIN, GPIO.LOW)

            time.sleep(0.05)

            hw.wait_aux()

            

            hw.ser.baudrate = orig_baud

            time.sleep(0.01)

            

            if len(reply) == 6:

                sped = reply[3]

                chan = reply[4] & 0x1F

                power = reply[5] & 0x03

                

                rate_map = {0x18: 0.3, 0x1A: 2.4, 0x2C: 9.6, 0x2D: 19.2}

                rate = rate_map.get(sped, 2.4)

                

                print(f"[CONFIG READ] SPED=0x{sped:02X} Rate={rate}k Chan={chan} Power={power}")

                return {"rate": rate, "channel": chan, "power": power}

            else:

                print(f"[CONFIG READ] Failed - got {len(reply)} bytes")

                return None

        except Exception as e:

            print(f"[CONFIG READ] Error: {e}")

            try:

                GPIO.output(M0_PIN, GPIO.LOW)

                GPIO.output(M1_PIN, GPIO.LOW)

            except:

                pass

            return None



def configure_e32(rate=None, channel=None, power=None, local_only=True):

    global CURRENT_AIR_RATE, CURRENT_CHANNEL, CURRENT_POWER, SIMULATED_TX_DELAY, SIMULATION_MODE

    if not local_only:

        return initiate_config_change(rate, channel, power)



    with hw.lock:

        if rate is not None:

            CURRENT_AIR_RATE = rate

            if CURRENT_AIR_RATE == 0.3:

                SIMULATED_TX_DELAY = 300

            elif CURRENT_AIR_RATE == 2.4:

                SIMULATED_TX_DELAY = 50

            elif CURRENT_AIR_RATE == 9.6:

                SIMULATED_TX_DELAY = 25

            elif CURRENT_AIR_RATE == 19.2:

                SIMULATED_TX_DELAY = 12

        if channel is not None:

            CURRENT_CHANNEL = channel

        if power is not None:

            CURRENT_POWER = power

            

        if SIMULATION_MODE:

            print(f"[SIMULATOR] Configured E32: Rate={CURRENT_AIR_RATE}kbps, Channel={CURRENT_CHANNEL}, Power={CURRENT_POWER}")

            update_lcd_ui(l2=f"R:{CURRENT_AIR_RATE}k C:{CURRENT_CHANNEL} D:{SIMULATED_TX_DELAY}")

            return True

            

        sped = 0x1A               

        if CURRENT_AIR_RATE == 0.3: sped = 0x18

        elif CURRENT_AIR_RATE == 2.4: sped = 0x1A

        elif CURRENT_AIR_RATE == 9.6: sped = 0x2C

        elif CURRENT_AIR_RATE == 19.2: sped = 0x2D

        

        chan_byte = CURRENT_CHANNEL & 0x1F

        option_byte = 0x44 | (CURRENT_POWER & 0x03)

        

        try:

            if not SIMULATION_MODE:

                try:

                                                                 

                    hw.ser.baudrate = 9600

                    time.sleep(0.01)

                    print(f"[DEBUG_AUX] Start. AUX={GPIO.input(AUX_PIN)}, last_tx_diff={time.time() - hw.last_tx_time:.3f}s")

                    elapsed = time.time() - hw.last_tx_time

                    if elapsed < 0.8:

                        time.sleep(0.8 - elapsed)

                    hw.wait_aux()

                    time.sleep(0.05)                      

                    print(f"[DEBUG_AUX] After wait_aux 1 & sleep. AUX={GPIO.input(AUX_PIN)}")

                except Exception as ex:

                    print(f"[DEBUG_AUX] wait_aux 1 exception: {ex}")

            GPIO.output(M0_PIN, GPIO.HIGH)

            GPIO.output(M1_PIN, GPIO.HIGH)

            time.sleep(0.05)

            if not SIMULATION_MODE:

                try:

                    hw.wait_aux()

                    print(f"[DEBUG_AUX] After wait_aux 2 (M0/M1 HIGH). AUX={GPIO.input(AUX_PIN)}")

                except:

                    pass

            

            cfg = bytes([0xC0, 0x00, 0x00, sped, chan_byte, option_byte])

            

            success = False

            reply = bytearray()

            for attempt in range(3):

                                     

                in_wat = hw.ser.in_waiting

                hw.ser.read(in_wat)

                print(f"[DEBUG_AUX] Cleared {in_wat} bytes from serial buffer. Attempt {attempt}: Writing config command...")

                hw.ser.write(cfg)

                hw.ser.flush()

                

                                

                start = time.time()

                reply = bytearray()

                while time.time() - start < 0.15:

                    if hw.ser.in_waiting > 0:

                        reply.extend(hw.ser.read(1))

                        if len(reply) == 6: break

                    time.sleep(0.005)

                    

                success = (len(reply) == 6 and reply[0] == 0xC0)

                if success:

                    print(f"[CONFIG] Attempt {attempt} succeeded.")

                    break

                else:

                    print(f"[CONFIG] Attempt {attempt} failed (reply: {reply.hex() if reply else 'None'})")

                    time.sleep(0.05)

                

                                                                                        

            if success and not SIMULATION_MODE:

                time.sleep(0.15)

                hw.ser.read(hw.ser.in_waiting)         

                hw.ser.write(bytes([0xC1, 0xC1, 0xC1]))

                hw.ser.flush()

                vstart = time.time()

                vreply = bytearray()

                while time.time() - vstart < 0.2:

                    if hw.ser.in_waiting > 0:

                        vreply.extend(hw.ser.read(1))

                        if len(vreply) == 6: break

                    time.sleep(0.005)

                if len(vreply) == 6:

                    v_chan = vreply[4] & 0x1F

                    v_sped = vreply[3]

                    print(f"[CONFIG VERIFY] Read-back: SPED=0x{v_sped:02X} CHAN={v_chan} OPT=0x{vreply[5]:02X}")

                    if v_chan != chan_byte or v_sped != sped:

                        print(f"[CONFIG VERIFY] WARNING: Mismatch! Expected SPED=0x{sped:02X}/CHAN={chan_byte}, got SPED=0x{v_sped:02X}/CHAN={v_chan}. Retrying save...")

                        hw.ser.read(hw.ser.in_waiting)

                        hw.ser.write(cfg)

                        hw.ser.flush()

                        time.sleep(0.15)

                else:

                    print(f"[CONFIG VERIFY] Could not read back config (got {len(vreply)} bytes)")



            GPIO.output(M0_PIN, GPIO.LOW)

            GPIO.output(M1_PIN, GPIO.LOW)

            time.sleep(0.05)

            if not SIMULATION_MODE:

                try:

                    hw.wait_aux()

                    print(f"[DEBUG_AUX] After wait_aux 3 (M0/M1 LOW). AUX={GPIO.input(AUX_PIN)}")

                except:

                    pass

            

                                                                     

            if not SIMULATION_MODE:

                if success:

                    target_baud = 38400 if CURRENT_AIR_RATE > 4.8 else 9600

                    hw.ser.baudrate = target_baud

                else:

                    prev_rate = BACKUP_CONFIG["rate"] if BACKUP_CONFIG else CURRENT_AIR_RATE

                    target_baud = 38400 if prev_rate > 4.8 else 9600

                    hw.ser.baudrate = target_baud

                time.sleep(0.01)

                

            if success:

                print(f"[CONFIG] Successfully configured E32 module (persistent): Rate={CURRENT_AIR_RATE}kbps, Channel={CURRENT_CHANNEL}, Power={CURRENT_POWER}.")

                update_lcd_ui(l2=f"R:{CURRENT_AIR_RATE}k C:{CURRENT_CHANNEL} D:{SIMULATED_TX_DELAY}")

            else:

                print(f"[CONFIG] Failed to configure E32 module (reply: {reply.hex() if reply else 'None'})")

                

            if not SIMULATION_MODE:

                try:

                    hw.ser.reset_input_buffer()

                except:

                    pass

                    

            return success

        except Exception as e:

            if not SIMULATION_MODE:

                try:

                    prev_rate = BACKUP_CONFIG["rate"] if BACKUP_CONFIG else CURRENT_AIR_RATE

                    target_baud = 38400 if prev_rate > 4.8 else 9600

                    hw.ser.baudrate = target_baud

                    hw.ser.reset_input_buffer()

                except:

                    pass

            try:

                GPIO.output(M0_PIN, GPIO.LOW)

                GPIO.output(M1_PIN, GPIO.LOW)

            except: pass

            return False



                  

def background_radio_rx_engine():

    global active_rx_sessions, rx_count, ui_state, BACKUP_CONFIG, revert_timer, msg_to_read, msg_prompt_start_time, msg_prompt_index, CURRENT_AIR_RATE, CURRENT_CHANNEL, CURRENT_POWER, active_tickets, current_command_ticket_id, command_eof_received

    rx_buffer = bytearray()

    while True:

        try:

            with hw.lock:

                if hw.ser.in_waiting > 0:

                    chunk = hw.ser.read(hw.ser.in_waiting)

                    if chunk:

                        rx_buffer.extend(chunk)

                        print(f"[DEBUG_RX] Read {len(chunk)} bytes: {chunk.hex().upper()}")

                    

            if len(rx_buffer) < 58:

                time.sleep(0.002)

                continue

                

            idx = rx_buffer.find(0xAA)

            if idx == -1:

                rx_buffer.clear()

                time.sleep(0.002)

                continue

                

            if idx > 0:

                del rx_buffer[:idx]

                

            if len(rx_buffer) < 58:

                time.sleep(0.002)

                continue

                

            frame = bytes(rx_buffer[:58])

            del rx_buffer[:58]

            if True:

                crc = 0

                for b in frame[:57]: crc ^= b

                

                if crc != frame[57]: continue

                

                rx_count += 1

                print_terminal_backup()

                

                p_type = frame[1]

                payload_id = struct.unpack_from(">I", frame, 2)[0]

                index = frame[6]

                count = frame[7]

                

                               

                t_name = "UNKNOWN"

                if p_type == 0x00: t_name = "TEXT"

                elif p_type == 0x01: t_name = "HANDSHAKE"

                elif p_type == 0x02: t_name = "PING"

                elif p_type == 0x03: t_name = "PONG"

                elif p_type == 0x04: t_name = "IMAGE"

                

                add_telemetry(frame.hex().upper(), "RX", t_name, payload_id, index, count)

                if p_type not in (0x02, 0x03):

                    global last_other_activity_time

                    last_other_activity_time = time.time()

                

                global last_heartbeat_time, EMG_TST_MODE, has_connected_to_base

                last_heartbeat_time = time.time()

                has_connected_to_base = True

                if ui_state == "EMG_TST_SEARCH" or EMG_TST_MODE:

                    EMG_TST_MODE = False

                    ui_state = "BASE_FOUND"

                

                if p_type == 0x02:                     

                    set_ping_pong_indicator(chr(0xFF))

                    pong = bytearray(58)

                    pong[0] = 0xAA

                    pong[1] = 0x03

                    pong[2:6] = frame[2:6]

                    pong[6:14] = frame[6:14]

                    pcrc = 0

                    for b in pong[:57]: pcrc ^= b

                    pong[57] = pcrc

                    hw.write_raw_frame(pong)

                    set_ping_pong_indicator(chr(0x00))

                    add_telemetry(pong.hex().upper(), "TX", "PONG", payload_id, 0, 0)

                    

                elif p_type == 0x03:       

                    with ping_lock:

                        if payload_id in pending_pings: pending_pings[payload_id] = frame

                        

                elif p_type == 0x01:            

                    stage = frame[6]

                    param = frame[7]

                    total_chunks = frame[8]

                    data_type = frame[9]

                    

                    with pending_lock:

                        if payload_id in pending_responses: pending_responses[payload_id] = frame

                        

                                              

                    if stage == 1:      

                        if ui_state == "MENU":

                            ui_state = "RECEIVING"

                            update_lcd(l1="* Receiving Msg *", l2="Waiting for data...", l3=f"Status: RX-SYN", l4=f"Payload ID: {payload_id}", from_ui=True)

                        else:

                            update_lcd(l3=f"Status: RX-SYN", l4=f"Payload ID: {payload_id}")

                        total_length = struct.unpack_from(">I", frame, 10)[0]

                        with rx_sessions_lock:

                            active_rx_sessions[payload_id] = {

                                "type": data_type,

                                "total_chunks": total_chunks,

                                "total_length": total_length,

                                "chunks": {},

                                "last_active": time.time()

                            }

                                       

                        reply = bytearray(58)

                        reply[0] = 0xAA; reply[1] = 0x01

                        reply[2:6] = frame[2:6]

                        reply[6] = 2

                        reply[7] = max(param, 15)

                        reply[8] = total_chunks

                        reply[9] = data_type

                        

                        rcrc = 0

                        for b in reply[:57]: rcrc ^= b

                        reply[57] = rcrc

                        hw.write_raw_frame(reply)

                        add_telemetry(reply.hex().upper(), "TX", "HANDSHAKE", payload_id, 2, total_chunks)

                        

                    elif stage == 3:            

                        update_lcd(l3=f"Status: RX-EST", l4=f"Chunks expected: {total_chunks}")

                        with rx_sessions_lock:

                            if payload_id in active_rx_sessions:

                                active_rx_sessions[payload_id]["last_active"] = time.time()

                                

                    elif stage == 5:      

                        update_lcd(l3=f"Status: RX-FIN", l4="Verifying...")

                        with rx_sessions_lock:

                            session = active_rx_sessions.get(payload_id)

                            status = 0

                            is_malformed = False

                            if not session:

                                status = 1

                            elif len(session["chunks"]) < session["total_chunks"]:

                                status = 1          

                                is_malformed = True

                                

                            reply = bytearray(58)

                            reply[0] = 0xAA; reply[1] = 0x01

                            reply[2:6] = frame[2:6]

                            reply[6] = 6

                            reply[7] = status

                            

                                                                  

                            if status == 1:

                                bitmask = bytearray(49)

                                if session:

                                    for i in range(session["total_chunks"]):

                                        if i not in session["chunks"]:

                                            byte_idx = i // 8

                                            bit_idx = i % 8

                                            bitmask[byte_idx] |= (1 << bit_idx)

                                else:

                                    bitmask = bytearray([0xFF] * 49)

                                reply[8:57] = bitmask

                                

                            rcrc = 0

                            for b in reply[:57]: rcrc ^= b

                            reply[57] = rcrc

                            hw.write_raw_frame(reply)

                            add_telemetry(reply.hex().upper(), "TX", "HANDSHAKE", payload_id, 6, status)

                            

                                                                                 

                            if status == 0 and session:

                                ordered = [session["chunks"][i] for i in sorted(session["chunks"].keys())]

                                full_b64_or_raw = b"".join(ordered)

                                decoded_payload = wacknet_decompress(full_b64_or_raw)

                                full_b64 = decoded_payload.decode('utf-8', errors='ignore')

                                try:

                                    decoded = base64.b64decode(full_b64).decode('utf-8', errors='ignore')

                                except:

                                    decoded = f"[Binary payload: {len(full_b64)} chars]"

                                    

                                import re

                                t_match = re.match(r"^\[(TKT-[A-Za-z0-9]+)\]\s*(.*)$", decoded, re.DOTALL)

                                if t_match:

                                    t_id = t_match.group(1)

                                    clean_decoded = t_match.group(2)

                                else:

                                    t_id = None

                                    clean_decoded = decoded

                                    

                                if session["type"] == 0x00:

                                    if t_id:

                                        if t_id in active_tickets:

                                            active_tickets[t_id]["return_message"] = clean_decoded

                                            del active_tickets[t_id]

                                        if current_command_ticket_id == t_id:

                                            current_command_ticket_id = None

                                            

                                    with msg_lock:

                                        incoming_messages.append({

                                            "timestamp": int(time.time() * 1000),

                                            "payload_id": payload_id,

                                            "type": session["type"],

                                            "data": f"[{t_id}] {clean_decoded}" if t_id else clean_decoded

                                        })

                                    msg_to_read = clean_decoded

                                    msg_prompt_index = 0

                                    msg_prompt_start_time = time.time()

                                    ui_state = "MSG_PROMPT"

                                elif session["type"] == 0x06:

                                    if t_id and t_id in active_tickets:

                                        active_tickets[t_id]["output"].append(clean_decoded)

                                        

                                    with cmd_output_lock:

                                        lines = clean_decoded.split('\n')

                                        for line in lines:

                                                                                                     

                                            line_clean = line.replace('\r', '')

                                                              

                                            if not line_clean:

                                                active_cmd_output.append("")

                                            else:

                                                for k in range(0, len(line_clean), 20):

                                                    active_cmd_output.append(line_clean[k:k+20])

                                        while len(active_cmd_output) > 200:

                                            active_cmd_output.pop(0)

                                elif session["type"] == 0x08:

                                    command_eof_received = True

                                    

                                if payload_id in active_rx_sessions:

                                    del active_rx_sessions[payload_id]

                                stop_progress_bar()



                    elif stage == 10:                 

                        rate_code = frame[7]

                        r_chan = frame[8]

                        r_pow = frame[9]

                        

                        r_rates = [0.3, 2.4, 9.6, 19.2]

                        r_rate = r_rates[rate_code] if rate_code < len(r_rates) else CURRENT_AIR_RATE

                        

                                                                     

                        pending_config_proposals[payload_id] = {

                            "rate": r_rate,

                            "channel": r_chan,

                            "power": r_pow,

                            "time": time.time()

                        }

                        

                                                                  

                        reply = bytearray(58)

                        reply[0] = 0xAA; reply[1] = 0x01

                        reply[2:6] = frame[2:6]

                        reply[6] = 11

                        reply[7] = rate_code

                        reply[8] = r_chan

                        reply[9] = r_pow

                        

                        crc = 0

                        for b in reply[:57]: crc ^= b

                        reply[57] = crc

                        

                        print(f"[CONFIG_NEG] PROPOSE received: Rate={r_rate}, Chan={r_chan}, Pow={r_pow}. Sending AGREE (no switch yet)...")

                        hw.write_raw_frame(reply)

                        add_telemetry(reply.hex().upper(), "TX", "HANDSHAKE", payload_id, 11, 0)

 

                    elif stage == 12:                 

                        proposal = pending_config_proposals.pop(payload_id, None)

                        if proposal:

                            print(f"[CONFIG_NEG] CONFIRM received! Switching to Rate={proposal['rate']}, Chan={proposal['channel']}, Pow={proposal['power']}...")

                            

                            BACKUP_CONFIG = {

                                "rate": CURRENT_AIR_RATE,

                                "channel": CURRENT_CHANNEL,

                                "power": CURRENT_POWER

                            }

                            

                            confirm_air_time = (2 * 58 * 8) / (CURRENT_AIR_RATE * 1000.0)

                            recv_switch_delay = max(0.5, confirm_air_time - 0.2)

                            print(f"[CONFIG_NEG] Sleeping {recv_switch_delay:.2f}s before local configuration switch...")

                            time.sleep(recv_switch_delay)

                            configure_e32(rate=proposal["rate"], channel=proposal["channel"], power=proposal["power"], local_only=True)

                            

                            if revert_timer: revert_timer.cancel()

                            revert_timer = threading.Timer(30.0, revert_config)

                            revert_timer.start()

                        else:

                            print(f"[CONFIG_NEG] Duplicate CONFIRM for {payload_id}, ignoring.")

 

                    elif stage == 13:                                 

                        reply = bytearray(58)

                        reply[0] = 0xAA; reply[1] = 0x01

                        reply[2:6] = frame[2:6]

                        reply[6] = 14              

                        

                        crc = 0

                        for b in reply[:57]: crc ^= b

                        reply[57] = crc

                        

                        print("[CONFIG_NEG] VERIFY received on new channel, sending VERIFY_ACK. Config confirmed!")

                        hw.write_raw_frame(reply)

                        add_telemetry(reply.hex().upper(), "TX", "HANDSHAKE", payload_id, 14, 0)

                        

                        if revert_timer:

                            revert_timer.cancel()

                            revert_timer = None

                        BACKUP_CONFIG = None

                                                                                                    

                        last_heartbeat_time = time.time()

                        EMG_TST_MODE = False

 

                    elif stage == 14:                              

                        if revert_timer:

                            revert_timer.cancel()

                            revert_timer = None

                        BACKUP_CONFIG = None

 

                elif p_type in (0x00, 0x04, 0x05, 0x06, 0x07, 0x08):       

                    with rx_sessions_lock:

                        session = active_rx_sessions.get(payload_id)

                        if session:

                            chunk_len = 49

                            if index == session["total_chunks"] - 1:

                                chunk_len = session.get("total_length", 49 * session["total_chunks"]) - index * 49

                            data_bytes = frame[8:8+chunk_len]

                            session["chunks"][index] = bytes(data_bytes)

                            session["last_active"] = time.time()

                            update_lcd(l3=f"RX DATA {len(session['chunks'])}/{session['total_chunks']}")

                            set_progress_bar(len(session['chunks']) / session['total_chunks'], line=4)

                            

        except Exception as e:

            import traceback

            traceback.print_exc()

        time.sleep(0.002)

 

              

def rx_cleaner():

    global active_rx_sessions, msg_to_read, msg_prompt_index, msg_prompt_start_time, ui_state, command_eof_received, current_command_ticket_id

    while True:

        try:

            now = time.time()

            to_del = []

            with rx_sessions_lock:

                timeout_dur = max(15.0, get_block_guard_delay() * 2.0)

                for pid, sess in active_rx_sessions.items():

                    if now - sess["last_active"] > timeout_dur: to_del.append((pid, sess))

                for pid, sess in to_del:

                    print(f"Cleaning up timed-out RX session {pid}")

                    received = len(sess["chunks"])

                    total = sess["total_chunks"]

                    if BEST_EFFORT_RX and received > 0:

                        is_malformed = received < total

                        ordered = [sess["chunks"][i] for i in sorted(sess["chunks"].keys())]

                        full_b64_or_raw = b"".join(ordered)

                        decoded_payload = wacknet_decompress(full_b64_or_raw)

                        full_b64 = decoded_payload.decode('utf-8', errors='ignore')

                        try:

                            decoded = base64.b64decode(full_b64).decode('utf-8', errors='ignore')

                        except:

                            decoded = f"[Binary payload: {len(full_b64)} chars]"

                            

                        import re

                        t_match = re.match(r"^\[(TKT-[A-Za-z0-9]+)\]\s*(.*)$", decoded, re.DOTALL)

                        if t_match:

                            t_id = t_match.group(1)

                            clean_decoded = t_match.group(2)

                        else:

                            t_id = None

                            clean_decoded = decoded

                            

                        if is_malformed:

                            clean_decoded = f"[MALFORMED/PARTIAL] {clean_decoded}"

 

                        if sess["type"] == 0x00:

                            if t_id:

                                if t_id in active_tickets:

                                    active_tickets[t_id]["return_message"] = clean_decoded

                                    del active_tickets[t_id]

                                if current_command_ticket_id == t_id:

                                    current_command_ticket_id = None

                                    

                            with msg_lock:

                                incoming_messages.append({

                                    "timestamp": int(time.time() * 1000),

                                    "payload_id": pid,

                                    "type": sess["type"],

                                    "data": f"[{t_id}] {clean_decoded}" if t_id else clean_decoded

                                })

                            msg_to_read = clean_decoded

                            msg_prompt_index = 0

                            msg_prompt_start_time = time.time()

                            ui_state = "MSG_PROMPT"

                        elif sess["type"] == 0x06:

                            if t_id and t_id in active_tickets:

                                active_tickets[t_id]["output"].append(clean_decoded)

                                

                            with cmd_output_lock:

                                lines = clean_decoded.split('\n')

                                for line in lines:

                                    line_clean = line.replace('\r', '')

                                    if not line_clean:

                                        active_cmd_output.append("")

                                    else:

                                        for k in range(0, len(line_clean), 20):

                                            active_cmd_output.append(line_clean[k:k+20])

                                while len(active_cmd_output) > 200:

                                    active_cmd_output.pop(0)

                        elif sess["type"] == 0x08:

                            command_eof_received = True

                            

                    del active_rx_sessions[pid]

                    stop_progress_bar()

        except Exception as e:

            print(f"Exception in rx_cleaner: {e}")

                                         

        try:

            stale = [pid for pid, p in list(pending_config_proposals.items()) if time.time() - p.get("time", 0) > 30]

            for pid in stale:

                pending_config_proposals.pop(pid, None)

        except:

            pass

        time.sleep(5)



                     

COMPRESSION_DICT = (

    b"needIPneedSTATUSneedNETneedCONneedBSneedNMAPneedX"

    b"AvailableoptionsGetlocalIPsystemstatusListvisibleWiFinetworks"

    b"ConnecttoWiFiGetrandomBSListactivesubnetsListcommands"

    b"Completed.Output:WackNetStatusUptimeCPUTempLoadChRateTxDelEMG"

    b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+/="

)



def wacknet_compress(payload_bytes):

    try:

        import zlib

        compressor = zlib.compressobj(level=9, method=zlib.DEFLATED, wbits=-15, zdict=COMPRESSION_DICT)

        compressed = compressor.compress(payload_bytes) + compressor.flush()

        if len(compressed) + 1 < len(payload_bytes):

            return b"\x01" + compressed

    except Exception as e:

        print(f"[COMPRESS] Error: {e}")

    return b"\x00" + payload_bytes



def wacknet_decompress(compressed_payload):

    if not compressed_payload:

        return b""

    header = compressed_payload[0]

    data = compressed_payload[1:]

    if header == 0x01:

        try:

            import zlib

            decompressor = zlib.decompressobj(wbits=-15, zdict=COMPRESSION_DICT)

            return decompressor.decompress(data)

        except Exception as e:

            print(f"[DECOMPRESS] Error: {e}")

            return data

    return data



                  

def get_block_guard_delay():

    rate = CURRENT_AIR_RATE

    if rate == 19.2:

        return 0.220

    elif rate == 9.6:

        return 0.445

    elif rate == 2.4:

        return 1.780

    elif rate == 0.3:

        return 14.220

    else:

        rate_bps = rate * 1000.0

        return (3712.0 / rate_bps) * 1.15



                  

def start_handshake_session(p_type, payload_bytes, delay_ms):

    global tx_count

    payload_id = random.randint(100000, 999999)

    compressed_payload = wacknet_compress(payload_bytes)

    chunks = [compressed_payload[i:i+49] for i in range(0, len(compressed_payload), 49)]

    total = len(chunks)

    

    outbound_lock.acquire()

    try:

        return _start_handshake_session_locked(p_type, compressed_payload, delay_ms, payload_id, chunks, total)

    finally:

        stop_spinner()

        stop_progress_bar()

        outbound_lock.release()



def _start_handshake_session_locked(p_type, payload_bytes, delay_ms, payload_id, chunks, total):

    global tx_count

    update_lcd(l3="Status: SYN", l4=f"ID: {payload_id}")

    start_spinner(line=4, col=19)

    

                          

    syn = bytearray(58)

    syn[0] = 0xAA; syn[1] = 0x01

    struct.pack_into(">I", syn, 2, payload_id)

    syn[6] = 1      

    syn[7] = min(delay_ms, 255)

    syn[8] = total

    syn[9] = p_type

    struct.pack_into(">I", syn, 10, len(payload_bytes))

    syn[14] = 1 if BEST_EFFORT_RX else 0

    

    crc = 0

    for b in syn[:57]: crc ^= b

    syn[57] = crc



    with pending_lock: pending_responses[payload_id] = None

    agreed_delay = delay_ms

    syn_ack_ok = False

    

    for retry in range(3):

        update_lcd(l3=f"Status: SYN (R:{retry})")

        hw.write_raw_frame(syn)

        tx_count += 1

        add_telemetry(syn.hex().upper(), "TX", "HANDSHAKE", payload_id, 1, total)

        

        start_wait = time.time()

        while time.time() - start_wait < 3.0:

            with pending_lock:

                frame = pending_responses.get(payload_id)

                if frame and frame[1] == 0x01 and frame[6] == 2:

                    agreed_delay = frame[7]

                    syn_ack_ok = True

                    break

            time.sleep(0.01)

        if syn_ack_ok: break

        

    if not syn_ack_ok:

        stop_spinner()

        stop_progress_bar()

        update_lcd(l3="Status: SYN-FAIL", l4="SYN-ACK Timeout")

        with pending_lock:

            if payload_id in pending_responses: del pending_responses[payload_id]

        return False



    update_lcd(l3="Status: SYN-ACK", l4="Parameters ok")

    time.sleep(0.05)



                                

    est = bytearray(58)

    est[0] = 0xAA; est[1] = 0x01

    struct.pack_into(">I", est, 2, payload_id)

    est[6] = 3

    est[7] = min(agreed_delay, 255)

    est[8] = total

    

    crc = 0

    for b in est[:57]: crc ^= b

    est[57] = crc

    

    hw.write_raw_frame(est)

    tx_count += 1

    add_telemetry(est.hex().upper(), "TX", "HANDSHAKE", payload_id, 3, total)

    update_lcd(l3="Status: ESTABLISHED")

    stop_spinner()

    set_progress_bar(0.0, line=4)

    time.sleep(agreed_delay / 1000.0)



                                                                            

    chunks_to_send = list(range(total))

    nak_round = 0

    max_nak_rounds = 5

    block_guard_delay = get_block_guard_delay()

    

    verif = 1

    received_fin_ack = None

    

    while nak_round <= max_nak_rounds:

        update_lcd(l3=f"TX DATA R{nak_round} {total - len(chunks_to_send)}/{total}")

        

                                              

        for i in range(0, len(chunks_to_send), 8):

            block = chunks_to_send[i:i+8]

            for idx in block:

                chunk = chunks[idx]

                frame = bytearray(58)

                frame[0] = 0xAA; frame[1] = p_type

                struct.pack_into(">I", frame, 2, payload_id)

                frame[6] = idx

                frame[7] = total

                frame[8:8+len(chunk)] = chunk

                

                crc = 0

                for b in frame[:57]: crc ^= b

                frame[57] = crc

                

                hw.write_raw_frame(frame)

                tx_count += 1

                p_name = "TEXT" if p_type == 0x00 else "IMAGE"

                add_telemetry(frame.hex().upper(), "TX", p_name, payload_id, idx, total)

                

                                                

                chunks_sent_so_far = (total - len(chunks_to_send)) + (i + block.index(idx) + 1)

                update_lcd(l3=f"TX DATA R{nak_round} {chunks_sent_so_far}/{total}")

                set_progress_bar(chunks_sent_so_far / total, line=4)

            

                                                                               

            block_air_time = (len(block) * 58 * 8) / (CURRENT_AIR_RATE * 1000.0)

            time.sleep(block_air_time * 1.15)



                              

        fin = bytearray(58)

        fin[0] = 0xAA; fin[1] = 0x01

        struct.pack_into(">I", fin, 2, payload_id)

        fin[6] = 5

        crc = 0

        for b in fin[:57]: crc ^= b

        fin[57] = crc



        with pending_lock: pending_responses[payload_id] = None

        fin_ack_ok = False

        verif = 1

        received_fin_ack = None

        

        for retry in range(3):

            update_lcd(l3=f"Status: FIN R{nak_round} (R:{retry})")

            hw.write_raw_frame(fin)

            tx_count += 1

            add_telemetry(fin.hex().upper(), "TX", "HANDSHAKE", payload_id, 5, 0)

            

            start_wait = time.time()

            while time.time() - start_wait < 3.0:

                with pending_lock:

                    frame = pending_responses.get(payload_id)

                    if frame and frame[1] == 0x01 and frame[6] == 6:

                        verif = frame[7]

                        received_fin_ack = bytes(frame)

                        fin_ack_ok = True

                        break

                time.sleep(0.01)

            if fin_ack_ok: break



        if not fin_ack_ok:

            update_lcd(l3="Status: FIN-FAIL", l4=f"Timeout round {nak_round}")

            with pending_lock:

                if payload_id in pending_responses: del pending_responses[payload_id]

            return False

            

        if verif == 0:

            update_lcd(l3="Status: SUCCESS", l4="Transfer completed!")

            with pending_lock:

                if payload_id in pending_responses: del pending_responses[payload_id]

            return True

            

        elif verif == 1:

            missing_chunks = []

            bitmask = received_fin_ack[8:57]

            for idx in range(total):

                byte_idx = idx // 8

                bit_idx = idx % 8

                if byte_idx < len(bitmask) and (bitmask[byte_idx] & (1 << bit_idx)):

                    missing_chunks.append(idx)

                    

            if not missing_chunks:

                if BEST_EFFORT_RX:

                    update_lcd(l3="Status: PARTIAL", l4="Missing packets!")

                    with pending_lock:

                        if payload_id in pending_responses: del pending_responses[payload_id]

                    return True

                else:

                    update_lcd(l3="Status: SUCCESS", l4="Transfer completed!")

                    with pending_lock:

                        if payload_id in pending_responses: del pending_responses[payload_id]

                    return True

                    

            print(f"[NAK ROUND {nak_round}] Missing chunks: {missing_chunks}")

            chunks_to_send = missing_chunks

            nak_round += 1

            

        else:

            update_lcd(l3="Status: TX-FAIL", l4=f"Verification error {verif}")

            with pending_lock:

                if payload_id in pending_responses: del pending_responses[payload_id]

            return False



    with pending_lock:

        if payload_id in pending_responses: del pending_responses[payload_id]



    if verif == 1 and BEST_EFFORT_RX:

        update_lcd(l3="Status: PARTIAL", l4="Missing packets!")

        return True

    else:

        update_lcd(l3="Status: TX-FAIL", l4="Verification error")

        return False



                 

def run_ping_test():

    global tx_count

    ping_id = random.randint(100000, 999999)

    sent = int(time.time() * 1000)

    

    ping = bytearray(58)

    ping[0] = 0xAA; ping[1] = 0x02

    struct.pack_into(">I", ping, 2, ping_id)

    struct.pack_into(">Q", ping, 6, sent)

    

    crc = 0

    for b in ping[:57]: crc ^= b

    ping[57] = crc



    with ping_lock: pending_pings[ping_id] = None

    

    update_lcd(l3="Status: PINGING...", l4="Await loopback pong")

    hw.write_raw_frame(ping)

    tx_count += 1

    add_telemetry(ping.hex().upper(), "TX", "PING", ping_id, 0, 0)

    

    start = time.time()

    timeout = 4.0 if CURRENT_AIR_RATE > 0.3 else 5.0

    while time.time() - start < timeout:

        with ping_lock:

            frame = pending_pings.get(ping_id)

            if frame:

                rtt = int(time.time() * 1000) - sent

                del pending_pings[ping_id]

                update_lcd(l3="Status: PONG OK", l4=f"RTT: {rtt} ms")

                return {"status": "success", "rtt": rtt}

        time.sleep(0.01)

        

    with ping_lock:

        if ping_id in pending_pings: del pending_pings[ping_id]

    update_lcd(l3="Status: PING TIMEOUT", l4="Base station offline")

    return {"status": "timeout"}



                        

def main_menu_loop():

    import select

    import termios

    import tty



    global CURRENT_AIR_RATE, CURRENT_CHANNEL, CURRENT_POWER, SIMULATED_TX_DELAY, tx_count, rx_count, ui_state, typed_command, command_eof_received, typed_cmd_input, BEST_EFFORT_RX, _pending_transition

    

    MENU_ITEMS = [

        "Send Message",

        "Message Inbox",

        "Command Mode",

        "Set Air Rate",

        "Set Channel",

        "Set Tx Power",

        "WiFi Settings",

        "Run Ping Test",

        "Telemetry Logs",

        "[x] Best Effort Rx" if BEST_EFFORT_RX else "[ ] Best Effort Rx",

        "Radio Config",

        "Shutdown"

    ]

    

    def update_menu_items():

        MENU_ITEMS[9] = "[x] Best Effort Rx" if BEST_EFFORT_RX else "[ ] Best Effort Rx"

    

    ui_state = "EMG_TST_SEARCH"

    typed_msg = ""

    log_scroll_index = 0

    log_scroll_offset = 0

    inbox_scroll_index = 0

    inbox_scroll_offset = 0

    send_success = False

    ping_res = None

    config_success = True

    

    wifi_list = []

    wifi_index = 0

    wifi_offset = 0

    wifi_password = ""

    selected_ssid = ""

    wifi_connect_result = {}

    last_rem = -1

    last_ui_state = "MENU"

    key_queue = []

    

    menu_index = 0

    menu_offset = 0

    

    send_opt_index = 0

    send_opt_offset = 0

    

    rate_index = 0

    rate_offset = 0



    power_index = 0

    power_offset = 0

    temp_channel = 26

    

    selected_index = 0

    detail_offset = 0

    

                                  

    fd = sys.stdin.fileno()

    is_tty = True

    try:

        old_settings = termios.tcgetattr(fd)

        tty.setraw(fd)

                                                                              

        attrs = termios.tcgetattr(fd)

        attrs[1] |= termios.OPOST

        termios.tcsetattr(fd, termios.TCSANOW, attrs)

    except termios.error:

        is_tty = False

        

    def refresh_lcd():

        global ui_state

        nonlocal typed_msg, log_scroll_index, log_scroll_offset, inbox_scroll_index, inbox_scroll_offset

        nonlocal send_success, ping_res, menu_index, menu_offset, send_opt_index, send_opt_offset, rate_index, rate_offset

        nonlocal power_index, power_offset, temp_channel

        nonlocal selected_index, detail_offset

        nonlocal wifi_list, wifi_index, wifi_offset, wifi_password, selected_ssid, wifi_connect_result, last_rem, config_success

        

        if ui_state in ("RADIO_CONFIG",):

            start_wave_animation()

        else:

            stop_wave_animation()

            

        if ui_state == "MENU":

            if menu_index < menu_offset:

                menu_offset = menu_index

            elif menu_index >= menu_offset + 3:

                menu_offset = menu_index - 2

                

            lines = []

            for i in range(3):

                idx = menu_offset + i

                if idx < len(MENU_ITEMS):

                    prefix = "> " if idx == menu_index else "  "

                    lines.append(f"{prefix}{idx+1}. {MENU_ITEMS[idx]}")

                else:

                    lines.append("")

                                       

            has_unread = False

            with msg_lock:

                has_unread = len(incoming_messages) > 0

            title = "\x04 WackNet Menu \x04" if not has_unread else "\x04 WackNet  \x04 \x06"

            title = title.ljust(19, " ") + _ping_pong_indicator

            update_lcd_ui(

                l1=title,

                l2=lines[0],

                l3=lines[1],

                l4=lines[2]

            )

        elif ui_state == "SEND_OPTION":

            SEND_OPTS = [

                "Write Custom Msg",

                "Canned: Ping Req",

                "Canned: Status OK",

                "Canned: Help Needed",

                "Canned: Ack Receipt",

                "< Back to Menu"

            ]

            if send_opt_index < send_opt_offset:

                send_opt_offset = send_opt_index

            elif send_opt_index >= send_opt_offset + 3:

                send_opt_offset = send_opt_index - 2

                

            lines = []

            for i in range(3):

                idx = send_opt_offset + i

                if idx < len(SEND_OPTS):

                    prefix = "> " if idx == send_opt_index else "  "

                    lines.append(f"{prefix}{idx+1}. {SEND_OPTS[idx]}")

                else:

                    lines.append("")

            update_lcd_ui(

                l1="* Send Message *",

                l2=lines[0],

                l3=lines[1],

                l4=lines[2]

            )

        elif ui_state == "SEND_MSG":

            disp_msg = typed_msg

            if len(disp_msg) > 18:

                disp_msg = ".." + disp_msg[-16:]

            update_lcd_ui(

                l1="Send Msg: (Enter)",

                l2=f"> {disp_msg}",

                l3="",

                l4="Backsp:Del Enter:Snd"

            )

        elif ui_state == "SENDING":

            stop_wave_animation()

            start_spinner(line=3, col=19)

            update_lcd_ui(

                l1="* Transmitting *",

                l2="Initiating link...",

                l3="Please wait",

                l4=""

            )

        elif ui_state == "SEND_RESULT":

            stop_spinner()

            stop_progress_bar()

            lcd.load_char_page("menu")

            icon = "\x04" if send_success else "\x05"                  

            status_str = f"{icon} SUCCESS!" if send_success else f"{icon} FAILED"

            update_lcd_ui(

                l1="Send Result:",

                l2=status_str,

                l3="Press Enter",

                l4="to return..."

            )

        elif ui_state == "PINGING":

            stop_wave_animation()

            start_spinner(line=2, col=19)

            update_lcd_ui(

                l1="Ping Diagnostics",

                l2="Sending ping...",

                l3="Timeout: 4.0s",

                l4=""

            )

        elif ui_state == "PING_RESULT":

            stop_spinner()

            lcd.load_char_page("menu")

            if ping_res and ping_res["status"] == "success":

                rtt_str = f"RTT: {ping_res['rtt']} ms"

                status_str = "\x04 PONG RECEIVED"

            else:

                rtt_str = "TIMEOUT"

                status_str = "\x05 BASE OFFLINE"

            update_lcd_ui(

                l1="Ping Diagnostics",

                l2=status_str,

                l3=rtt_str,

                l4="Press Enter"

            )

        elif ui_state == "RATE_MENU":

            RATE_OPTS = [

                "0.3 kbps (ESGTST)",

                "2.4 kbps (default)",

                "9.6 kbps",

                "19.2 kbps",

                "< Back to Menu"

            ]

            if rate_index < rate_offset:

                rate_offset = rate_index

            elif rate_index >= rate_offset + 3:

                rate_offset = rate_index - 2

                

            lines = []

            for i in range(3):

                idx = rate_offset + i

                if idx < len(RATE_OPTS):

                    prefix = "> " if idx == rate_index else "  "

                    lines.append(f"{prefix}{idx+1}. {RATE_OPTS[idx]}")

                else:

                    lines.append("")

            update_lcd_ui(

                l1=f"* Set Rate ({CURRENT_AIR_RATE}k) *",

                l2=lines[0],

                l3=lines[1],

                l4=lines[2]

            )

        elif ui_state == "CHAN_MENU":

            freq = 410 + temp_channel

            update_lcd_ui(

                l1="* Set Channel *",

                l2=f"Channel: {temp_channel:2d}",

                l3=f"Freq: {freq} MHz",

                l4="Up/Dn:Chg Ent:Save"

            )

        elif ui_state == "POWER_MENU":

            POWER_OPTS = [

                "Max Power",

                "Med-High Power",

                "Med-Low Power",

                "Min Power",

                "< Back to Menu"

            ]

            if power_index < power_offset:

                power_offset = power_index

            elif power_index >= power_offset + 3:

                power_offset = power_index - 2

                

            lines = []

            for i in range(3):

                idx = power_offset + i

                if idx < len(POWER_OPTS):

                    prefix = "> " if idx == power_index else "  "

                    lines.append(f"{prefix}{idx+1}. {POWER_OPTS[idx]}")

                else:

                    lines.append("")

            

            power_names = ["Max", "Med-High", "Med-Low", "Min"]

            curr_p_name = power_names[CURRENT_POWER] if CURRENT_POWER < len(power_names) else str(CURRENT_POWER)

            update_lcd_ui(

                l1=f"* Power ({curr_p_name}) *",

                l2=lines[0],

                l3=lines[1],

                l4=lines[2]

            )

        elif ui_state == "CONFIG_TOGGLED":

            stop_spinner()

            lcd.load_char_page("menu")

            if config_success:

                power_names = ["Max", "Med-High", "Med-Low", "Min"]

                p_str = power_names[CURRENT_POWER] if CURRENT_POWER < len(power_names) else str(CURRENT_POWER)

                update_lcd_ui(

                    l1="* Config Saved *",

                    l2=f"R:{CURRENT_AIR_RATE}k  C:{CURRENT_CHANNEL}",

                    l3=f"P:{p_str}",

                    l4="Press Enter..."

                )

            else:

                update_lcd_ui(

                    l1="* Config Failed *",

                    l2="Negotiation timeout",

                    l3="Reverted to old",

                    l4="Press Enter..."

                )

        elif ui_state == "VIEW_LOGS":

            with telemetry_lock:

                logs = list(telemetry_log)

            if not logs:

                update_lcd_ui(

                    l1="Telemetry Logs:",

                    l2="No logs recorded.",

                    l3="",

                    l4="Press Enter"

                )

            else:

                rev_logs = list(reversed(logs))

                if log_scroll_index < log_scroll_offset:

                    log_scroll_offset = log_scroll_index

                elif log_scroll_index >= log_scroll_offset + 3:

                    log_scroll_offset = log_scroll_index - 2

                

                lines = []

                for i in range(3):

                    idx = log_scroll_offset + i

                    if idx < len(rev_logs):

                        log = rev_logs[idx]

                        t = time.strftime('%H:%M:%S', time.localtime(log['timestamp']/1000.0))

                        prefix = "> " if idx == log_scroll_index else "  "

                        lines.append(f"{prefix}{t} {log['direction']} {log['type'][:4]}")

                    else:

                        lines.append("")

                update_lcd_ui(

                    l1=f"Logs ({log_scroll_index+1}/{len(rev_logs)}) Ent:Det",

                    l2=lines[0],

                    l3=lines[1],

                    l4=lines[2]

                )

        elif ui_state == "LOG_DETAIL":

            with telemetry_lock:

                logs = list(telemetry_log)

            rev_logs = list(reversed(logs))

            if selected_index < len(rev_logs):

                log = rev_logs[selected_index]

                pid = log.get('payload_id', 0)

                direction = log.get('direction', '??')

                p_type = log.get('type', '???')

                idx = log.get('index', 0)

                count = log.get('count', 0)

                h = log.get('hex', '')

                visible_hex = h[detail_offset:detail_offset+18]

                update_lcd_ui(

                    l1="* Log Detail (Esc) *",

                    l2=f"ID:{pid} Dir:{direction}",

                    l3=f"T:{p_type} I:{idx}/{count}",

                    l4=f"H:{visible_hex}"

                )

            else:

                ui_state = "VIEW_LOGS"

                refresh_lcd()

        elif ui_state == "VIEW_INBOX":

            with msg_lock:

                msgs = list(incoming_messages)

            if not msgs:

                update_lcd_ui(

                    l1="Inbox Messages:",

                    l2="No messages.",

                    l3="",

                    l4="Press Enter"

                )

            else:

                rev_msgs = list(reversed(msgs))

                if inbox_scroll_index < inbox_scroll_offset:

                    inbox_scroll_offset = inbox_scroll_index

                elif inbox_scroll_index >= inbox_scroll_offset + 3:

                    inbox_scroll_offset = inbox_scroll_index - 2

                

                lines = []

                for i in range(3):

                    idx = inbox_scroll_offset + i

                    if idx < len(rev_msgs):

                        m = rev_msgs[idx]

                        t = time.strftime('%H:%M:%S', time.localtime(m['timestamp']/1000.0))

                        prefix = "> " if idx == inbox_scroll_index else "  "

                        lines.append(f"{prefix}{t}: {m['data'][:10]}")

                    else:

                        lines.append("")

                update_lcd_ui(

                    l1=f"Inbox ({inbox_scroll_index+1}/{len(rev_msgs)}) Ent:Det",

                    l2=lines[0],

                    l3=lines[1],

                    l4=lines[2]

                )

        elif ui_state == "INBOX_DETAIL":

            with msg_lock:

                msgs = list(incoming_messages)

            rev_msgs = list(reversed(msgs))

            if selected_index < len(rev_msgs):

                m = rev_msgs[selected_index]

                t_str = time.strftime('%H:%M:%S', time.localtime(m['timestamp']/1000.0))

                pid = m.get('payload_id', 0)

                data = m.get('data', '')

                p_type = m.get('type', 0x00)

                type_str = "TEXT" if p_type == 0x00 else "IMG"

                visible_data = data[detail_offset:detail_offset+20]

                update_lcd_ui(

                    l1="* Msg Detail (Esc) *",

                    l2=f"Time: {t_str}",

                    l3=f"ID:{pid} T:{type_str}",

                    l4=visible_data

                )

            else:

                ui_state = "VIEW_INBOX"

                refresh_lcd()

        elif ui_state in ("RECEIVING", "RECEIVE_RESULT"):

            stop_wave_animation()

            update_lcd_ui(

                l1=current_lcd_status["line1"],

                l2=current_lcd_status["line2"],

                l3=current_lcd_status["line3"],

                l4=current_lcd_status["line4"]

            )

        elif ui_state == "MSG_PROMPT":

            elapsed = time.time() - msg_prompt_start_time

            rem = max(0, int(8.0 - elapsed))

            r_prefix = "> " if msg_prompt_index == 0 else "  "

            e_prefix = "> " if msg_prompt_index == 1 else "  "

            update_lcd_ui(

                l1="* New Message *",

                l2=f"{r_prefix}Read",

                l3=f"{e_prefix}Exit",

                l4=f"Timeout: {rem}s"

            )

        elif ui_state == "MSG_READ":

            disp_line1 = msg_to_read[detail_offset:detail_offset+20]

            disp_line1 = disp_line1.ljust(20, " ")

            exit_prefix = "> " if msg_prompt_index == 1 else "  "

            update_lcd_ui(

                l1=disp_line1,

                l2="  [L/R to Scroll]",

                l3=f"{exit_prefix}Exit",

                l4="L/R:Scroll Dn:Exit" if msg_prompt_index == 0 else "Enter:Exit Up:Scroll"

            )

        elif ui_state == "WIFI_SCANNING":

            stop_wave_animation()

            start_spinner(line=3, col=19)

            update_lcd_ui(

                l1="* WiFi Settings *",

                l2="Scanning...",

                l3="Please wait",

                l4=""

            )

        elif ui_state == "WIFI_LIST":

            stop_spinner()

            options = [f"{n['ssid']} [{n['signal']}%]" for n in wifi_list] + ["< Back to Menu"]

            if wifi_index < wifi_offset:

                wifi_offset = wifi_index

            elif wifi_index >= wifi_offset + 3:

                wifi_offset = wifi_index - 2

                

            lines = []

            for i in range(3):

                idx = wifi_offset + i

                if idx < len(options):

                    prefix = "> " if idx == wifi_index else "  "

                    lines.append(f"{prefix}{options[idx]}")

                else:

                    lines.append("")

            update_lcd_ui(

                l1="* Select Network *",

                l2=lines[0],

                l3=lines[1],

                l4=lines[2]

            )

        elif ui_state == "WIFI_PASSWORD":

            disp_pwd = wifi_password

            if len(disp_pwd) > 18:

                disp_pwd = ".." + disp_pwd[-16:]

            update_lcd_ui(

                l1="Enter Password:",

                l2=f"> {disp_pwd}",

                l3="",

                l4="enter to send it"

            )

        elif ui_state == "WIFI_CONNECTING":

            start_spinner(line=3, col=19)

            update_lcd_ui(

                l1="Connecting to:",

                l2=selected_ssid[:20],

                l3="Please wait...",

                l4=""

            )

        elif ui_state == "WIFI_CONNECT_RESULT":

            stop_spinner()

            status_str = "SUCCESS!" if wifi_connect_result.get("status") == "success" else "FAILED"

            msg_str = wifi_connect_result.get("message", "")[:20]

            update_lcd_ui(

                l1="WiFi Connection:",

                l2=status_str,

                l3=msg_str,

                l4="Press Enter..."

            )

        elif ui_state == "EMG_TST_SEARCH":

            update_lcd_ui(

                l1="waiting for connect",

                l2="searching right now",

                l3="300bps",

                l4="ESC to see menu"

            )

        elif ui_state == "BASE_FOUND":

            r_prefix = "> " if option_index == 0 else "  "

            s_prefix = "> " if option_index == 1 else "  "

            update_lcd_ui(

                l1="base found",

                l2=f"{r_prefix}Go to Rate Menu",

                l3=f"{s_prefix}Stay at 0.3kbps",

                l4="Select option..."

            )

        elif ui_state == "COMMAND_INPUT":

            disp_cmd = typed_command

            if len(disp_cmd) > 18:

                disp_cmd = ".." + disp_cmd[-16:]

            update_lcd_ui(

                l1="Command: (Enter)",

                l2=f"> {disp_cmd}",

                l3="",

                l4="enter to send it"

            )

        elif ui_state == "COMMAND_RUNNING":

            with cmd_output_lock:

                lines = list(active_cmd_output)

            global command_eof_received

            if command_eof_received:

                ui_state = "COMMAND_FINISHED"

                                                       

                update_lcd_ui(

                    l1="it was sent",

                    l2="YouMaySeeOutput",

                    l3="Press Enter",

                    l4="to return..."

                )

            else:

                l2_disp = lines[-2] if len(lines) >= 2 else ""

                l3_disp = lines[-1] if len(lines) >= 1 else ""

                update_lcd_ui(

                    l1="* Cmd Running *",

                    l2=l2_disp[:20],

                    l3=l3_disp[:20],

                    l4="Ent:Input Esc:Abort"

                )

        elif ui_state == "COMMAND_INPUT_PROMPT":

            disp_in = typed_cmd_input

            if len(disp_in) > 18:

                disp_in = ".." + disp_in[-16:]

            update_lcd_ui(

                l1="input: (Ent)",

                l2=f"> {disp_in}",

                l3="",

                l4="enter to send"

            )

        elif ui_state == "RADIO_CONFIG":

            stop_spinner()

            update_lcd_ui(

                l1="\x06 Radio Config \x06",

                l2="Polling E32...",

                l3="Please wait",

                l4=""

            )

        elif ui_state == "COMMAND_FINISHED":

            stop_spinner()

            update_lcd_ui(

                l1="comand done",

                l2="we sent it ",

                l3="Press Enter",

                l4="to return..."

            )



    global refresh_lcd_global

    refresh_lcd_global = refresh_lcd



    try:

        refresh_lcd()

        

        while True:

                                                

            if ui_state != last_ui_state:

                old_ui = last_ui_state

                last_ui_state = ui_state

                if ui_state == "MSG_PROMPT":

                    msg_prompt_start_time = time.time()

                    msg_prompt_index = 0

                                                         

                _pending_transition = _get_transition_style(old_ui, ui_state)

                refresh_lcd()

                

                                         

            if ui_state == "MSG_PROMPT":

                elapsed = time.time() - msg_prompt_start_time

                if elapsed > 8.0:

                    ui_state = "MENU"

                    continue

                rem = int(8.0 - elapsed)

                if rem != last_rem:

                    last_rem = rem

                    refresh_lcd()

            

                                 

            if not key_queue:

                if not is_tty:

                    time.sleep(0.05)

                else:

                    rlist, _, _ = select.select([fd], [], [], 0.05)

                    if rlist:

                        time.sleep(0.02)

                        try:

                            b = os.read(fd, 100)

                        except Exception:

                            b = b''

                        if len(b) > 0:

                            parsed = parse_keys(b)

                            key_queue.extend(parsed)

                            

            global cmd_output_dirty, command_eof_received

            if ui_state == "COMMAND_RUNNING" and (cmd_output_dirty or command_eof_received):

                cmd_output_dirty = False

                refresh_lcd()

                

            if not key_queue:

                time.sleep(0.01)

                continue

                

            key = key_queue.pop(0)

                

            if ui_state == "MENU":

                if key == 'UP' or key.upper() == 'W':

                    menu_index = max(0, menu_index - 1)

                    refresh_lcd()

                elif key == 'DOWN' or key.upper() == 'S':

                    menu_index = min(len(MENU_ITEMS) - 1, menu_index + 1)

                    refresh_lcd()

                elif key == '\n' or key == '\r':

                    if menu_index == 0:

                        ui_state = "SEND_OPTION"

                        send_opt_index = 0

                        send_opt_offset = 0

                        refresh_lcd()

                    elif menu_index == 1:

                        ui_state = "VIEW_INBOX"

                        inbox_scroll_index = 0

                        inbox_scroll_offset = 0

                        refresh_lcd()

                    elif menu_index == 2:

                        ui_state = "COMMAND_INPUT"

                        typed_command = ""

                        refresh_lcd()

                    elif menu_index == 3:

                        ui_state = "RATE_MENU"

                        rate_index = 0

                        rate_offset = 0

                        refresh_lcd()

                    elif menu_index == 4:

                        ui_state = "CHAN_MENU"

                        temp_channel = CURRENT_CHANNEL

                        refresh_lcd()

                    elif menu_index == 5:

                        ui_state = "POWER_MENU"

                        power_index = CURRENT_POWER

                        power_offset = 0

                        refresh_lcd()

                    elif menu_index == 6:

                        ui_state = "WIFI_SCANNING"

                        refresh_lcd()

                        def run_scan():

                            global ui_state

                            nonlocal wifi_list, wifi_index, wifi_offset

                            wifi_list = scan_wifi()

                            wifi_index = 0

                            wifi_offset = 0

                            ui_state = "WIFI_LIST"

                        threading.Thread(target=run_scan, daemon=True).start()

                    elif menu_index == 7:

                        ui_state = "PINGING"

                        refresh_lcd()

                        ping_res = run_ping_test()

                        ui_state = "PING_RESULT"

                        refresh_lcd()

                    elif menu_index == 8:

                        ui_state = "VIEW_LOGS"

                        log_scroll_index = 0

                        log_scroll_offset = 0

                        refresh_lcd()

                    elif menu_index == 9:

                        BEST_EFFORT_RX = not BEST_EFFORT_RX

                        update_menu_items()

                        refresh_lcd()

                    elif menu_index == 10:

                        ui_state = "RADIO_CONFIG"

                        refresh_lcd()

                        def poll_radio_thread():

                            global ui_state

                            cfg = read_e32_config()

                            if cfg:

                                update_lcd_ui(

                                    l1=" Radio Config ",

                                    l2=f"Rate: {cfg['rate']} kbps",

                                    l3=f"Chan: {cfg['channel']} Pwr: {cfg['power']}",

                                    l4="Enter to return"

                                )

                            else:

                                update_lcd_ui(

                                    l1="X Xadio Xonfig X",

                                    l2="Yo shit fucked up",

                                    l3="base not respond",

                                    l4="Enter to return"

                                )

                        threading.Thread(target=poll_radio_thread, daemon=True).start()

                    elif menu_index == 11:

                        print("\nShutting down handheld console interface.")

                        break

                elif key == '\x1b':

                    print("\nShutting down handheld console interface.")

                    break

                    

            elif ui_state == "SEND_OPTION":

                SEND_OPTS_LEN = 6

                if key == 'UP' or key.upper() == 'W':

                    send_opt_index = max(0, send_opt_index - 1)

                    refresh_lcd()

                elif key == 'DOWN' or key.upper() == 'S':

                    send_opt_index = min(SEND_OPTS_LEN - 1, send_opt_index + 1)

                    refresh_lcd()

                elif key == '\n' or key == '\r':

                    if send_opt_index == 0:

                        ui_state = "SEND_MSG"

                        typed_msg = ""

                        refresh_lcd()

                    elif send_opt_index == 5:

                        ui_state = "MENU"

                        refresh_lcd()

                    else:

                        canned_msgs = {

                            1: "Ping Request",

                            2: "Status OK",

                            3: "Help Needed",

                            4: "Ack Receipt"

                        }

                        msg_text = canned_msgs.get(send_opt_index, "Hello")

                        ui_state = "SENDING"

                        refresh_lcd()

                        send_success = start_handshake_session(0x00, base64.b64encode(msg_text.encode('utf-8')), SIMULATED_TX_DELAY)

                        ui_state = "SEND_RESULT"

                        refresh_lcd()

                elif key == '\x1b':

                    ui_state = "MENU"

                    refresh_lcd()

                    

            elif ui_state == "SEND_MSG":

                if key == '\n' or key == '\r':

                    if typed_msg:

                        ui_state = "SENDING"

                        refresh_lcd()

                        send_success = start_handshake_session(0x00, base64.b64encode(typed_msg.encode('utf-8')), SIMULATED_TX_DELAY)

                        ui_state = "SEND_RESULT"

                        refresh_lcd()

                    else:

                        ui_state = "SEND_OPTION"

                        refresh_lcd()

                elif key in ('\x7f', '\x08', '\b'):

                    typed_msg = typed_msg[:-1]

                    refresh_lcd()

                elif key == '\x1b':

                    ui_state = "SEND_OPTION"

                    refresh_lcd()

                elif len(key) == 1 and key.isprintable():

                    typed_msg += key

                    refresh_lcd()

                    

            elif ui_state in ("SEND_RESULT", "PING_RESULT", "CONFIG_TOGGLED", "RECEIVING", "RECEIVE_RESULT"):

                if key == '\n' or key == '\r' or key == '\x1b':

                    ui_state = "MENU"

                    refresh_lcd()

                    

            elif ui_state == "RATE_MENU":

                RATE_OPTS_LEN = 5

                if key == 'UP' or key.upper() == 'W':

                    rate_index = max(0, rate_index - 1)

                    refresh_lcd()

                elif key == 'DOWN' or key.upper() == 'S':

                    rate_index = min(RATE_OPTS_LEN - 1, rate_index + 1)

                    refresh_lcd()

                elif key == '\n' or key == '\r':

                    if rate_index == 4:

                        ui_state = "MENU"

                        refresh_lcd()

                    else:

                        rates = [0.3, 2.4, 9.6, 19.2]

                        next_rate = rates[rate_index]

                        ui_state = "RADIO_CONFIG"

                        refresh_lcd()

                        config_success = configure_e32(rate=next_rate, local_only=False)

                        ui_state = "CONFIG_TOGGLED"

                        refresh_lcd()

                elif key == '\x1b':

                    ui_state = "MENU"

                    refresh_lcd()

 

            elif ui_state == "CHAN_MENU":

                if key == 'UP' or key.upper() == 'W':

                    temp_channel = min(31, temp_channel + 1)

                    refresh_lcd()

                elif key == 'DOWN' or key.upper() == 'S':

                    temp_channel = max(0, temp_channel - 1)

                    refresh_lcd()

                elif key == '\n' or key == '\r':

                    ui_state = "RADIO_CONFIG"

                    refresh_lcd()

                    config_success = configure_e32(channel=temp_channel, local_only=False)

                    ui_state = "CONFIG_TOGGLED"

                    refresh_lcd()

                elif key == '\x1b':

                    ui_state = "MENU"

                    refresh_lcd()

 

            elif ui_state == "POWER_MENU":

                POWER_OPTS_LEN = 5

                if key == 'UP' or key.upper() == 'W':

                    power_index = max(0, power_index - 1)

                    refresh_lcd()

                elif key == 'DOWN' or key.upper() == 'S':

                    power_index = min(POWER_OPTS_LEN - 1, power_index + 1)

                    refresh_lcd()

                elif key == '\n' or key == '\r':

                    if power_index == 4:

                        ui_state = "MENU"

                        refresh_lcd()

                    else:

                        ui_state = "RADIO_CONFIG"

                        refresh_lcd()

                        config_success = configure_e32(power=power_index, local_only=False)

                        ui_state = "CONFIG_TOGGLED"

                        refresh_lcd()

                elif key == '\x1b':

                    ui_state = "MENU"

                    refresh_lcd()

                    

            elif ui_state == "VIEW_LOGS":

                with telemetry_lock:

                    logs_len = len(telemetry_log)

                if logs_len == 0:

                    if key is not None:

                        ui_state = "MENU"

                        refresh_lcd()

                else:

                    if key == 'UP' or key.upper() == 'W':

                        log_scroll_index = max(0, log_scroll_index - 1)

                        refresh_lcd()

                    elif key == 'DOWN' or key.upper() == 'S':

                        log_scroll_index = min(logs_len - 1, log_scroll_index + 1)

                        refresh_lcd()

                    elif key == '\n' or key == '\r':

                        selected_index = log_scroll_index

                        detail_offset = 0

                        ui_state = "LOG_DETAIL"

                        refresh_lcd()

                    elif key == '\x1b' or key in ('\x7f', '\x08', '\b'):

                        ui_state = "MENU"

                        refresh_lcd()

                        

            elif ui_state == "LOG_DETAIL":

                with telemetry_lock:

                    logs = list(telemetry_log)

                rev_logs = list(reversed(logs))

                hex_len = 0

                if selected_index < len(rev_logs):

                    hex_len = len(rev_logs[selected_index].get('hex', ''))

                    

                if key == 'LEFT' or key.upper() == 'A':

                    detail_offset = max(0, detail_offset - 1)

                    refresh_lcd()

                elif key == 'RIGHT' or key.upper() == 'D':

                    detail_offset = min(max(0, hex_len - 18), detail_offset + 1)

                    refresh_lcd()

                elif key == '\n' or key == '\r' or key == '\x1b' or key in ('\x7f', '\x08', '\b'):

                    ui_state = "VIEW_LOGS"

                    refresh_lcd()

                    

            elif ui_state == "VIEW_INBOX":

                with msg_lock:

                    msgs_len = len(incoming_messages)

                if msgs_len == 0:

                    if key is not None:

                        ui_state = "MENU"

                        refresh_lcd()

                else:

                    if key == 'UP' or key.upper() == 'W':

                        inbox_scroll_index = max(0, inbox_scroll_index - 1)

                        refresh_lcd()

                    elif key == 'DOWN' or key.upper() == 'S':

                        inbox_scroll_index = min(msgs_len - 1, inbox_scroll_index + 1)

                        refresh_lcd()

                    elif key == '\n' or key == '\r':

                        selected_index = inbox_scroll_index

                        detail_offset = 0

                        ui_state = "INBOX_DETAIL"

                        refresh_lcd()

                    elif key == '\x1b' or key in ('\x7f', '\x08', '\b'):

                        ui_state = "MENU"

                        refresh_lcd()

                        

            elif ui_state == "INBOX_DETAIL":

                with msg_lock:

                    msgs = list(incoming_messages)

                rev_msgs = list(reversed(msgs))

                data_len = 0

                if selected_index < len(rev_msgs):

                    data_len = len(rev_msgs[selected_index].get('data', ''))

                    

                if key == 'LEFT' or key.upper() == 'A':

                    detail_offset = max(0, detail_offset - 1)

                    refresh_lcd()

                elif key == 'RIGHT' or key.upper() == 'D':

                    detail_offset = min(max(0, data_len - 20), detail_offset + 1)

                    refresh_lcd()

                elif key == '\n' or key == '\r' or key == '\x1b' or key in ('\x7f', '\x08', '\b'):

                    ui_state = "VIEW_INBOX"

                    refresh_lcd()

                    

            elif ui_state == "MSG_PROMPT":

                if key == 'UP' or key == 'DOWN' or key.upper() in ('W', 'S'):

                    msg_prompt_index = 1 - msg_prompt_index

                    refresh_lcd()

                elif key == '\n' or key == '\r':

                    if msg_prompt_index == 0:

                        ui_state = "MSG_READ"

                        detail_offset = 0

                        msg_prompt_index = 0

                        refresh_lcd()

                    else:

                        ui_state = "MENU"

                        refresh_lcd()

                elif key == '\x1b' or key in ('\x7f', '\x08', '\b'):

                    ui_state = "MENU"

                    refresh_lcd()

                    

            elif ui_state == "MSG_READ":

                if msg_prompt_index == 0:

                    if key == 'LEFT' or key.upper() == 'A':

                        detail_offset = max(0, detail_offset - 1)

                        refresh_lcd()

                    elif key == 'RIGHT' or key.upper() == 'D':

                        detail_offset = min(max(0, len(msg_to_read) - 20), detail_offset + 1)

                        refresh_lcd()

                    elif key == 'DOWN' or key.upper() == 'S':

                        msg_prompt_index = 1

                        refresh_lcd()

                    elif key == '\x1b' or key in ('\x7f', '\x08', '\b'):

                        ui_state = "MENU"

                        refresh_lcd()

                else:

                    if key == 'UP' or key.upper() == 'W':

                        msg_prompt_index = 0

                        refresh_lcd()

                    elif key == '\n' or key == '\r':

                        ui_state = "MENU"

                        refresh_lcd()

                    elif key == '\x1b' or key in ('\x7f', '\x08', '\b'):

                        ui_state = "MENU"

                        refresh_lcd()

                        

            elif ui_state == "WIFI_LIST":

                options_len = len(wifi_list) + 1

                if key == 'UP' or key.upper() == 'W':

                    wifi_index = max(0, wifi_index - 1)

                    refresh_lcd()

                elif key == 'DOWN' or key.upper() == 'S':

                    wifi_index = min(options_len - 1, wifi_index + 1)

                    refresh_lcd()

                elif key == '\n' or key == '\r':

                    if wifi_index == options_len - 1:

                        ui_state = "MENU"

                        refresh_lcd()

                    else:

                        selected_ssid = wifi_list[wifi_index]["ssid"]

                        ui_state = "WIFI_PASSWORD"

                        wifi_password = ""

                        refresh_lcd()

                elif key == '\x1b' or key in ('\x7f', '\x08', '\b'):

                    ui_state = "MENU"

                    refresh_lcd()

                    

            elif ui_state == "WIFI_PASSWORD":

                if key == '\n' or key == '\r':

                    ui_state = "WIFI_CONNECTING"

                    refresh_lcd()

                    def run_connect():

                        global ui_state

                        nonlocal wifi_connect_result

                        wifi_connect_result = connect_wifi(selected_ssid, wifi_password)

                        ui_state = "WIFI_CONNECT_RESULT"

                    threading.Thread(target=run_connect, daemon=True).start()

                elif key in ('\x7f', '\x08', '\b'):

                    wifi_password = wifi_password[:-1]

                    refresh_lcd()

                elif key == '\x1b':

                    ui_state = "WIFI_LIST"

                    refresh_lcd()

                elif len(key) == 1 and key.isprintable():

                    wifi_password += key

                    refresh_lcd()

                    

            elif ui_state == "EMG_TST_SEARCH":

                if key == '\x1b':

                    ui_state = "MENU"

                    refresh_lcd()

            elif ui_state == "BASE_FOUND":

                global option_index

                if key == 'UP' or key == 'DOWN' or key.upper() in ('W', 'S'):

                    option_index = 1 - option_index

                    refresh_lcd()

                elif key == '\n' or key == '\r':

                    if option_index == 0:

                        ui_state = "RATE_MENU"

                        rate_index = 0

                        rate_offset = 0

                    else:

                        ui_state = "MENU"

                    refresh_lcd()

                elif key == '\x1b':

                    ui_state = "MENU"

                    refresh_lcd()

            elif ui_state == "COMMAND_INPUT":

                if key == '\n' or key == '\r':

                    if typed_command:

                        ui_state = "SENDING"

                        refresh_lcd()

                        def send_cmd_thread():

                            global ui_state, command_eof_received, current_command_ticket_id, active_tickets

                            import random

                            t_id = f"TKT-{random.randint(1000, 9999)}"

                            current_command_ticket_id = t_id

                            active_tickets[t_id] = {"output": [], "command": typed_command, "timestamp": time.time()}

                            

                            prefixed_cmd = f"[{t_id}] {typed_command}"

                            success = start_handshake_session(0x05, base64.b64encode(prefixed_cmd.encode('utf-8')), SIMULATED_TX_DELAY)

                            if success:

                                with cmd_output_lock:

                                    active_cmd_output.clear()

                                command_eof_received = False

                                ui_state = "COMMAND_RUNNING"

                            else:

                                ui_state = "COMMAND_FINISHED"

                                current_command_ticket_id = None

                            refresh_lcd()

                        threading.Thread(target=send_cmd_thread, daemon=True).start()

                    else:

                        ui_state = "MENU"

                        refresh_lcd()

                elif key in ('\x7f', '\x08', '\b'):

                    typed_command = typed_command[:-1]

                    refresh_lcd()

                elif key == '\x1b':

                    ui_state = "MENU"

                    refresh_lcd()

                elif len(key) == 1 and key.isprintable():

                    typed_command += key

                    refresh_lcd()

            elif ui_state == "COMMAND_RUNNING":

                if key == '\n' or key == '\r':

                    ui_state = "COMMAND_INPUT_PROMPT"

                    typed_cmd_input = ""

                    refresh_lcd()

                elif key == '\x1b':

                    global current_command_ticket_id

                    current_command_ticket_id = None

                    cancel_frame = bytearray(58)

                    cancel_frame[0] = 0xAA

                    cancel_frame[1] = 0x09

                    crc = 0

                    for b in cancel_frame[:57]: crc ^= b

                    cancel_frame[57] = crc

                    hw.write_raw_frame(cancel_frame)

                    ui_state = "MENU"

                    refresh_lcd()

            elif ui_state == "COMMAND_INPUT_PROMPT":

                if key == '\n' or key == '\r':

                    ui_state = "SENDING"

                    refresh_lcd()

                    def send_input_thread():

                        global ui_state, current_command_ticket_id

                        payload_str = typed_cmd_input

                        if current_command_ticket_id:

                            payload_str = f"[{current_command_ticket_id}] {typed_cmd_input}"

                        success = start_handshake_session(0x07, base64.b64encode(payload_str.encode('utf-8')), SIMULATED_TX_DELAY)

                        ui_state = "COMMAND_RUNNING"

                        refresh_lcd()

                    threading.Thread(target=send_input_thread, daemon=True).start()

                elif key in ('\x7f', '\x08', '\b'):

                    typed_cmd_input = typed_cmd_input[:-1]

                    refresh_lcd()

                elif key == '\x1b':

                    ui_state = "COMMAND_RUNNING"

                    refresh_lcd()

                elif len(key) == 1 and key.isprintable():

                    typed_cmd_input += key

                    refresh_lcd()

            elif ui_state == "RADIO_CONFIG":

                if key == '\n' or key == '\r' or key == '\x1b':

                    ui_state = "MENU"

                    refresh_lcd()

            elif ui_state == "COMMAND_FINISHED":

                if key is not None:

                    ui_state = "MENU"

                    refresh_lcd()

                    

            elif ui_state == "WIFI_CONNECT_RESULT":

                if key is not None:

                    ui_state = "MENU"

                    refresh_lcd()

    finally:

        if is_tty:

            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)



def handheld_heartbeat_monitor_loop():

    global last_heartbeat_time, last_other_activity_time, EMG_TST_MODE, ui_state, CURRENT_CHANNEL, has_connected_to_base, active_handshake_state, active_rx_sessions

    print("[HEARTBEAT] Monitor thread active.")

    while True:

        time.sleep(1.0)

                                       

        other_active = False

        if ui_state in ("COMMAND_RUNNING", "COMMAND_INPUT_PROMPT"):

            other_active = True

        elif active_handshake_state is not None and active_handshake_state.get("status") not in ("success", "failed"):

            other_active = True

        elif len(active_rx_sessions) > 0:

            other_active = True

        elif time.time() - last_other_activity_time < 20.0:

            other_active = True

            

        if other_active:

            last_heartbeat_time = time.time()

            continue

            

        if has_connected_to_base and not EMG_TST_MODE and (time.time() - last_heartbeat_time > 30.0):

            print("[HEARTBEAT] Missed heartbeats. Entering EMG TST failsafe...")

            EMG_TST_MODE = True

            ui_state = "EMG_TST_SEARCH"

            configure_e32(rate=0.3, channel=CURRENT_CHANNEL, power=0, local_only=True)

            update_lcd(l1="* Link Offline *", l2="EMG TST Searching...", l3="Rate: 0.3k", l4="Await heartbeat...", from_ui=True)



def poll_radio_config_startup():

    global CURRENT_AIR_RATE, CURRENT_CHANNEL, CURRENT_POWER

    print("[STARTUP] Polling radio module configuration...")

    

                           

    lcd.load_char_page("menu")

    lcd_transition("none", " " * 20, " " * 20, " " * 20, " " * 20)

    boot_text = "  W A C K N E T  "

    for i in range(len(boot_text) + 1):

        partial = boot_text[:i].rjust(20)

        with lcd_lock:

            lcd.write_line_raw(2, partial)

        time.sleep(0.04)

    time.sleep(0.3)

    lcd_transition("flash",

        "\x06 WackNet v2.0 \x06",

        "LoRa Transceiver",

        "Reading E32 config..",

        "Please wait..."

    )

    start_spinner(line=4, col=19)

    

    cfg = read_e32_config()

    stop_spinner()

    if cfg:

        print(f"[STARTUP] Radio reports: Rate={cfg['rate']}k Chan={cfg['channel']} Power={cfg['power']}")

        lcd_transition("flash",

            "* Radio OK *",

            f"R:{cfg['rate']}k C:{cfg['channel']}",

            f"Power: {cfg['power']}",

            "Configuring..."

        )

        time.sleep(1.0)

    else:

        print("[STARTUP] WARNING: Could not read radio config!")

        lcd_transition("flash",

            "* Radio Error *",

            "No E32 response!",

            "Check connection.",

            "Continuing..."

        )

        time.sleep(2.0)



if __name__ == "__main__":

                             

    poll_radio_config_startup()

    

                                                              

    configure_e32(0.3, 15, 0)

    

                   

    threading.Thread(target=background_radio_rx_engine, daemon=True).start()

    threading.Thread(target=rx_cleaner, daemon=True).start()

    threading.Thread(target=handheld_heartbeat_monitor_loop, daemon=True).start()

    

                                                                 

    def send_initial_ping():

        time.sleep(2.0)                                                        

        print("[INIT] Sending initial ping to base station...")

        for _ in range(3):

            ping_id = random.randint(100000, 999999)

            sent = int(time.time() * 1000)

            ping = bytearray(58)

            ping[0] = 0xAA; ping[1] = 0x02

            struct.pack_into(">I", ping, 2, ping_id)

            struct.pack_into(">Q", ping, 6, sent)

            crc = 0

            for b in ping[:57]: crc ^= b

            ping[57] = crc

            hw.write_raw_frame(ping)

            time.sleep(0.5)

            

    threading.Thread(target=send_initial_ping, daemon=True).start()

    

    try:

        main_menu_loop()

    except KeyboardInterrupt:

        print("\nExiting handheld transceiver.")

