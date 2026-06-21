                      

import os

import sys

import time

import struct

import threading

import random

import json

import base64

from http.server import SimpleHTTPRequestHandler, HTTPServer

from datetime import datetime

from zoneinfo import ZoneInfo

import re



M0_PIN = 17

M1_PIN = 27

AUX_PIN = 22



SIMULATION_MODE = False

SIMULATED_PACKET_LOSS = 0.0                          

SIMULATED_TX_DELAY = 50                                      



                                       

telemetry_log = []

telemetry_lock = threading.Lock()



                               

incoming_messages = []

msg_lock = threading.Lock()



                           

active_handshake_state = None

state_lock = threading.Lock()



outbound_lock = threading.Lock()

EMG_TST_MODE = True

consecutive_missed_heartbeats = 0

startup_scan_active = False

heartbeat_active = False

active_command_proc = None

active_tickets = {}

last_other_activity_time = 0.0

last_wifi_scan_results = []



                                                   

pending_responses = {}

pending_lock = threading.Lock()



pending_pings = {}

ping_lock = threading.Lock()



pending_config_proposals = {}



                                                                     

active_rx_sessions = {}

rx_sessions_lock = threading.Lock()



                       

virtual_rx_sessions = {}



def add_telemetry(frame_hex, direction, p_type, payload_id, index, count, crc_ok):

    print(f"[TELEMETRY] {direction} {p_type} Stage={index} ID={payload_id} CRC={crc_ok}")

    with telemetry_lock:

        telemetry_log.append({

            "timestamp": int(time.time() * 1000),

            "hex": frame_hex,

            "direction": direction,

            "type": p_type,

            "payload_id": payload_id,

            "index": index,

            "count": count,

            "crc_ok": crc_ok

        })

        if len(telemetry_log) > 50:

            telemetry_log.pop(0)



def get_local_ip():

    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:

        s.connect(('8.8.8.8', 1))

        IP = s.getsockname()[0]

    except Exception:

        IP = '127.0.0.1'

    finally:

        s.close()

    return IP



class BatteryFuelGauge:

    def __init__(self, shm_path="/dev/shm/wacknet_battery.json", disk_path="/home/user/trans/execute/wacknet_battery.json"):

        self.shm_path = shm_path

        self.disk_path = disk_path

                                                                  

                                                                    

                                                  

                                                   

        self.total_capacity_mas = 2407.8 * 3600.0

        self.remaining_mas = self.total_capacity_mas

        self.heavy_tx_mode = False

        self.last_update_time = time.time()

        self.last_disk_save_time = time.time()

        self.lock = threading.RLock()

        

        self.load_state()

        

                                        

        self.running = True

        self.thread = threading.Thread(target=self._update_loop, daemon=True)

        self.thread.start()



    def load_state(self):

        with self.lock:

                                                 

            for path in (self.shm_path, self.disk_path):

                try:

                    if os.path.exists(path):

                        with open(path, "r") as f:

                            data = json.load(f)

                            self.remaining_mas = float(data.get("remaining_mas", self.total_capacity_mas))

                                                           

                            self.remaining_mas = max(0.0, min(self.remaining_mas, self.total_capacity_mas))

                            print(f"[BATTERY] Loaded state from {path}: {self.get_percentage():.2f}% ({self.remaining_mas:.2f} mAs)")

                            return

                except Exception as e:

                    print(f"[BATTERY] Error loading state from {path}: {e}")

            

                                                         

            self.remaining_mas = self.total_capacity_mas

            print(f"[BATTERY] Initialized to 100.00% capacity ({self.remaining_mas:.2f} mAs)")



    def save_state(self, to_disk=False):

        with self.lock:

            data = {"remaining_mas": self.remaining_mas, "timestamp": time.time()}

                                  

            try:

                os.makedirs(os.path.dirname(self.shm_path), exist_ok=True)

                with open(self.shm_path, "w") as f:

                    json.dump(data, f)

            except Exception as e:

                print(f"[BATTERY] Error saving state to RAM: {e}")

                

                                                

            if to_disk:

                try:

                    os.makedirs(os.path.dirname(self.disk_path), exist_ok=True)

                                                            

                    temp_path = self.disk_path + ".tmp"

                    with open(temp_path, "w") as f:

                        json.dump(data, f)

                    os.replace(temp_path, self.disk_path)

                    self.last_disk_save_time = time.time()

                    print(f"[BATTERY] Persisted state to disk: {self.get_percentage():.2f}%")

                except Exception as e:

                    print(f"[BATTERY] Error saving state to disk: {e}")



    def set_heavy_tx(self, enabled):

        with self.lock:

            self._update_energy()

            self.heavy_tx_mode = enabled

            print(f"[BATTERY] Heavy TX mode set to: {enabled}")



    def get_percentage(self):

        with self.lock:

            return max(0.0, min((self.remaining_mas / self.total_capacity_mas) * 100.0, 100.0))



    def reset_charge(self):

        with self.lock:

            self.remaining_mas = self.total_capacity_mas

            self.save_state(to_disk=True)

            print(f"[BATTERY] Charge reset to 100% ({self.remaining_mas:.2f} mAs)")



    def _update_energy(self):

        now = time.time()

        elapsed = now - self.last_update_time

        self.last_update_time = now

        

        if elapsed <= 0.0:

            return

            

        current_draw = 165.0                         

        if self.heavy_tx_mode:

            current_draw += 110.0                          

            

        consumed = elapsed * current_draw

        self.remaining_mas = max(0.0, self.remaining_mas - consumed)



    def _update_loop(self):

        while self.running:

            time.sleep(1.0)

            with self.lock:

                self._update_energy()

                

                         

            self.save_state(to_disk=False)

            

                                                           

            if time.time() - self.last_disk_save_time >= 60.0:

                self.save_state(to_disk=True)



                                         

battery_gauge = BatteryFuelGauge()



def get_system_status():

    import os

    try:

        with open("/proc/uptime", "r") as f:

            uptime_sec = float(f.readline().split()[0])

            uptime_str = f"{int(uptime_sec // 3600)}h {int((uptime_sec % 3600) // 60)}m"

    except:

        uptime_str = "Unknown"

    try:

        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:

            temp_c = float(f.read().strip()) / 1000.0

            temp_str = f"{temp_c:.1f}C"

    except:

        temp_str = "Unknown"

    try:

        with open("/proc/loadavg", "r") as f:

            load = f.read().split()[:3]

            load_str = ", ".join(load)

    except:

        load_str = "Unknown"

        

    global CURRENT_CHANNEL, CURRENT_AIR_RATE, SIMULATED_TX_DELAY, EMG_TST_MODE, consecutive_missed_heartbeats

    battery_pct = battery_gauge.get_percentage()

    return (

        f"--- WackNet Status ---\n"

        f"Battery: {battery_pct:.1f}%\n"

        f"Uptime: {uptime_str}\n"

        f"CPU Temp: {temp_str}\n"

        f"Load: {load_str}\n"

        f"Ch: {CURRENT_CHANNEL} Rate: {CURRENT_AIR_RATE}k\n"

        f"TxDel: {SIMULATED_TX_DELAY} EMG: {EMG_TST_MODE}\n"

        f"ConsecMiss: {consecutive_missed_heartbeats}"

    )



def get_net_info():

    """Return a numbered list of visible WiFi networks."""

    global last_wifi_scan_results

    import subprocess

    networks = scan_wifi()

    last_wifi_scan_results = networks

    if not networks:

        return "No WiFi networks found."

    lines = ["=== WiFi Networks ==="]

    for i, net in enumerate(networks, 1):

        sec = net.get('security', '--')

        lines.append(f"{i}. {net['ssid']} [{net['signal']}%] {sec}")

    return "\n".join(lines)



def get_random_bs():

    import random

    import string

    return "".join(random.choices(string.ascii_letters, k=64))



def get_nmap_list():

    import subprocess

    import re

    

                                                      

    subnets = []

    try:

        res = subprocess.run(["ip", "-4", "addr", "show"], capture_output=True, text=True)

        if res.returncode == 0:

            for line in res.stdout.split('\n'):

                if "inet " in line and " scope " in line and " lo" not in line:

                    match = re.search(r"inet (\d+\.\d+\.\d+)\.\d+/24", line)

                    if match:

                        subnets.append(f"{match.group(1)}.0/24")

    except Exception as e:

        print(f"Error finding subnets: {e}")

        

    if not subnets:

        ip = get_local_ip()

        if ip and ip != "127.0.0.1":

            parts = ip.split('.')

            if len(parts) == 4:

                subnets.append(f"{parts[0]}.{parts[1]}.{parts[2]}.0/24")

                

    if not subnets:

        return "No network connected."

        

    hosts = []

    seen_ips = set()

    for subnet in sorted(list(set(subnets))):

        try:

            res = subprocess.run(["sudo", "nmap", "-sn", subnet], capture_output=True, text=True, timeout=15)

            raw_out = res.stdout

        except Exception as e:

            continue

            

        for line in raw_out.split('\n'):

            match = re.search(r"Nmap scan report for (.*?)(?:\s*\((.*?)\))?$", line)

            if match:

                name = match.group(1).strip()

                ip_addr = match.group(2)

                if ip_addr:

                    ip_addr = ip_addr.strip()

                else:

                    ip_addr = name

                    name = ""

                if ip_addr not in seen_ips:

                    seen_ips.add(ip_addr)

                    hosts.append({"name": name, "ip": ip_addr})

                    

    if not hosts:

        return "No active hosts found."

        

    def sort_key(h):

        name_lower = h["name"].lower()

        if "wack" in name_lower:

            return (0, name_lower)

        return (1, h["ip"])

        

    sorted_hosts = sorted(hosts, key=sort_key)

    lines = ["=== Network Devices ==="]

    for h in sorted_hosts:

        if h["name"]:

            lines.append(f"- {h['name']} ({h['ip']})")

        else:

            lines.append(f"- {h['ip']}")

    return "\n".join(lines)



def scan_wifi():

    global SIMULATION_MODE

    if SIMULATION_MODE:

        time.sleep(3)

        return [

            {"ssid": "TWIN", "signal": 95, "security": "WPA2"},

            {"ssid": "Tactical_Net", "signal": 75, "security": "WPA2"},

            {"ssid": "Guest_Wifi", "signal": 40, "security": "--"}

        ]

    import subprocess

    try:

        subprocess.run(["sudo", "nmcli", "device", "wifi", "rescan"], capture_output=True, check=False)

        time.sleep(3)

        out = subprocess.check_output(["sudo", "nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"], text=True)

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

                                                                                               

        subprocess.run(["sudo", "nmcli", "connection", "delete", ssid], capture_output=True, text=True, timeout=5)

        time.sleep(0.5)

        if password:

            cmd = ["sudo", "nmcli", "device", "wifi", "connect", ssid, "password", password]

        else:

            cmd = ["sudo", "nmcli", "device", "wifi", "connect", ssid]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if res.returncode != 0 and "certificate" in res.stderr.lower():

                                                    

            subprocess.run(

                ["sudo", "nmcli", "connection", "modify", ssid, "802-1x.ca-cert", ""],

                capture_output=True, text=True, timeout=5

            )

            subprocess.run(

                ["sudo", "nmcli", "connection", "modify", ssid, "802-1x.phase2-ca-cert", ""],

                capture_output=True, text=True, timeout=5

            )

            subprocess.run(

                ["sudo", "nmcli", "connection", "modify", ssid, "802-1x.system-ca-certs", "no"],

                capture_output=True, text=True, timeout=5

            )

            res = subprocess.run(["sudo", "nmcli", "connection", "up", ssid], capture_output=True, text=True, timeout=30)

        if res.returncode == 0:

            return {"status": "success", "message": res.stdout.strip()}

        else:

            return {"status": "error", "message": res.stderr.strip()}

    except subprocess.TimeoutExpired:

        return {"status": "error", "message": "Connection attempt timed out"}

    except Exception as e:

        return {"status": "error", "message": str(e)}





                                                            

class MockGPIO:

    BCM = 11

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

        global SIMULATION_MODE

        self.lock = threading.RLock()

        self.mock_ser = None

        self.last_tx_time = 0

        

        if not SIMULATION_MODE:

            try:

                import RPi.GPIO as rgpio

                global GPIO

                GPIO = rgpio

                GPIO.setmode(GPIO.BCM)

                GPIO.setwarnings(False)

                GPIO.setup(M0_PIN, GPIO.OUT)

                GPIO.setup(M1_PIN, GPIO.OUT)

                GPIO.setup(AUX_PIN, GPIO.IN)

                

                import serial

                self.ser = serial.Serial(port=port, baudrate=9600, timeout=0.1)

                

                self.wait_aux()

                GPIO.output(M0_PIN, GPIO.LOW)

                GPIO.output(M1_PIN, GPIO.LOW)

                time.sleep(0.05)

                self.wait_aux()

                print("Hardware Serial & GPIO initialized successfully.")

            except Exception as e:

                print(f"Failed to initialize hardware serial/GPIO: {e}. Falling back to Simulation Mode.")

                SIMULATION_MODE = True

                

        if SIMULATION_MODE:

            self.mock_ser = MockSerial()

            self.ser = self.mock_ser



    def wait_aux(self):

        if SIMULATION_MODE:

            return

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



CURRENT_AIR_RATE = 0.3

CURRENT_CHANNEL = 15

CURRENT_POWER = 0                                           



BACKUP_CONFIG = None

revert_timer = None



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



def revert_config():

    global CURRENT_AIR_RATE, CURRENT_CHANNEL, CURRENT_POWER, BACKUP_CONFIG

    if BACKUP_CONFIG:

        print(f"[REVERT] Reverting config to: {BACKUP_CONFIG}")

        configure_e32(rate=BACKUP_CONFIG["rate"], channel=BACKUP_CONFIG["channel"], power=BACKUP_CONFIG["power"], local_only=True)

        BACKUP_CONFIG = None



def initiate_config_change(rate=None, channel=None, power=None):

    global CURRENT_AIR_RATE, CURRENT_CHANNEL, CURRENT_POWER, BACKUP_CONFIG, revert_timer

    

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

        add_telemetry(prop_frame.hex().upper(), "TX", "HANDSHAKE", payload_id, 10, 0, True)

        

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

        add_telemetry(confirm_frame.hex().upper(), "TX", "HANDSHAKE", payload_id, 12, 0, True)

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

        add_telemetry(verify_frame.hex().upper(), "TX", "HANDSHAKE", payload_id, 13, 0, True)

        

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

                                                                                        

        global consecutive_missed_heartbeats, EMG_TST_MODE

        consecutive_missed_heartbeats = 0

        EMG_TST_MODE = False

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

    global CURRENT_AIR_RATE, CURRENT_CHANNEL, CURRENT_POWER, SIMULATION_MODE

    if not local_only:

        return initiate_config_change(rate, channel, power)



    with hw.lock:

        if rate is not None:

            CURRENT_AIR_RATE = rate

        if channel is not None:

            CURRENT_CHANNEL = channel

        if power is not None:

            CURRENT_POWER = power

            

        if SIMULATION_MODE:

            print(f"[SIMULATOR] Configured E32: Rate={CURRENT_AIR_RATE}kbps, Channel={CURRENT_CHANNEL}, Power={CURRENT_POWER}")

            return True

            

        sped = 0x1A               

        if CURRENT_AIR_RATE == 0.3:

            sped = 0x18

        elif CURRENT_AIR_RATE == 2.4:

            sped = 0x1A

        elif CURRENT_AIR_RATE == 9.6:

            sped = 0x2C

        elif CURRENT_AIR_RATE == 19.2:

            sped = 0x2D

            

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

            

            cfg_cmd = bytes([0xC0, 0x00, 0x00, sped, chan_byte, option_byte])

            

            success = False

            reply = bytearray()

            for attempt in range(3):

                                     

                in_wat = hw.ser.in_waiting

                hw.ser.read(in_wat)

                print(f"[DEBUG_AUX] Cleared {in_wat} bytes from serial buffer. Attempt {attempt}: Writing config command...")

                

                hw.ser.write(cfg_cmd)

                hw.ser.flush()

                

                                                

                start = time.time()

                reply = bytearray()

                while time.time() - start < 0.15:

                    if hw.ser.in_waiting > 0:

                        reply.extend(hw.ser.read(1))

                        if len(reply) == 6:

                            break

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

                        hw.ser.write(cfg_cmd)

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

                print(f"Successfully configured E32 module (persistent): Rate={CURRENT_AIR_RATE}kbps, Channel={CURRENT_CHANNEL}, Power={CURRENT_POWER}.")

            else:

                print(f"Failed to configure E32 module (no/bad reply: {reply.hex()})")

                

            if not SIMULATION_MODE:

                try:

                    hw.ser.reset_input_buffer()

                except:

                    pass

                    

            return success

        except Exception as e:

            print(f"Error configuring E32: {e}")

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

    global active_rx_sessions, BACKUP_CONFIG, revert_timer

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

                

            full_frame = bytes(rx_buffer[:58])

            del rx_buffer[:58]

            if True:

                crc = 0

                for b in full_frame[:57]:

                    crc ^= b

                

                crc_ok = (crc == full_frame[57])

                

                p_type = full_frame[1]

                payload_id = struct.unpack_from(">I", full_frame, 2)[0]

                index = full_frame[6]

                count = full_frame[7]

                

                p_type_name = "UNKNOWN"

                if p_type == 0x00: p_type_name = "TEXT"

                elif p_type == 0x01: p_type_name = "HANDSHAKE"

                elif p_type == 0x02: p_type_name = "PING"

                elif p_type == 0x03: p_type_name = "PONG"

                elif p_type == 0x04: p_type_name = "IMAGE"

                elif p_type == 0x05: p_type_name = "CMD_REQ"

                elif p_type == 0x06: p_type_name = "CMD_RESP"

                elif p_type == 0x07: p_type_name = "CMD_IN"

                elif p_type == 0x08: p_type_name = "CMD_EOF"

                elif p_type == 0x09: p_type_name = "CMD_CAN"

                

                add_telemetry(full_frame.hex().upper(), "RX", p_type_name, payload_id, index, count, crc_ok)

                

                if not crc_ok:

                    print(f"CRC Mismatch on incoming frame! Computed {crc:#x}, got {full_frame[57]:#x}")

                    continue

                    

                                             

                global heartbeat_active, consecutive_missed_heartbeats, EMG_TST_MODE

                if not heartbeat_active:

                    print("[HEARTBEAT] Handheld ping/packet received. Activating heartbeat system!")

                    heartbeat_active = True

                consecutive_missed_heartbeats = 0

                if CURRENT_AIR_RATE > 0.3:

                    EMG_TST_MODE = False

                if p_type not in (0x02, 0x03):

                    global last_other_activity_time

                    last_other_activity_time = time.time()

                    

                                               

                if p_type == 0x02:       

                                           

                    pong = bytearray(58)

                    pong[0] = 0xAA

                    pong[1] = 0x03       

                    pong[2:6] = full_frame[2:6]          

                    pong[6:14] = full_frame[6:14]                 

                    

                    pcrc = 0

                    for b in pong[:57]: pcrc ^= b

                    pong[57] = pcrc

                    

                    hw.write_raw_frame(pong)

                    add_telemetry(pong.hex().upper(), "TX", "PONG", payload_id, index, count, True)

                    

                elif p_type == 0x03:       

                    with ping_lock:

                        if payload_id in pending_pings:

                            pending_pings[payload_id] = full_frame

                            

                elif p_type == 0x09:                 

                    cancel_active_command()

                    

                elif p_type == 0x01:            

                    stage = full_frame[6]

                    param = full_frame[7]                     

                    total_chunks = full_frame[8]

                    data_type = full_frame[9]

                    

                                                                          

                    with pending_lock:

                        if payload_id in pending_responses:

                            pending_responses[payload_id] = full_frame

                            

                                                                 

                    if stage == 1:      

                        total_length = struct.unpack_from(">I", full_frame, 10)[0]

                        best_effort = (full_frame[14] == 1)

                        with rx_sessions_lock:

                            active_rx_sessions[payload_id] = {

                                "type": data_type,

                                "total_chunks": total_chunks,

                                "total_length": total_length,

                                "delay_ms": max(param, 15),

                                "chunks": {},

                                "last_active": time.time(),

                                "best_effort": best_effort

                            }

                                                

                        reply = bytearray(58)

                        reply[0] = 0xAA

                        reply[1] = 0x01

                        reply[2:6] = full_frame[2:6]

                        reply[6] = 2          

                        reply[7] = max(param, 15)

                        reply[8] = total_chunks

                        reply[9] = data_type

                        

                        crc = 0

                        for b in reply[:57]: crc ^= b

                        reply[57] = crc

                        

                        hw.write_raw_frame(reply)

                        add_telemetry(reply.hex().upper(), "TX", "HANDSHAKE", payload_id, 2, total_chunks, True)

                        

                    elif stage == 3:              

                        with rx_sessions_lock:

                            if payload_id in active_rx_sessions:

                                active_rx_sessions[payload_id]["last_active"] = time.time()

                                

                    elif stage == 5:      

                        with rx_sessions_lock:

                            session = active_rx_sessions.get(payload_id)

                            status = 0          

                            is_malformed = False

                            if not session:

                                status = 1          

                            else:

                                received = len(session["chunks"])

                                if received < session["total_chunks"]:

                                    status = 1          

                                    is_malformed = True

                                    

                            reply = bytearray(58)

                            reply[0] = 0xAA

                            reply[1] = 0x01

                            reply[2:6] = full_frame[2:6]

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

                                

                            crc = 0

                            for b in reply[:57]: crc ^= b

                            reply[57] = crc

                            

                            hw.write_raw_frame(reply)

                            add_telemetry(reply.hex().upper(), "TX", "HANDSHAKE", payload_id, 6, status, True)

                            

                                                                                                          

                            if status == 0 and session:

                                ordered = [session["chunks"][i] for i in sorted(session["chunks"].keys())]

                                full_b64_or_raw = b"".join(ordered)

                                decoded_payload = wacknet_decompress(full_b64_or_raw)

                                full_b64 = decoded_payload.decode('utf-8', errors='ignore')

                                

                                try:

                                    if session["type"] in (0x00, 0x05, 0x07):

                                        decoded = base64.b64decode(full_b64).decode('utf-8', errors='ignore')

                                    else:

                                        decoded = full_b64

                                except Exception as ex:

                                    decoded = f"Error decoding: {ex}"

                                    

                                if session["type"] == 0x05:              

                                    match = re.match(r"^\[(TKT-[A-Za-z0-9]+)\]\s*(.*)$", decoded, re.DOTALL)

                                    if match:

                                        t_id = match.group(1)

                                        cmd_str = match.group(2)

                                    else:

                                        t_id = None

                                        cmd_str = decoded

                                    run_command_asynchronously(cmd_str, t_id)

                                elif session["type"] == 0x07:                

                                    match = re.match(r"^\[(TKT-[A-Za-z0-9]+)\]\s*(.*)$", decoded, re.DOTALL)

                                    if match:

                                        t_id = match.group(1)

                                        inp_str = match.group(2)

                                    else:

                                        t_id = None

                                        inp_str = decoded

                                    write_command_input(inp_str, t_id)

                                else:

                                    with msg_lock:

                                        incoming_messages.append({

                                            "timestamp": int(time.time() * 1000),

                                            "payload_id": payload_id,

                                            "type": session["type"],

                                            "data": decoded

                                        })

                                        if len(incoming_messages) > 30:

                                            incoming_messages.pop(0)

                                            

                                    cmd_stripped = decoded.strip()

                                    if session["type"] == 0x00 and (cmd_stripped in ("needIP", "needSTATUS", "needNET", "needBS", "needNMAP", "needX") or cmd_stripped.startswith("needCON")):

                                        def reply_task():

                                            time.sleep(0.5)

                                            if cmd_stripped == "needIP":

                                                text_reply = f"IP: {get_local_ip()}"

                                            elif cmd_stripped == "needSTATUS":

                                                text_reply = get_system_status()

                                            elif cmd_stripped == "needNET":

                                                text_reply = get_net_info()

                                            elif cmd_stripped == "needBS":

                                                text_reply = get_random_bs()

                                            elif cmd_stripped == "needNMAP":

                                                text_reply = get_nmap_list()

                                            elif cmd_stripped == "needX":

                                                text_reply = "Available options:\nneedIP - Get local IP\nneedSTATUS - Get system status\nneedNET - List visible WiFi networks\nneedCON:<num>[:<pass>] - Connect to WiFi\nneedBS - Get random BS\nneedNMAP - List active subnets\nneedX - List commands"

                                            elif cmd_stripped.startswith("needCON"):

                                                                               

                                                parts = cmd_stripped.split(":", 2)

                                                if len(parts) < 2:

                                                    text_reply = "Usage: needCON:<number>[:<password>]"

                                                else:

                                                    try:

                                                        net_idx = int(parts[1]) - 1

                                                        pwd = parts[2] if len(parts) > 2 else ""

                                                        if not last_wifi_scan_results:

                                                            text_reply = "No cached scan. Send needNET first."

                                                        elif net_idx < 0 or net_idx >= len(last_wifi_scan_results):

                                                            text_reply = f"Invalid index. Range: 1-{len(last_wifi_scan_results)}"

                                                        else:

                                                            target_ssid = last_wifi_scan_results[net_idx]["ssid"]

                                                            text_reply = f"Connecting to: {target_ssid}...\n"

                                                            result = connect_wifi(target_ssid, pwd)

                                                            text_reply += f"Status: {result['status']}\n{result.get('message', '')}"

                                                    except ValueError:

                                                        text_reply = "needCON:<number> - number must be an integer"

                                            else:

                                                text_reply = "Unknown cmd"

                                            reply_bytes = base64.b64encode(text_reply.encode('utf-8'))

                                            start_handshake_session(0x00, reply_bytes, SIMULATED_TX_DELAY)

                                        threading.Thread(target=reply_task, daemon=True).start()

                                        

                                rejoined_active = active_rx_sessions.pop(payload_id, None)

                                

                    elif stage == 10:                 

                        rate_code = full_frame[7]

                        r_chan = full_frame[8]

                        r_pow = full_frame[9]

                        

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

                        reply[2:6] = full_frame[2:6]

                        reply[6] = 11

                        reply[7] = rate_code

                        reply[8] = r_chan

                        reply[9] = r_pow

                        

                        crc = 0

                        for b in reply[:57]: crc ^= b

                        reply[57] = crc

                        

                        print(f"[CONFIG_NEG] PROPOSE received: Rate={r_rate}, Chan={r_chan}, Pow={r_pow}. Sending AGREE (no switch yet)...")

                        hw.write_raw_frame(reply)

                        add_telemetry(reply.hex().upper(), "TX", "HANDSHAKE", payload_id, 11, 0, True)

 

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

                        reply[2:6] = full_frame[2:6]

                        reply[6] = 14              

                        

                        crc = 0

                        for b in reply[:57]: crc ^= b

                        reply[57] = crc

                        

                        print("[CONFIG_NEG] VERIFY received on new channel, sending VERIFY_ACK. Config confirmed!")

                        hw.write_raw_frame(reply)

                        add_telemetry(reply.hex().upper(), "TX", "HANDSHAKE", payload_id, 14, 0, True)

                        

                        if revert_timer:

                            revert_timer.cancel()

                            revert_timer = None

                        BACKUP_CONFIG = None

 

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

                            data_bytes = full_frame[8:8+chunk_len]

                            session["chunks"][index] = bytes(data_bytes)

                            session["last_active"] = time.time()

                            

        except Exception as e:

            print(f"Exception in Rx thread: {e}")

            

        time.sleep(0.002)

 

def rx_session_cleaner_thread():

    while True:

        try:

            now = time.time()

            to_delete = []

            with rx_sessions_lock:

                for p_id, sess in list(active_rx_sessions.items()):

                    timeout_dur = max(15.0, get_block_guard_delay() * 2.0)

                    if now - sess["last_active"] > timeout_dur:

                        to_delete.append((p_id, sess))

                for p_id, sess in to_delete:

                    print(f"Cleaning up timed-out RX session {p_id}")

                    best_effort = sess.get("best_effort", False)

                    received = len(sess["chunks"])

                    total = sess["total_chunks"]

                    if best_effort and received > 0:

                        is_malformed = received < total

                        ordered = [sess["chunks"][i] for i in sorted(sess["chunks"].keys())]

                        full_b64_or_raw = b"".join(ordered)

                        decoded_payload = wacknet_decompress(full_b64_or_raw)

                        full_b64 = decoded_payload.decode('utf-8', errors='ignore')

                        try:

                            if sess["type"] in (0x00, 0x05, 0x07):

                                decoded = base64.b64decode(full_b64).decode('utf-8', errors='ignore')

                            else:

                                decoded = full_b64

                        except Exception as ex:

                            decoded = f"Error decoding: {ex}"

                        if is_malformed and sess["type"] == 0x00:

                            decoded = f"[MALFORMED/PARTIAL] {decoded}"

                            

                        if sess["type"] == 0x05:              

                            match = re.match(r"^\[(TKT-[A-Za-z0-9]+)\]\s*(.*)$", decoded, re.DOTALL)

                            if match:

                                t_id = match.group(1)

                                cmd_str = match.group(2)

                            else:

                                t_id = None

                                cmd_str = decoded

                            run_command_asynchronously(cmd_str, t_id)

                        elif sess["type"] == 0x07:                

                            match = re.match(r"^\[(TKT-[A-Za-z0-9]+)\]\s*(.*)$", decoded, re.DOTALL)

                            if match:

                                t_id = match.group(1)

                                inp_str = match.group(2)

                            else:

                                t_id = None

                                inp_str = decoded

                            write_command_input(inp_str, t_id)

                        else:

                            with msg_lock:

                                incoming_messages.append({

                                    "timestamp": int(time.time() * 1000),

                                    "payload_id": p_id,

                                    "type": sess["type"],

                                    "data": decoded

                                })

                                if len(incoming_messages) > 30:

                                    incoming_messages.pop(0)

                                    

                            cmd_stripped = decoded.strip()

                            if sess["type"] == 0x00 and (cmd_stripped in ("needIP", "needSTATUS", "needNET", "needBS", "needNMAP", "needX") or cmd_stripped.startswith("needCON")):

                                def reply_task(cmd=cmd_stripped):

                                    time.sleep(0.5)

                                    if cmd == "needIP":

                                        text_reply = f"IP: {get_local_ip()}"

                                    elif cmd == "needSTATUS":

                                        text_reply = get_system_status()

                                    elif cmd == "needNET":

                                        text_reply = get_net_info()

                                    elif cmd == "needBS":

                                        text_reply = get_random_bs()

                                    elif cmd == "needNMAP":

                                        text_reply = get_nmap_list()

                                    elif cmd == "needX":

                                        text_reply = "Available options:\nneedIP - Get local IP\nneedSTATUS - Get system status\nneedNET - List visible WiFi networks\nneedCON:<num>[:<pass>] - Connect to WiFi\nneedBS - Get random BS\nneedNMAP - List active subnets\nneedX - List commands"

                                    elif cmd.startswith("needCON"):

                                        parts = cmd.split(":", 2)

                                        if len(parts) < 2:

                                            text_reply = "Usage: needCON:<number>[:<password>]"

                                        else:

                                            try:

                                                net_idx = int(parts[1]) - 1

                                                pwd = parts[2] if len(parts) > 2 else ""

                                                if not last_wifi_scan_results:

                                                    text_reply = "No cached scan. Send needNET first."

                                                elif net_idx < 0 or net_idx >= len(last_wifi_scan_results):

                                                    text_reply = f"Invalid index. Range: 1-{len(last_wifi_scan_results)}"

                                                else:

                                                    target_ssid = last_wifi_scan_results[net_idx]["ssid"]

                                                    text_reply = f"Connecting to: {target_ssid}...\n"

                                                    result = connect_wifi(target_ssid, pwd)

                                                    text_reply += f"Status: {result['status']}\n{result.get('message', '')}"

                                            except ValueError:

                                                text_reply = "needCON:<number> - number must be an integer"

                                    else:

                                        text_reply = "Unknown cmd"

                                    reply_bytes = base64.b64encode(text_reply.encode('utf-8'))

                                    start_handshake_session(0x00, reply_bytes, SIMULATED_TX_DELAY)

                                threading.Thread(target=reply_task, daemon=True).start()

                    del active_rx_sessions[p_id]

        except Exception as e:

            print(f"Exception in cleaner thread: {e}")

                                         

        stale = [pid for pid, p in list(pending_config_proposals.items()) if time.time() - p.get("time", 0) > 30]

        for pid in stale:

            pending_config_proposals.pop(pid, None)

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



def start_handshake_session(p_type, payload_bytes, delay_ms):

    global active_handshake_state

    

    payload_id = random.randint(100000, 999999)

    compressed_payload = wacknet_compress(payload_bytes)

    chunks = [compressed_payload[i:i+49] for i in range(0, len(compressed_payload), 49)]

    total_count = len(chunks)

    

    def update_state(stage, status, error=None, sent=0):

        global active_handshake_state

        with state_lock:

            active_handshake_state = {

                "payload_id": payload_id,

                "stage": stage,

                "total_chunks": total_count,

                "sent_chunks": sent,

                "status": status,

                "error": error

            }



    outbound_lock.acquire()

    try:

        return _start_handshake_session_locked(p_type, compressed_payload, delay_ms, payload_id, chunks, total_count, update_state)

    finally:

        outbound_lock.release()



def _start_handshake_session_locked(p_type, payload_bytes, delay_ms, payload_id, chunks, total_count, update_state):

    update_state(1, "negotiating")

    

                          

    syn = bytearray(58)

    syn[0] = 0xAA

    syn[1] = 0x01

    struct.pack_into(">I", syn, 2, payload_id)

    syn[6] = 1          

    syn[7] = min(delay_ms, 255)

    syn[8] = total_count

    syn[9] = p_type

    struct.pack_into(">I", syn, 10, len(payload_bytes))

    syn[14] = 0                                                               

    

    scrc = 0

    for b in syn[:57]: scrc ^= b

    syn[57] = scrc



    with pending_lock:

        pending_responses[payload_id] = None



    agreed_delay = delay_ms

    syn_ack_ok = False

    

    for retry in range(3):

        update_state(1, f"sending_syn_retry_{retry}")

        hw.write_raw_frame(syn)

        add_telemetry(syn.hex().upper(), "TX", "HANDSHAKE", payload_id, 1, total_count, True)

        

        start_wait = time.time()

        while time.time() - start_wait < 3.0:

            with pending_lock:

                frame = pending_responses.get(payload_id)

                if frame and frame[1] == 0x01 and frame[6] == 2:

                    agreed_delay = frame[7]

                    syn_ack_ok = True

                    break

            time.sleep(0.01)

        if syn_ack_ok:

            break

            

    if not syn_ack_ok:

        update_state(1, "failed", "SYN-ACK handshake timeout after 3 retries")

        with pending_lock:

            if payload_id in pending_responses: del pending_responses[payload_id]

        return False



    update_state(2, "negotiated")

    time.sleep(0.05)



                                

    est = bytearray(58)

    est[0] = 0xAA

    est[1] = 0x01

    struct.pack_into(">I", est, 2, payload_id)

    est[6] = 3

    est[7] = min(agreed_delay, 255)

    est[8] = total_count

    

    ecrc = 0

    for b in est[:57]: ecrc ^= b

    est[57] = ecrc

    

    hw.write_raw_frame(est)

    add_telemetry(est.hex().upper(), "TX", "HANDSHAKE", payload_id, 3, total_count, True)

    update_state(3, "established")

    time.sleep(agreed_delay / 1000.0)



                                                                            

    chunks_to_send = list(range(total_count))

    nak_round = 0

    max_nak_rounds = 5

    block_guard_delay = get_block_guard_delay()

    

    verification_status = 1

    received_fin_ack = None

    

    while nak_round <= max_nak_rounds:

        update_state(4, f"transmitting_round_{nak_round}" if nak_round > 0 else "transmitting", sent=total_count - len(chunks_to_send))

        battery_gauge.set_heavy_tx(True)

        try:

            for i in range(0, len(chunks_to_send), 8):

                block = chunks_to_send[i:i+8]

                for idx in block:

                    chunk = chunks[idx]

                    frame = bytearray(58)

                    frame[0] = 0xAA

                    frame[1] = p_type

                    struct.pack_into(">I", frame, 2, payload_id)

                    frame[6] = idx

                    frame[7] = total_count

                    frame[8:8+len(chunk)] = chunk

                    

                    crc = 0

                    for b in frame[:57]: crc ^= b

                    frame[57] = crc

                    

                    hw.write_raw_frame(frame)

                    p_type_name = "TEXT" if p_type == 0x00 else "IMAGE"

                    add_telemetry(frame.hex().upper(), "TX", p_type_name, payload_id, idx, total_count, True)

                    

                                                    

                    chunks_sent_so_far = (total_count - len(chunks_to_send)) + (i + block.index(idx) + 1)

                    update_state(4, f"transmitting_round_{nak_round}" if nak_round > 0 else "transmitting", sent=chunks_sent_so_far)

                

                                                                                   

                block_air_time = (len(block) * 58 * 8) / (CURRENT_AIR_RATE * 1000.0)

                time.sleep(block_air_time * 1.15)

        finally:

            battery_gauge.set_heavy_tx(False)

            

                              

        fin = bytearray(58)

        fin[0] = 0xAA

        fin[1] = 0x01

        struct.pack_into(">I", fin, 2, payload_id)

        fin[6] = 5

        

        fcrc = 0

        for b in fin[:57]: fcrc ^= b

        fin[57] = fcrc



        with pending_lock:

            pending_responses[payload_id] = None



        fin_ack_ok = False

        verification_status = 1

        received_fin_ack = None

        

        for retry in range(3):

            update_state(5, f"sending_fin_round_{nak_round}_retry_{retry}", sent=total_count)

            hw.write_raw_frame(fin)

            add_telemetry(fin.hex().upper(), "TX", "HANDSHAKE", payload_id, 5, 0, True)

            

            start_wait = time.time()

            while time.time() - start_wait < 3.0:

                with pending_lock:

                    frame = pending_responses.get(payload_id)

                    if frame and frame[1] == 0x01 and frame[6] == 6:

                        verification_status = frame[7]

                        received_fin_ack = bytes(frame)

                        fin_ack_ok = True

                        break

                time.sleep(0.01)

            if fin_ack_ok:

                break



        if not fin_ack_ok:

            update_state(5, "failed", f"FIN-ACK validation timeout at round {nak_round}")

            with pending_lock:

                if payload_id in pending_responses: del pending_responses[payload_id]

            return False

            

        if verification_status == 0:

            update_state(6, "success", sent=total_count)

            with pending_lock:

                if payload_id in pending_responses: del pending_responses[payload_id]

            return True

            

        elif verification_status == 1:

            missing_chunks = []

            bitmask = received_fin_ack[8:57]

            for idx in range(total_count):

                byte_idx = idx // 8

                bit_idx = idx % 8

                if byte_idx < len(bitmask) and (bitmask[byte_idx] & (1 << bit_idx)):

                    missing_chunks.append(idx)

                    

            if not missing_chunks:

                update_state(6, "success", sent=total_count)

                with pending_lock:

                    if payload_id in pending_responses: del pending_responses[payload_id]

                return True

                

            print(f"[NAK ROUND {nak_round}] Missing chunks: {missing_chunks}")

            chunks_to_send = missing_chunks

            nak_round += 1

            

        else:

            update_state(6, "failed", f"Receiver reports CRC errors/status {verification_status}", sent=total_count)

            with pending_lock:

                if payload_id in pending_responses: del pending_responses[payload_id]

            return False

            

    update_state(6, "failed", "Exceeded maximum NAK retransmission rounds", sent=total_count)

    return False



def run_ping_test():

    ping_id = random.randint(100000, 999999)

    sent_time_ms = int(time.time() * 1000)

    

    ping = bytearray(58)

    ping[0] = 0xAA

    ping[1] = 0x02       

    struct.pack_into(">I", ping, 2, ping_id)

    struct.pack_into(">Q", ping, 6, sent_time_ms)

    

    pcrc = 0

    for b in ping[:57]: pcrc ^= b

    ping[57] = pcrc



    with ping_lock:

        pending_pings[ping_id] = None

        

    hw.write_raw_frame(ping)

    add_telemetry(ping.hex().upper(), "TX", "PING", ping_id, 0, 0, True)

    

    start_wait = time.time()

    timeout = 4.0 if CURRENT_AIR_RATE > 0.3 else 5.0

    while time.time() - start_wait < timeout:

        with ping_lock:

            frame = pending_pings.get(ping_id)

            if frame:

                rtt = int(time.time() * 1000) - sent_time_ms

                del pending_pings[ping_id]

                return {"status": "success", "rtt": rtt}

        time.sleep(0.01)

        

    with ping_lock:

        if ping_id in pending_pings: del pending_pings[ping_id]

    return {"status": "timeout"}



def run_ping_test_short_timeout(timeout=1.2):

    ping_id = random.randint(100000, 999999)

    sent_time_ms = int(time.time() * 1000)

    

    ping = bytearray(58)

    ping[0] = 0xAA

    ping[1] = 0x02       

    struct.pack_into(">I", ping, 2, ping_id)

    struct.pack_into(">Q", ping, 6, sent_time_ms)

    

    pcrc = 0

    for b in ping[:57]: pcrc ^= b

    ping[57] = pcrc



    with ping_lock:

        pending_pings[ping_id] = None

        

    hw.write_raw_frame(ping)

    

    start_wait = time.time()

    while time.time() - start_wait < timeout:

        with ping_lock:

            frame = pending_pings.get(ping_id)

            if frame:

                rtt = int(time.time() * 1000) - sent_time_ms

                del pending_pings[ping_id]

                return {"status": "success", "rtt": rtt}

        time.sleep(0.01)

        

    with ping_lock:

        if ping_id in pending_pings: del pending_pings[ping_id]

    return {"status": "timeout"}



import subprocess

import pty

import select



class InteractiveCommand:

    def __init__(self, command, on_output, on_close):

        self.command = command

        self.on_output = on_output

        self.on_close = on_close

        self.master_fd, self.slave_fd = pty.openpty()

        self.proc = subprocess.Popen(

            ["/bin/bash", "-c", command],

            stdin=self.slave_fd,

            stdout=self.slave_fd,

            stderr=self.slave_fd,

            preexec_fn=os.setsid,

            text=False

        )

        os.close(self.slave_fd)

        self.thread = threading.Thread(target=self._read_loop, daemon=True)

        self.thread.start()



    def _read_loop(self):

        buffer = bytearray()

        last_read_time = time.time()

        while self.proc.poll() is None:

            r, w, x = select.select([self.master_fd], [], [], 0.05)

            if self.master_fd in r:

                try:

                    data = os.read(self.master_fd, 1024)

                    if data:

                        buffer.extend(data)

                        last_read_time = time.time()

                except OSError:

                    break

            if len(buffer) > 0 and (len(buffer) >= 100 or time.time() - last_read_time > 0.2):

                self.on_output(bytes(buffer))

                buffer.clear()

            time.sleep(0.01)

        

                            

        while True:

            r, w, x = select.select([self.master_fd], [], [], 0.02)

            if self.master_fd in r:

                try:

                    data = os.read(self.master_fd, 1024)

                    if not data: break

                    buffer.extend(data)

                except OSError:

                    break

            else:

                break

        if len(buffer) > 0:

            self.on_output(bytes(buffer))

        

        try:

            os.close(self.master_fd)

        except:

            pass

        self.on_close()



    def write_input(self, text):

        try:

            os.write(self.master_fd, text.encode('utf-8') + b'\n')

        except Exception as e:

            print(f"Error writing input: {e}")



    def terminate(self):

        try:

            os.killpg(os.getpgid(self.proc.pid), 9)

        except Exception:

            pass



def run_command_asynchronously(command_str, ticket_id=None):

    global active_command_proc, active_tickets

    print(f"[CMD] Starting interactive command: {command_str} (Ticket: {ticket_id})")

    if active_command_proc:

        print("[CMD] Killing old active command...")

        active_command_proc.terminate()

        active_command_proc = None

        

    if ticket_id:

        active_tickets[ticket_id] = []

        

    def on_output(data):

        print(f"[CMD] Output: {data.decode('utf-8', errors='ignore')}")

        if ticket_id and ticket_id in active_tickets:

            active_tickets[ticket_id].append(data)

            

        payload_bytes = data

        if ticket_id:

            prefix = f"[{ticket_id}] ".encode('utf-8')

            payload_bytes = prefix + data

            

        b64_out = base64.b64encode(payload_bytes)

        threading.Thread(target=start_handshake_session, args=(0x06, b64_out, SIMULATED_TX_DELAY), daemon=True).start()

        

    def on_close():

        global active_command_proc, active_tickets

        print("[CMD] Process terminated.")

        active_command_proc = None

        

        eof_payload = b"EOF"

        if ticket_id:

            eof_payload = f"[{ticket_id}] EOF".encode('utf-8')

        threading.Thread(target=start_handshake_session, args=(0x08, eof_payload, SIMULATED_TX_DELAY), daemon=True).start()

        

        if ticket_id and ticket_id in active_tickets:

            raw_output = b"".join(active_tickets[ticket_id])

            decoded_output = raw_output.decode('utf-8', errors='ignore')

            return_msg = f"[{ticket_id}] Command completed. Output:\n{decoded_output}"

            b64_msg = base64.b64encode(return_msg.encode('utf-8'))

            print(f"[CMD] Sending final return message for ticket {ticket_id}")

            threading.Thread(target=start_handshake_session, args=(0x00, b64_msg, SIMULATED_TX_DELAY), daemon=True).start()

            del active_tickets[ticket_id]

        

    active_command_proc = InteractiveCommand(command_str, on_output, on_close)

    active_command_proc.ticket_id = ticket_id



def write_command_input(input_str, ticket_id=None):

    global active_command_proc

    if active_command_proc:

        proc_ticket_id = getattr(active_command_proc, 'ticket_id', None)

        if proc_ticket_id and ticket_id and proc_ticket_id != ticket_id:

            print(f"[CMD] Input ticket ID mismatch! Process: {proc_ticket_id}, Received: {ticket_id}. Ignoring input.")

            return

        print(f"[CMD] Input received for {proc_ticket_id}: {input_str}")

        active_command_proc.write_input(input_str)

    else:

        print("[CMD] No active process for input.")



def cancel_active_command():

    global active_command_proc

    if active_command_proc:

        print("[CMD] Cancelling active process...")

        active_command_proc.terminate()

        active_command_proc = None



def base_heartbeat_loop():

    global EMG_TST_MODE, consecutive_missed_heartbeats, CURRENT_CHANNEL, CURRENT_AIR_RATE, heartbeat_active

    print("[HEARTBEAT] Thread active.")

    time.sleep(2)

    

    while True:

        if not heartbeat_active:

            time.sleep(1.0)

            continue

            

        other_active = False

        if active_command_proc is not None:

            other_active = True

        elif active_handshake_state is not None and active_handshake_state.get("status") not in ("success", "failed"):

            other_active = True

        elif len(active_rx_sessions) > 0:

            other_active = True

        elif time.time() - last_other_activity_time < 20.0:

            other_active = True

            

        if other_active:

            consecutive_missed_heartbeats = 0

            time.sleep(1.0)

            continue

            

        ping_id = random.randint(100000, 999999)

        sent_time_ms = int(time.time() * 1000)

        

        ping = bytearray(58)

        ping[0] = 0xAA

        ping[1] = 0x02       

        struct.pack_into(">I", ping, 2, ping_id)

        struct.pack_into(">Q", ping, 6, sent_time_ms)

        

        try:

            la_time_str = datetime.now(ZoneInfo('America/Los_Angeles')).strftime("%Y-%m-%d %H:%M:%S")

            time_bytes = la_time_str.encode('utf-8')

            ping[14:14+len(time_bytes)] = time_bytes

        except Exception as e:

            la_time_str = "Error"

            print(f"[HEARTBEAT] LA time err: {e}")

            

        pcrc = 0

        for b in ping[:57]: pcrc ^= b

        ping[57] = pcrc



        with ping_lock:

            pending_pings[ping_id] = None

            

        print(f"[HEARTBEAT] Ping {ping_id} (LA: {la_time_str})")

        hw.write_raw_frame(ping)

        add_telemetry(ping.hex().upper(), "TX", "PING", ping_id, 0, 0, True)

        

        start_wait = time.time()

        pong_received = False

        pong_timeout = 5.0 if CURRENT_AIR_RATE > 0.3 else 3.0

        while time.time() - start_wait < pong_timeout:

            with ping_lock:

                frame = pending_pings.get(ping_id)

                if frame:

                    pong_received = True

                    del pending_pings[ping_id]

                    break

            time.sleep(0.02)

            

        if pong_received:

            consecutive_missed_heartbeats = 0

            if EMG_TST_MODE:

                print("[HEARTBEAT] EMG TST Connection Restored!")

        else:

            consecutive_missed_heartbeats += 1

            print(f"[HEARTBEAT] Timeout ({consecutive_missed_heartbeats})")

            with ping_lock:

                if ping_id in pending_pings: del pending_pings[ping_id]

                

            if consecutive_missed_heartbeats >= 3 and not EMG_TST_MODE:

                print("[HEARTBEAT] 3 Missed heartbeats. Dropping to EMG TST (0.3kbps) failsafe...")

                EMG_TST_MODE = True

                configure_e32(rate=0.3, channel=CURRENT_CHANNEL, power=0, local_only=True)



        interval = 6.0 if (EMG_TST_MODE and consecutive_missed_heartbeats >= 2) else 15.0

        time.sleep(interval)



def startup_scan_thread():

    global CURRENT_AIR_RATE, CURRENT_CHANNEL, CURRENT_POWER, startup_scan_active, EMG_TST_MODE

    print("[SCAN] Waiting 5s for handheld initialization...")

    time.sleep(5)

    print("[SCAN] Starting startup scanning...")

    startup_scan_active = True

    

    initial_targets = [

        {"channel": 15, "rate": 2.4},

        {"channel": 15, "rate": 9.6},

        {"channel": 15, "rate": 19.2},

        {"channel": 16, "rate": 2.4},

        {"channel": 16, "rate": 9.6},

        {"channel": 16, "rate": 19.2}

    ]

    

    all_targets = []

    for ch in range(32):

        for r in [0.3, 2.4, 9.6, 19.2]:

            t = {"channel": ch, "rate": r}

            if t not in initial_targets:

                all_targets.append(t)

                

    scan_list = initial_targets + all_targets

    

    found = False

    idx = 0

    while not found:

        target = scan_list[idx % len(scan_list)]

        print(f"[SCAN] Trying Channel={target['channel']} ({410+target['channel']}MHz) @ {target['rate']}kbps...")

        

        configure_e32(rate=target["rate"], channel=target["channel"], power=0, local_only=True)

        time.sleep(0.3)

        

        timeout = 4.5 if target["rate"] == 0.3 else 1.2

        ping_res = run_ping_test_short_timeout(timeout=timeout)

        if ping_res["status"] == "success":

            print(f"[SCAN] Handheld found at Channel={target['channel']} @ {target['rate']}kbps")

            found = True

            

            configure_e32(rate=target["rate"], channel=target["channel"], power=0, local_only=True)

            

            if target["channel"] != 15 or target["rate"] != 2.4:

                print("[SCAN] Negotiating handheld to Channel 15 (425MHz) @ 2.4kbps...")

                neg_success = initiate_config_change(rate=2.4, channel=15, power=0)

                if neg_success:

                    print("[SCAN] Negotiated to 425MHz @ 2.4kbps.")

                    EMG_TST_MODE = False

                else:

                    print("[SCAN] Negotiation failed. Restarting scan.")

                    found = False

                    time.sleep(1.0)

            else:

                EMG_TST_MODE = False

            break

            

        idx += 1

        time.sleep(0.1)

        

    print("[SCAN] Startup scan finished successfully.")

    startup_scan_active = False



class CustomFrontendAPI(SimpleHTTPRequestHandler):

    def log_message(self, format, *args):

        pass



    def do_GET(self):

        global telemetry_log, incoming_messages, active_handshake_state, SIMULATION_MODE, SIMULATED_PACKET_LOSS, SIMULATED_TX_DELAY

        

        if self.path == "/":

            self.send_response(200)

            self.send_header("Content-Type", "text/html")

            self.end_headers()

            try:

                with open("index.html", "rb") as f: 

                    self.wfile.write(f.read())

            except: 

                self.wfile.write(b"index.html asset missing.")

            

        elif self.path == "/api/log":

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.send_header("Cache-Control", "no-cache")

            self.end_headers()

            

            with telemetry_lock:

                telemetry_data = list(telemetry_log)

            self.wfile.write(json.dumps(telemetry_data).encode('utf-8'))

            

        elif self.path == "/api/messages":

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.end_headers()

            

            with msg_lock:

                msgs = list(incoming_messages)

                incoming_messages.clear()

            self.wfile.write(json.dumps(msgs).encode('utf-8'))

            

        elif self.path == "/api/handshake_status":

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.end_headers()

            

            with state_lock:

                state = active_handshake_state

            self.wfile.write(json.dumps(state).encode('utf-8'))

            

        elif self.path == "/api/battery":

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.end_headers()

            

            data = {

                "percentage": battery_gauge.get_percentage(),

                "remaining_mas": battery_gauge.remaining_mas,

                "total_capacity_mas": battery_gauge.total_capacity_mas,

                "heavy_tx": battery_gauge.heavy_tx_mode

            }

            self.wfile.write(json.dumps(data).encode('utf-8'))

            

        elif self.path == "/api/config":

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.end_headers()

            

            config = {

                "simulation_mode": SIMULATION_MODE,

                "packet_loss": SIMULATED_PACKET_LOSS,

                "tx_delay": SIMULATED_TX_DELAY,

                "air_rate": CURRENT_AIR_RATE,

                "channel": CURRENT_CHANNEL,

                "tx_power": CURRENT_POWER

            }

            self.wfile.write(json.dumps(config).encode('utf-8'))

            

        elif self.path == "/api/wifi/scan":

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.end_headers()

            self.wfile.write(json.dumps(scan_wifi()).encode('utf-8'))

            

        elif self.path == "/api/radio_config":

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.end_headers()

            cfg = read_e32_config()

            if cfg:

                self.wfile.write(json.dumps({"status": "ok", "config": cfg}).encode('utf-8'))

            else:

                self.wfile.write(json.dumps({"status": "error", "message": "No response from E32 module"}).encode('utf-8'))

            

        else:

            super().do_GET()

 

    def do_POST(self):

        global SIMULATED_PACKET_LOSS, SIMULATED_TX_DELAY

        

        content_length_str = self.headers.get('Content-Length')

        content_length = int(content_length_str) if content_length_str is not None else 0

        post_data = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else ""

        

        from urllib.parse import parse_qs

        parsed = parse_qs(post_data)

        

        if self.path == "/api/ping":

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.end_headers()

            

            result = run_ping_test()

            self.wfile.write(json.dumps(result).encode('utf-8'))

            

        elif self.path in ("/api/send", "/api/image"):

            raw_b64 = parsed.get('data', [''])[0]

            delay_ms = int(parsed.get('delay', [SIMULATED_TX_DELAY])[0])

            

            p_type = 0x04 if self.path == "/api/image" else 0x00

            

            if raw_b64:

                threading.Thread(

                    target=start_handshake_session, 

                    args=(p_type, raw_b64.encode('utf-8'), delay_ms), 

                    daemon=True

                ).start()

                

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "initiated"}).encode('utf-8'))

            

        elif self.path == "/api/config":

            loss = parsed.get('packet_loss', [None])[0]

            delay = parsed.get('tx_delay', [None])[0]

            air_rate = parsed.get('air_rate', [None])[0]

            channel = parsed.get('channel', [None])[0]

            tx_power = parsed.get('tx_power', [None])[0]

            

            if loss is not None:

                SIMULATED_PACKET_LOSS = float(loss)

            if delay is not None:

                SIMULATED_TX_DELAY = int(delay)

                

            rate_val = float(air_rate) if air_rate is not None else None

            chan_val = int(channel) if channel is not None else None

            power_val = int(tx_power) if tx_power is not None else None

            

            success = True

            if rate_val is not None or chan_val is not None or power_val is not None:

                success = configure_e32(rate=rate_val, channel=chan_val, power=power_val, local_only=False)

                

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "updated" if success else "failed"}).encode('utf-8'))

            

        elif self.path == "/api/wifi/connect":

            ssid = parsed.get('ssid', [''])[0]

            password = parsed.get('password', [''])[0]

            

            result = connect_wifi(ssid, password)

            

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.end_headers()

            self.wfile.write(json.dumps(result).encode('utf-8'))



        elif self.path == "/api/battery/reset":

            battery_gauge.reset_charge()

            self.send_response(200)

            self.send_header("Content-Type", "application/json")

            self.end_headers()

            self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))

 

def poll_radio_config_startup():

    """Poll radio config on startup. Print error if no response, but continue."""

    print("[STARTUP] Polling radio module configuration...")

    cfg = read_e32_config()

    if cfg:

        print(f"[STARTUP] Radio reports: Rate={cfg['rate']}k Chan={cfg['channel']} Power={cfg['power']}")

    else:

        print("[STARTUP] WARNING: Could not read radio config! Check E32 module connection.")



if __name__ == "__main__":

                             

    poll_radio_config_startup()

    

                                                              

    configure_e32(0.3, 15, 0)

    

    threading.Thread(target=background_radio_rx_engine, daemon=True).start()

    threading.Thread(target=rx_session_cleaner_thread, daemon=True).start()

    

                                                                 

    threading.Thread(target=base_heartbeat_loop, daemon=True).start()

    

    import signal

    def sig_handler(signum, frame):

        print(f"[SHUTDOWN] Signal {signum} received. Saving battery state...")

        battery_gauge.running = False

        battery_gauge.save_state(to_disk=True)

        sys.exit(0)

    signal.signal(signal.SIGTERM, sig_handler)

    signal.signal(signal.SIGINT, sig_handler)

    

    print("Base station web-app gateway online at http://localhost:8080")

    try:

        HTTPServer(('', 8080), CustomFrontendAPI).serve_forever()

    except KeyboardInterrupt:

        print("\nGateway shutting down.")

    finally:

        print("[SHUTDOWN] Cleanup. Saving battery state...")

        battery_gauge.running = False

        battery_gauge.save_state(to_disk=True)
