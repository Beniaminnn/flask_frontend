import socket
from flask import Flask, jsonify, request
from flask_socketio import SocketIO
from flask_cors import CORS
import pyaudio
import numpy as np
import threading
import queue
import serial
import serial.tools.list_ports
import json
import time
from collections import deque
import logging
import atexit
import psutil
import subprocess
import sys

# Configurare logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# Configurare Flask si SocketIO
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', ping_timeout=20, ping_interval=5, reconnection=True)

# Configurare audio
FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 44100
CHUNK = 512
LOOPBACK_DEVICE_INDEX = None
IQAUDIO_DEVICE_INDEX = None
p_proc = None

# Configurare port serial
SERIAL_PORT = None
BAUD_RATE = 115200
ser = None

# Parametri globali
params = {
    'delay_l': 0,
    'delay_r': 0,
    'running': False
}

sensor_data = {"distances": [-1.0] * 4, "positions": [], "velocities": [], "confidence": [], "timestamp": 0}
buffer = ""

MAX_DISTANCE = 400
ROOM_WIDTH = 400
ROOM_HEIGHT = 400
SPEAKER_POSITION = [ROOM_WIDTH / 2, ROOM_HEIGHT / 2]
SPEAKER_POSITION_LOCK = threading.Lock()
SPEAKER_WIDTH = 50

sensor_history = [deque(maxlen=10) for _ in range(4)]
people_positions = []

AUDIO_QUEUE_IN = queue.Queue(maxsize=10)
AUDIO_BUFFER_IN = deque(maxlen=5)
AUDIO_BUFFER_OUT = deque(maxlen=5)
processor = None
PROCESSOR_LOCK = threading.Lock()
SHOULD_RUN = False

LAST_SENSOR_UPDATE = 0
LAST_LOGS_UPDATE = 0
LAST_AUDIO_UPDATE = 0

SENSOR_LOGS = []
PEOPLE_LOGS = []
AUDIO_LOGS = []
GENERAL_LOGS = []

def log_debug(category, message):
    timestamp = time.strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {category.upper()}: {message}"
    if category == "sensors":
        SENSOR_LOGS.append(log_entry)
        if len(SENSOR_LOGS) > 100: SENSOR_LOGS.pop(0)
    elif category == "people":
        PEOPLE_LOGS.append(log_entry)
        if len(PEOPLE_LOGS) > 100: PEOPLE_LOGS.pop(0)
    elif category == "audio":
        AUDIO_LOGS.append(log_entry)
        if len(AUDIO_LOGS) > 100: AUDIO_LOGS.pop(0)
    else:
        GENERAL_LOGS.append(log_entry)
        if len(GENERAL_LOGS) > 100: GENERAL_LOGS.pop(0)
    log.debug(log_entry)

def find_serial_port():
    ports = serial.tools.list_ports.comports()
    log_debug("general", f"Porturi disponibile: {[port.device for port in ports]}")
    for port in ports:
        if "USB" in port.device or "ACM" in port.device:
            log_debug("sensors", f"Port serial gasit: {port.device}")
            return port.device
    log_debug("sensors", "Niciun port serial USB gasit, folosesc fallback /dev/ttyUSB0")
    return '/dev/ttyUSB0'

def calculate_speaker_position():
    global SPEAKER_POSITION
    with SPEAKER_POSITION_LOCK:
        distances = sensor_data["distances"]
        if any(d != -1.0 for d in distances):
            x = distances[1] if distances[1] != -1.0 else ROOM_WIDTH - distances[0]
            y = distances[2] if distances[2] != -1.0 else ROOM_HEIGHT - distances[3]
            x = max(0, min(ROOM_WIDTH, x))
            y = max(0, min(ROOM_HEIGHT, y))
            SPEAKER_POSITION = [x, y]
    log_debug("people", f"Pozitia difuzorului: x={x:.1f} cm, y={y:.1f} cm, distances={distances}")

def detect_people():
    global people_positions
    people_positions.clear()

    distances = sensor_data["distances"]
    positions = sensor_data["positions"]

    for i in range(4):
        sensor_history[i].append(distances[i] if distances[i] != -1.0 else MAX_DISTANCE)

    if positions and len(positions) >= 2:
        for i in range(0, len(positions), 2):
            if i + 1 < len(positions):
                x, y = positions[i], positions[i + 1]
                people_positions.append([max(0, min(ROOM_WIDTH, x)), max(0, min(ROOM_HEIGHT, y))])
        log_debug("people", f"Persoane detectate din ESP32: {len(people_positions)}")
    else:
        log_debug("people", "Nicio pozitie primita de la ESP32, folosesc distanțe brute")
        for i in range(4):
            current_distance = distances[i]
            if current_distance > 0 and current_distance < MAX_DISTANCE:
                if i == 0: people_positions.append([ROOM_WIDTH - current_distance, ROOM_HEIGHT / 2])
                elif i == 1: people_positions.append([current_distance, ROOM_HEIGHT / 2])
                elif i == 2: people_positions.append([ROOM_WIDTH / 2, current_distance])
                elif i == 3: people_positions.append([ROOM_WIDTH / 2, ROOM_HEIGHT - current_distance])

    if people_positions:
        avg_x = np.mean([pos[0] for pos in people_positions])
        avg_y = np.mean([pos[1] for pos in people_positions])
        log_debug("people", f"Persoana detectata, pozitie medie: ({avg_x:.1f}, {avg_y:.1f}) cm")

def adjust_time_alignment():
    global params
    with SPEAKER_POSITION_LOCK:
        speaker_pos = SPEAKER_POSITION
    if not people_positions:
        params['delay_l'] = 0
        params['delay_r'] = 0
        log_debug("people", "Nicio persoana detectata, parametri resetati")
        return

    closest_person = min(people_positions, key=lambda pos: ((pos[0] - speaker_pos[0])**2 + (pos[1] - speaker_pos[1])**2)**0.5)
    person_x, person_y = closest_person
    dist_cm = ((person_x - speaker_pos[0])**2 + (person_y - speaker_pos[1])**2)**0.5

    delay_ms = dist_cm / 34.3
    max_delay_ms = 50
    delay_samples = int(min(delay_ms, max_delay_ms) * RATE / 1000)

    params['delay_l'] = delay_samples
    params['delay_r'] = delay_samples
    log_debug("people", f"Ajustare delay bazat pe distanta: delay_l={params['delay_l']} samples, delay_r={params['delay_r']} samples, dist={dist_cm:.1f} cm")

def read_serial():
    global sensor_data, buffer, ser
    SERIAL_PORT = find_serial_port()
    while True:
        try:
            if ser is None or not ser.is_open:
                try:
                    ser = serial.Serial(port=SERIAL_PORT, baudrate=BAUD_RATE, timeout=1, write_timeout=1)
                    log_debug("sensors", f"Conectat la portul serial: {SERIAL_PORT}")
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                except serial.SerialException as e:
                    log_debug("sensors", f"Eroare la conectare: {e}")
                    time.sleep(5)
                    continue
            data = ser.read(ser.in_waiting or 1).decode('utf-8', errors='ignore').strip()
            if data:
                buffer += data
                while '{' in buffer:
                    start = buffer.find('{')
                    end = buffer.find('}', start) + 1
                    if end <= start:
                        next_start = buffer.find('{', start + 1)
                        if next_start == -1:
                            break
                        end = next_start
                    json_str = buffer[start:end].strip()
                    if not json_str.endswith('}'):
                        log_debug("sensors", f"JSON incomplet detectat: {json_str}")
                        buffer = buffer[end:]
                        continue
                    try:
                        data_dict = json.loads(json_str)
                        sensor_data["distances"] = [float(d) if d != 'eroare' else -1.0 for d in data_dict.get("d", [-1.0] * 4)]
                        sensor_data["positions"] = [float(x) for pair in zip(data_dict.get("p", [])[::2], data_dict.get("p", [])[1::2]) for x in pair] if data_dict.get("p") else []
                        sensor_data["velocities"] = [float(v) for pair in zip(data_dict.get("v", [])[::2], data_dict.get("v", [])[1::2]) for v in pair] if data_dict.get("v") else []
                        sensor_data["confidence"] = data_dict.get("f", [0.0])
                        sensor_data["timestamp"] = data_dict.get("t", 0)
                        log_debug("sensors", f"Date senzor primite: {sensor_data}")
                        detect_people()
                        adjust_time_alignment()
                    except json.JSONDecodeError as e:
                        log_debug("sensors", f"Eroare JSON: {e}, linie: {json_str}")
                    except Exception as e:
                        log_debug("sensors", f"Eroare neasteptata la parsare JSON: {e}, linie: {json_str}")
                    buffer = buffer[end:].strip()
            else:
                if ser.in_waiting == 0 and buffer and '{' not in buffer:
                    buffer = ""
                elif ser.in_waiting == 0:
                    log_debug("sensors", "Niciun date disponibile de la serial, verificare conexiune...")
                    time.sleep(0.1)
        except serial.SerialException as e:
            log_debug("sensors", f"Eroare serial: {e}")
            if ser and ser.is_open:
                ser.close()
            time.sleep(5)
            continue
        time.sleep(0.01)

# Funcții audio (neschimbate)
def find_audio_devices(p):
    loopback_idx = None
    output_idx = None
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        log_debug("audio", f"Device {i}: Name={info['name']}, Input={info['maxInputChannels']}, Output={info['maxOutputChannels']}")
        if 'Loopback' in info['name'] and info['maxInputChannels'] > 0:
            loopback_idx = i
        elif 'IQAUDIO' in info['name'] and info['maxOutputChannels'] > 0:
            output_idx = i
        elif info['maxInputChannels'] > 0 and loopback_idx is None:
            loopback_idx = i
        elif info['maxOutputChannels'] > 0 and output_idx is None:
            output_idx = i
    if loopback_idx is None or output_idx is None:
        log_debug("audio", "Dispozitive loopback sau output lipsa!")
    return loopback_idx, output_idx

class AudioProcessor:
    def __init__(self, p):
        self.p = p
        self.running = False
        self.audio_thread = None
        global LOOPBACK_DEVICE_INDEX, IQAUDIO_DEVICE_INDEX
        LOOPBACK_DEVICE_INDEX, IQAUDIO_DEVICE_INDEX = find_audio_devices(self.p)
        if LOOPBACK_DEVICE_INDEX is None or IQAUDIO_DEVICE_INDEX is None:
            log_debug("audio", "Dispozitive loopback sau output lipsa!")
            self.p.terminate()
            raise ValueError("Dispozitive audio necesare lipsesc")
        self.stream_in = None
        self.stream_out = None
        self.initialize_streams()
        max_delay = 2205
        self.delay_buffer = np.zeros((2, max_delay + CHUNK))
        self.delay_index = 0

    def initialize_streams(self):
        try:
            if self.stream_in:
                if self.stream_in.is_active():
                    self.stream_in.stop_stream()
                self.stream_in.close()
                self.stream_in = None
            if self.stream_out:
                if self.stream_out.is_active():
                    self.stream_out.stop_stream()
                self.stream_out.close()
                self.stream_out = None
            self.stream_in = self.p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                input_device_index=LOOPBACK_DEVICE_INDEX,
                frames_per_buffer=CHUNK,
                start=False
            )
            self.stream_out = self.p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                output=True,
                output_device_index=IQAUDIO_DEVICE_INDEX,
                frames_per_buffer=CHUNK,
                start=False
            )
            self.stream_in.start_stream()
            self.stream_out.start_stream()
            log_debug("audio", "Stream-uri audio pornite")
        except Exception as e:
            log_debug("audio", f"Eroare la initializarea stream-urilor: {e}")
            self.cleanup()
            raise

    def process_binaural_audio(self, data):
        global params
        audio_array = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        if len(audio_array) < CHUNK * CHANNELS:
            log_debug("audio", "Date audio incomplete, returnez nemodificate")
            return data

        left = audio_array[::2].copy()
        right = audio_array[1::2].copy()
        chunk_size = len(left)

        start_idx = self.delay_index
        end_idx = start_idx + chunk_size
        if end_idx > len(self.delay_buffer[0]):
            first_part = len(self.delay_buffer[0]) - start_idx
            self.delay_buffer[0, start_idx:] = left[:first_part]
            self.delay_buffer[1, start_idx:] = right[:first_part]
            remaining = chunk_size - first_part
            self.delay_buffer[0, :remaining] = left[first_part:]
            self.delay_buffer[1, :remaining] = right[first_part:]
        else:
            self.delay_buffer[0, start_idx:end_idx] = left
            self.delay_buffer[1, start_idx:end_idx] = right

        delay_idx_l = (start_idx - params['delay_l']) % len(self.delay_buffer[0])
        delay_idx_r = (start_idx - params['delay_r']) % len(self.delay_buffer[0])

        delayed_left = np.zeros(chunk_size, dtype=np.float32)
        delayed_right = np.zeros(chunk_size, dtype=np.float32)

        for i in range(chunk_size):
            idx_l = (delay_idx_l + i) % len(self.delay_buffer[0])
            idx_r = (delay_idx_r + i) % len(self.delay_buffer[0])
            delayed_left[i] = self.delay_buffer[0, idx_l]
            delayed_right[i] = self.delay_buffer[1, idx_r]

        left = delayed_left
        right = delayed_right

        self.delay_index = (self.delay_index + chunk_size) % len(self.delay_buffer[0])

        output = np.zeros_like(audio_array)
        output[::2] = np.clip(left, -32767, 32767)
        output[1::2] = np.clip(right, -32767, 32767)
        log_debug("audio", f"Procesare audio: delay_l={params['delay_l']} samples, delay_r={params['delay_r']} samples")
        return output.astype(np.int16).tobytes()

    def cleanup(self):
        log_debug("audio", "Incep cleanup AudioProcessor...")
        self.running = False
        if self.audio_thread and self.audio_thread.is_alive():
            log_debug("audio", "Astept oprirea thread-ului audio...")
            self.audio_thread.join(timeout=2.0)
            if self.audio_thread.is_alive():
                log_debug("audio", "Thread-ul audio nu s-a oprit in timp util")
        try:
            if hasattr(self, 'stream_in') and self.stream_in:
                if self.stream_in.is_active():
                    self.stream_in.stop_stream()
                self.stream_in.close()
                self.stream_in = None
                log_debug("audio", "Stream input inchis")
        except Exception as e:
            log_debug("audio", f"Eroare la inchiderea stream_in: {e}")
        try:
            if hasattr(self, 'stream_out') and self.stream_out:
                if self.stream_out.is_active():
                    self.stream_out.stop_stream()
                self.stream_out.close()
                self.stream_out = None
                log_debug("audio", "Stream output inchis")
        except Exception as e:
            log_debug("audio", f"Eroare la inchiderea stream_out: {e}")
        time.sleep(0.1)
        log_debug("audio", "Cleanup AudioProcessor complet")

    def start(self):
        if not self.running:
            self.running = True
            self.audio_thread = threading.Thread(target=self.run, daemon=True)
            self.audio_thread.start()
            log_debug("audio", "Thread audio pornit")

    def stop(self):
        if self.running:
            log_debug("audio", "Opresc thread-ul audio...")
            self.running = False
            if self.audio_thread and self.audio_thread.is_alive():
                self.audio_thread.join(timeout=2.0)

    def run(self):
        global SHOULD_RUN, LAST_AUDIO_UPDATE
        log_debug("audio", f"Rutare sunet de la hw:{LOOPBACK_DEVICE_INDEX} la hw:{IQAUDIO_DEVICE_INDEX}")
        while self.running and SHOULD_RUN:
            try:
                if not self.stream_in or not self.stream_in.is_active():
                    log_debug("audio", "Stream input inactiv, reinitializez")
                    self.initialize_streams()
                    continue
                data_in = self.stream_in.read(CHUNK, exception_on_overflow=False)
                if not self.running or not SHOULD_RUN:
                    break
                data_out = self.process_binaural_audio(data_in)
                if not self.stream_out or not self.stream_out.is_active():
                    log_debug("audio", "Stream output inactiv, reinitializez")
                    self.initialize_streams()
                    continue
                self.stream_out.write(data_out)
                if time.time() - LAST_AUDIO_UPDATE >= 0.1:
                    audio_array_in = np.frombuffer(data_in, dtype=np.int16)
                    audio_array_out = np.frombuffer(data_out, dtype=np.int16)
                    socketio.emit('data_input', {'input': audio_array_in.tolist(), 'max_amplitude': int(np.max(np.abs(audio_array_in)))})
                    socketio.emit('data_output', {'output': audio_array_out.tolist(), 'max_amplitude': int(np.max(np.abs(audio_array_out))), 'anomalies': []})
                    LAST_AUDIO_UPDATE = time.time()
            except OSError as e:
                if self.running and SHOULD_RUN:
                    log_debug("audio", f"Eroare la citire: {e}, reinitializez")
                    try:
                        self.initialize_streams()
                    except Exception as init_error:
                        log_debug("audio", f"Eroare la reinitializare: {init_error}")
                        time.sleep(0.1)
                continue
            except Exception as e:
                if self.running and SHOULD_RUN:
                    log_debug("audio", f"Eroare neasteptata: {e}")
                continue
        log_debug("audio", "Thread audio oprit complet.")

def start_processing():
    global processor, SHOULD_RUN, p_proc
    with PROCESSOR_LOCK:
        if processor is not None:
            log_debug("general", "Opresc procesorul existent...")
            SHOULD_RUN = False
            try:
                processor.stop()
                processor.cleanup()
            except Exception as e:
                log_debug("general", f"Eroare la cleanup: {e}")
            processor = None
        if p_proc:
            try:
                p_proc.terminate()
                log_debug("general", "PyAudio anterior terminat")
            except Exception as e:
                log_debug("general", f"Eroare la terminarea PyAudio: {e}")
            p_proc = None
        time.sleep(0.5)
        try:
            p_proc = pyaudio.PyAudio()
            processor = AudioProcessor(p_proc)
            SHOULD_RUN = True
            processor.start()
            log_debug("general", "Procesare audio pornita!")
        except Exception as e:
            log_debug("general", f"Eroare la pornirea procesarii: {e}")
            SHOULD_RUN = False
            processor = None
            if p_proc:
                try:
                    p_proc.terminate()
                except:
                    pass
                p_proc = None

def websocket_data_thread():
    global LAST_SENSOR_UPDATE, LAST_LOGS_UPDATE
    while True:
        if not params['running']:
            socketio.sleep(0.1)
            continue
        current_time = time.time()
        if current_time - LAST_SENSOR_UPDATE >= 0.1:
            if sensor_data and any(isinstance(v, (int, float)) and v != -1.0 for v in sensor_data["distances"]):
                socketio.emit('sensors', sensor_data)
            socketio.emit('people', {
                "count": len(people_positions),
                "positions": [{"x": pos[0], "y": pos[1]} for pos in people_positions]
            })
            with SPEAKER_POSITION_LOCK:
                socketio.emit('speaker_position', {'x': SPEAKER_POSITION[0], 'y': SPEAKER_POSITION[1]})
            LAST_SENSOR_UPDATE = current_time
        if current_time - LAST_LOGS_UPDATE >= 1.0:
            input_max = 0
            output_max = 0
            try:
                while not AUDIO_QUEUE_IN.empty():
                    data_in = AUDIO_QUEUE_IN.get_nowait()
                    if data_in:
                        audio_array_in = np.frombuffer(data_in, dtype=np.int16)
                        input_max = max(input_max, int(np.max(np.abs(audio_array_in))))
            except queue.Empty:
                pass
            try:
                temp = subprocess.check_output(['vcgencmd', 'measure_temp'], timeout=2).decode().strip()
                temperature = temp.replace('temp=', '')
            except:
                temperature = "N/A"
            cpu_load = psutil.cpu_percent(interval=0.1)
            try:
                wifi_info = subprocess.check_output(['iwconfig', 'wlan0'], timeout=2).decode()
                ssid = [line for line in wifi_info.split('\n') if 'ESSID' in line][0].split('"')[1]
                signal_line = [line for line in wifi_info.split('\n') if 'Signal level' in line][0]
                signal = signal_line.split('Signal level=')[1].split(' ')[0]
            except:
                ssid = "N/A"
                signal = "N/A"
            logs = {
                'input_max_amplitude': input_max,
                'output_max_amplitude': output_max,
                'temperature': temperature,
                'cpu_load': cpu_load,
                'wifi_ssid': ssid,
                'wifi_power': signal
            }
            socketio.emit('logs', logs)
            LAST_LOGS_UPDATE = current_time
        socketio.emit('params', params)
        socketio.sleep(0.01)

def watchdog():
    global serial_thread
    while True:
        if not serial_thread.is_alive():
            log_debug("general", "Serial thread oprit, repornesc...")
            serial_thread = threading.Thread(target=read_serial, daemon=True)
            serial_thread.start()
        time.sleep(5)

def cleanup():
    global processor, ser, p_proc, SHOULD_RUN
    log_debug("general", "Incep cleanup global...")
    with PROCESSOR_LOCK:
        SHOULD_RUN = False
    if processor:
        try:
            processor.stop()
            processor.cleanup()
        except Exception as e:
            log_debug("general", f"Eroare la cleanup procesor: {e}")
        processor = None
    if p_proc:
        try:
            p_proc.terminate()
            log_debug("general", "PyAudio procesare terminat")
        except Exception as e:
            log_debug("general", f"Eroare la terminarea p_proc: {e}")
        p_proc = None
    try:
        if ser and ser.is_open:
            ser.close()
            log_debug("general", "Port serial inchis")
    except Exception as e:
        log_debug("general", f"Eroare la inchiderea serial: {e}")

atexit.register(cleanup)

@app.route('/toggle', methods=['POST'])
def toggle_processing():
    global SHOULD_RUN, processor, p_proc
    log_debug("general", f"Inainte de toggle: running = {params['running']}")
    try:
        if params['running']:
            log_debug("general", "Oprim procesarea...")
            params['running'] = False
            with PROCESSOR_LOCK:
                SHOULD_RUN = False
                if processor is not None:
                    try:
                        processor.stop()
                        processor.cleanup()
                        log_debug("general", "Processor oprit si curatat")
                    except Exception as e:
                        log_debug("general", f"Eroare la oprirea procesorului: {e}")
                    processor = None
                if p_proc:
                    try:
                        p_proc.terminate()
                        log_debug("general", "PyAudio terminat")
                    except Exception as e:
                        log_debug("general", f"Eroare la terminarea p_proc: {e}")
                    p_proc = None
            time.sleep(1.0)
            log_debug("general", "Procesare oprit complet")
        else:
            log_debug("general", "Pornesc procesarea...")
            params['running'] = True
            start_processing()
        log_debug("general", f"Dupa toggle: running = {params['running']}")
        return jsonify({'status': 'success', 'running': params['running']})
    except Exception as e:
        log_debug("general", f"Eroare la toggle: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/logs/sensors', methods=['GET'])
def get_sensor_logs():
    return jsonify({'logs': SENSOR_LOGS})

@app.route('/logs/people', methods=['GET'])
def get_people_logs():
    return jsonify({'logs': PEOPLE_LOGS})

@app.route('/logs/audio', methods=['GET'])
def get_audio_logs():
    return jsonify({'logs': AUDIO_LOGS})

@app.route('/logs/general', methods=['GET'])
def get_general_logs():
    return jsonify({'logs': GENERAL_LOGS})

@socketio.on('connect')
def handle_connect():
    log_debug("general", "Client conectat!")
    socketio.emit('sensors', sensor_data)
    socketio.emit('people', {
        "count": len(people_positions),
        "positions": [{"x": pos[0], "y": pos[1]} for pos in people_positions]
    })
    with SPEAKER_POSITION_LOCK:
        socketio.emit('speaker_position', {'x': SPEAKER_POSITION[0], 'y': SPEAKER_POSITION[1]})
    socketio.emit('params', params)

@socketio.on('disconnect')
def handle_disconnect():
    log_debug("general", "Client deconectat!")

if __name__ == '__main__':
    log_debug("general", "Pornirea aplicatiei...")
    try:
        serial_thread = threading.Thread(target=read_serial, daemon=True)
        serial_thread.start()
        watchdog_thread = threading.Thread(target=watchdog, daemon=True)
        watchdog_thread.start()
        socketio.start_background_task(websocket_data_thread)
        log_debug("general", "Pornirea serverului Flask pe http://0.0.0.0:5500")
        socketio.run(app, host='0.0.0.0', port=5500, debug=True)
    except KeyboardInterrupt:
        log_debug("general", "Oprire prin Ctrl+C...")
        with PROCESSOR_LOCK:
            SHOULD_RUN = False
        cleanup()
        log_debug("general", "Aplicatie inchisa.")
    except Exception as e:
        log_debug("general", f"Eroare la pornirea aplicatiei: {e}")
        cleanup()
        sys.exit(1)
