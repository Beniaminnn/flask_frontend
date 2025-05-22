from flask import Flask, jsonify, request, make_response
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import pyaudio
import numpy as np
import threading
import queue
import psutil
import subprocess
import serial
import json
import time
from collections import deque

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*")

# Configurare audio
FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 44100
CHUNK = 1024
LOOPBACK_DEVICE_INDEX = 1
IQAUDIO_DEVICE_INDEX = 2

# Configurare port serial pentru senzori
SERIAL_PORT = '/dev/ttyUSB0'
BAUD_RATE = 115200
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)

# Parametri globali
params = {
    'delay_l': 5,
    'delay_r': 5,
    'running': False
}

# Variabile pentru stocarea datelor senzorilor
sensor_data = {"Dreapta": "Eroare", "StÃ¢nga": "Eroare", "FaÈ›Äƒ": "Eroare", "Spate": "Eroare"}
buffer = ""

# Variabile pentru detectarea persoanelor È™i poziÈ›ia boxei
MAX_DISTANCE = 400  # DistanÈ›a maximÄƒ a senzorilor (cm)
ROOM_WIDTH = 400    # LÄƒÈ›imea camerei (cm)
ROOM_HEIGHT = 400   # Lungimea camerei (cm)
SPEAKER_POSITION = [ROOM_WIDTH / 2, ROOM_HEIGHT / 2]  # PoziÈ›ie iniÈ›ialÄƒ (se va actualiza)
SPEAKER_POSITION_LOCK = threading.Lock()
SPEAKER_WIDTH = 50  # LÄƒÈ›imea boxei (cm), pentru calculul delay-urilor

HISTORY_LENGTH = 5  # NumÄƒrul de citiri pentru a detecta stabilitate
TOLERANCE = 5.0     # ToleranÈ›Äƒ pentru fluctuaÈ›ii (cm)
MIN_CHANGE = 20.0   # Schimbare minimÄƒ pentru a detecta o persoanÄƒ (cm)

# Istoricul citirilor senzorilor
sensor_history = {
    "Dreapta": deque(maxlen=HISTORY_LENGTH),
    "StÃ¢nga": deque(maxlen=HISTORY_LENGTH),
    "FaÈ›Äƒ": deque(maxlen=HISTORY_LENGTH),
    "Spate": deque(maxlen=HISTORY_LENGTH)
}

# Baseline-ul pentru fiecare senzor
sensor_baselines = {
    "Dreapta": MAX_DISTANCE,
    "StÃ¢nga": MAX_DISTANCE,
    "FaÈ›Äƒ": MAX_DISTANCE,
    "Spate": MAX_DISTANCE
}

# Lista cu poziÈ›iile persoanelor detectate (x, y)
people_positions = []

# Flag pentru a verifica dacÄƒ baseline-ul a fost stabilit
baseline_established = False

# Cozi pentru date audio È™i buffer pentru filtrare
audio_queue_in = queue.Queue()
audio_queue_out = queue.Queue()
audio_buffer_in = deque(maxlen=5)  # Buffer pentru medie mobilÄƒ
audio_buffer_out = deque(maxlen=5)  # Buffer pentru medie mobilÄƒ
processor = None
processor_lock = threading.Lock()
should_run = False

# Ultima actualizare a logurilor È™i a datelor senzorilor/persoanelor
last_sensor_update = 0
last_logs_update = 0
last_audio_update = 0

def calculate_speaker_position():
    """CalculeazÄƒ poziÈ›ia boxei pe baza datelor senzorilor."""
    global SPEAKER_POSITION
    with SPEAKER_POSITION_LOCK:
        distances = {}
        for direction in ["Dreapta", "StÃ¢nga", "FaÈ›Äƒ", "Spate"]:
            value = sensor_data[direction]
            distances[direction] = value if isinstance(value, (int, float)) else MAX_DISTANCE

        x = distances["StÃ¢nga"] if distances["StÃ¢nga"] != MAX_DISTANCE else ROOM_WIDTH - distances["Dreapta"]
        y = distances["FaÈ›Äƒ"] if distances["FaÈ›Äƒ"] != MAX_DISTANCE else ROOM_HEIGHT - distances["Spate"]

        x = max(0, min(ROOM_WIDTH, x))
        y = max(0, min(ROOM_HEIGHT, y))

        SPEAKER_POSITION[0] = x
        SPEAKER_POSITION[1] = y
        print(f"PoziÈ›ie boxÄƒ calculatÄƒ: ({x}, {y})")

def establish_baseline():
    """StabileÈ™te baseline-ul pentru fiecare senzor la pornire."""
    global sensor_baselines, baseline_established
    print("ÃŽncep stabilirea baseline-ului...")
    start_time = time.time()
    timeout = 10

    while time.time() - start_time < timeout:
        for direction in sensor_baselines.keys():
            history = list(sensor_history[direction])
            if len(history) < HISTORY_LENGTH:
                continue
            values = np.array(history[-HISTORY_LENGTH:])
            if np.all(np.abs(values - values[0]) <= TOLERANCE):
                sensor_baselines[direction] = values[0]
                print(f"Baseline stabilit pentru {direction}: {sensor_baselines[direction]} cm")
        if all(baseline != MAX_DISTANCE for baseline in sensor_baselines.values()):
            break
        time.sleep(0.2)

    for direction, baseline in sensor_baselines.items():
        if baseline == MAX_DISTANCE:
            print(f"Timeout: Folosesc valoarea maximÄƒ ca baseline pentru {direction}: {MAX_DISTANCE} cm")
            sensor_baselines[direction] = MAX_DISTANCE

    baseline_established = True
    print("Stabilirea baseline-ului s-a Ã®ncheiat.")

def detect_people():
    """DetecteazÄƒ persoanele bazÃ¢ndu-se pe schimbÄƒrile Ã®n distanÈ›e È™i stabilitate."""
    global people_positions, sensor_baselines

    people_positions.clear()

    distances = {}
    for direction in ["Dreapta", "StÃ¢nga", "FaÈ›Äƒ", "Spate"]:
        value = sensor_data[direction]
        distances[direction] = value if isinstance(value, (int, float)) else MAX_DISTANCE

    for direction, distance in distances.items():
        sensor_history[direction].append(distance)

    calculate_speaker_position()

    if not baseline_established:
        return

    for direction in ["Dreapta", "StÃ¢nga", "FaÈ›Äƒ", "Spate"]:
        history = list(sensor_history[direction])
        if len(history) < HISTORY_LENGTH:
            continue

        values = np.array(history[-HISTORY_LENGTH:])
        current_distance = values[-1]
        baseline = sensor_baselines[direction]

        if len(values) >= 2:
            diff = baseline - current_distance
            if diff > MIN_CHANGE and np.all(np.abs(values[-2:] - current_distance) <= TOLERANCE):
                if direction == "Dreapta":
                    x = ROOM_WIDTH - current_distance
                    y = ROOM_HEIGHT / 2
                elif direction == "StÃ¢nga":
                    x = current_distance
                    y = ROOM_HEIGHT / 2
                elif direction == "FaÈ›Äƒ":
                    x = ROOM_WIDTH / 2
                    y = current_distance
                elif direction == "Spate":
                    x = ROOM_WIDTH / 2
                    y = ROOM_HEIGHT - current_distance
                people_positions.append((x, y))
                print(f"PersoanÄƒ detectatÄƒ la {direction}, poziÈ›ie: ({x}, {y})")

    if len(people_positions) > 1:
        avg_x = np.mean([pos[0] for pos in people_positions])
        avg_y = np.mean([pos[1] for pos in people_positions])
        people_positions = [(avg_x, avg_y)]

def adjust_delay_based_on_position():
    """AjusteazÄƒ delay_l È™i delay_r bazÃ¢ndu-se pe poziÈ›ia celei mai apropiate persoane."""
    global params
    with SPEAKER_POSITION_LOCK:
        speaker_pos = (SPEAKER_POSITION[0], SPEAKER_POSITION[1])
    if not people_positions:
        params['delay_l'] = 0
        params['delay_r'] = 0
        return

    closest_person = min(people_positions, key=lambda pos: ((pos[0] - speaker_pos[0])**2 + (pos[1] - speaker_pos[1])**2)**0.5)
    person_x, person_y = closest_person

    speaker_left_x = speaker_pos[0] - SPEAKER_WIDTH / 2
    speaker_right_x = speaker_pos[0] + SPEAKER_WIDTH / 2
    speaker_y = speaker_pos[1]

    dist_to_left = ((person_x - speaker_left_x)**2 + (person_y - speaker_y)**2)**0.5
    dist_to_right = ((person_x - speaker_right_x)**2 + (person_y - speaker_y)**2)**0.5

    time_diff_ms = (dist_to_right - dist_to_left) / 34.3
    max_delay = 50

    if time_diff_ms > 0:
        params['delay_r'] = min(int(abs(time_diff_ms)), max_delay)
        params['delay_l'] = 0
    else:
        params['delay_l'] = min(int(abs(time_diff_ms)), max_delay)
        params['delay_r'] = 0

    print(f"Delay ajustat: delay_l={params['delay_l']}, delay_r={params['delay_r']}")

def read_serial():
    global sensor_data, buffer, ser
    while True:
        try:
            if not ser.is_open:
                try:
                    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
                    print("Reconectat la portul serial")
                except serial.SerialException as e:
                    print(f"Eroare la reconectare: {e}")
                    time.sleep(5)
                    continue
            data = ser.read(ser.in_waiting or 1).decode('utf-8', errors='replace')
            if data:
                buffer += data
                while '{' in buffer and '}' in buffer:
                    start = buffer.find('{')
                    end = buffer.find('}', start) + 1
                    if end > 0:
                        json_str = buffer[start:end]
                        try:
                            data = json.loads(json_str)
                            expected_keys = {"Dreapta", "StÃ¢nga", "FaÈ›Äƒ", "Spate"}
                            if all(key in data for key in expected_keys):
                                sensor_data = data
                                print(f"Date senzor actualizate: {sensor_data}")
                                detect_people()
                                adjust_delay_based_on_position()
                            else:
                                print(f"StructurÄƒ JSON invalidÄƒ: {json_str}")
                        except json.JSONDecodeError as e:
                            print(f"Eroare la parsarea JSON: {e}, Linie: {json_str}")
                        buffer = buffer[end:]
                    else:
                        break
        except serial.SerialException as e:
            print(f"Eroare serial: {e}")
            ser.close()
            time.sleep(5)
        except Exception as e:
            print(f"Eroare neaÈ™teptatÄƒ: {e}")
        time.sleep(0.01)

# Pornim citirea serialÄƒ Ã®ntr-un thread separat
serial_thread = threading.Thread(target=read_serial, daemon=True)
serial_thread.start()

# RuleazÄƒ stabilirea baseline-ului Ã®ntr-un thread separat
baseline_thread = threading.Thread(target=establish_baseline, daemon=True)
baseline_thread.start()

class AudioProcessor:
    def __init__(self):
        self.p = pyaudio.PyAudio()
        print("Dispozitive disponibile:")
        for i in range(self.p.get_device_count()):
            print(self.p.get_device_info_by_index(i))
        
        self.stream_in = self.p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True,
                                     input_device_index=LOOPBACK_DEVICE_INDEX, frames_per_buffer=CHUNK)
        self.stream_out = self.p.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True,
                                      output_device_index=IQAUDIO_DEVICE_INDEX, frames_per_buffer=CHUNK)
        max_delay = max(params['delay_l'], params['delay_r'])
        self.delay_buffer = np.zeros((2, max_delay + CHUNK))
        self.delay_index = 0

    def apply_noise_filter(self, data):
        """AplicÄƒ filtrare de zgomot È™i medie mobilÄƒ pe datele audio."""
        # Prag de zgomot (Â±2)
        noise_threshold = 2
        filtered_data = np.array(data, dtype=np.float32)

        # AplicÄƒ prag pentru a elimina zgomotul de amplitudine micÄƒ
        filtered_data = np.where(np.abs(filtered_data) > noise_threshold, filtered_data, 0)

        # Medie mobilÄƒ pe o fereastrÄƒ de 5 eÈ™antioane
        window_size = 5
        if len(filtered_data) >= window_size:
            smoothed = np.convolve(filtered_data, np.ones(window_size) / window_size, mode='same')
            return smoothed.astype(np.int16).tolist()
        return filtered_data.astype(np.int16).tolist()

    def process_audio(self, data):
        audio_array = np.frombuffer(data, dtype=np.int16).astype(np.float32)
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

        left = 0.8 * left + 0.2 * delayed_left
        right = 0.8 * right + 0.2 * delayed_right

        self.delay_index = (self.delay_index + chunk_size) % len(self.delay_buffer[0])

        output = np.zeros_like(audio_array)
        output[::2] = np.clip(left, -32768, 32767)
        output[1::2] = np.clip(right, -32768, 32767)
        return output.astype(np.int16).tobytes()

    def run(self):
        global should_run, audio_buffer_in, audio_buffer_out, last_audio_update
        print(f"RedirecÈ›ionare sunet de la hw:0,1 la hw:3,0 la {RATE} Hz...")
        while True:
            with processor_lock:
                if not should_run:
                    break
                try:
                    data_in = self.stream_in.read(CHUNK, exception_on_overflow=False)
                    audio_array = np.frombuffer(data_in, dtype=np.int16)
                    data_out = self.process_audio(data_in)
                    self.stream_out.write(data_out)
                    audio_queue_in.put(data_in)
                    audio_queue_out.put(data_out)

                    # AdaugÄƒ datele brute Ã®n buffer pentru filtrare
                    audio_buffer_in.append(list(audio_array[::2]))  # Doar canalul stÃ¢nga pentru simplitate
                    audio_buffer_out.append(list(np.frombuffer(data_out, dtype=np.int16)[::2]))

                    current_time = time.time()
                    if current_time - last_audio_update >= 0.06:  # Refresh rate de ~60ms (16 Hz)
                        # AplicÄƒ filtrarea de zgomot
                        filtered_input = self.apply_noise_filter([item for sublist in audio_buffer_in for item in sublist])
                        filtered_output = self.apply_noise_filter([item for sublist in audio_buffer_out for item in sublist])
                        socketio.emit('data_input', {'input': filtered_input})
                        socketio.emit('data_output', {'output': filtered_output})
                        last_audio_update = current_time
                        audio_buffer_in.clear()  # ReseteazÄƒ buffer-ul dupÄƒ trimitere
                        audio_buffer_out.clear()

                except OSError as e:
                    print(f"Eroare la citire: {e}, continuÄƒm...")
                    continue
        print("Thread audio oprit.")

    def cleanup(self):
        print("ÃŽncep cleanup...")
        if self.stream_in.is_active():
            self.stream_in.stop_stream()
        self.stream_in.close()
        if self.stream_out.is_active():
            self.stream_out.stop_stream()
        self.stream_out.close()
        self.p.terminate()
        print("Cleanup finalizat.")

def start_processing():
    global processor, should_run
    with processor_lock:
        if processor is not None:
            should_run = False
            processor.cleanup()
            processor = None
        processor = AudioProcessor()
        should_run = True
        print("Procesare audio pornitÄƒ!")
        threading.Thread(target=processor.run, daemon=True).start()

# Thread pentru trimiterea datelor prin WebSocket cu frecvenÈ›e diferite
def websocket_data_thread():
    global last_sensor_update, last_logs_update
    while True:
        if params['running']:
            current_time = time.time()

            # ActualizÄƒri la 200ms pentru senzori, persoane È™i poziÈ›ia boxei
            if current_time - last_sensor_update >= 0.2:
                if sensor_data and any(isinstance(v, (int, float)) for v in sensor_data.values()):
                    socketio.emit('sensors', sensor_data)
                socketio.emit('people', {
                    "count": len(people_positions),
                    "positions": [{"x": pos[0], "y": pos[1]} for pos in people_positions]
                })
                with SPEAKER_POSITION_LOCK:
                    socketio.emit('speaker_position', {'x': SPEAKER_POSITION[0], 'y': SPEAKER_POSITION[1]})
                last_sensor_update = current_time

            # ActualizÄƒri la 1 secundÄƒ pentru loguri
            if current_time - last_logs_update >= 1.0:
                input_max = 0
                output_max = 0
                data_in = None
                data_out = None
                while not audio_queue_in.empty():
                    data_in = audio_queue_in.get()
                while not audio_queue_out.empty():
                    data_out = audio_queue_out.get()

                if data_in:
                    audio_array_in = np.frombuffer(data_in, dtype=np.int16)
                    input_max = int(np.max(np.abs(audio_array_in)))
                if data_out:
                    audio_array_out = np.frombuffer(data_out, dtype=np.int16)
                    output_max = int(np.max(np.abs(audio_array_out)))

                try:
                    temp = subprocess.check_output(['vcgencmd', 'measure_temp']).decode().strip()
                    temperature = temp.replace('temp=', '')
                except:
                    temperature = "N/A"

                cpu_load = psutil.cpu_percent(interval=1)

                try:
                    wifi_info = subprocess.check_output(['iwconfig', 'wlan0']).decode()
                    ssid = [line for line in wifi_info.split('\n') if 'ESSID' in line][0].split('"')[1]
                    signal = [line for line in wifi_info.split('\n') if 'Signal level' in line][0].split('Signal level=')[1].split(' ')[0]
                except:
                    ssid = "N/A"
                    signal = "N/A"

                logs = {
                    'input_max_amplitude': input_max,
                    'output_max_amplitude': output_max,
                    'temperature': temperature,
                    'cpu_load': cpu_load,
                    'wifi_ssid': ssid,
                    'wifi_signal': signal
                }
                socketio.emit('logs', logs)
                last_logs_update = current_time

            # Trimite parametrii la fiecare 200ms
            socketio.emit('params', params)

        socketio.sleep(0.01)  # Ciclul principal al thread-ului

# Pornim thread-ul WebSocket
socketio.start_background_task(websocket_data_thread)

@app.route('/toggle', methods=['POST'])
def toggle_processing():
    print("Cerere POST /toggle primitÄƒ!")
    print(f"ÃŽnainte de toggle: running = {params['running']}")
    params['running'] = not params['running']
    print(f"DupÄƒ toggle: running = {params['running']}")
    if params['running']:
        start_processing()
    else:
        global should_run
        with processor_lock:
            should_run = False
            while not audio_queue_in.empty():
                audio_queue_in.get()
            while not audio_queue_out.empty():
                audio_queue_out.get()
            print("Cozile audio au fost golite.")
        if processor is not None:
            print("Oprire procesare prin toggle...")
    return jsonify({'status': 'success', 'running': params['running']})

@socketio.on('connect')
def handle_connect():
    print("Client conectat!")

@socketio.on('disconnect')
def handle_disconnect():
    print("Client deconectat!")

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5500, debug=True)
