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
ser = serial.Serial()

# Parametri globali
params = {
    'delay_l': 0,
    'delay_r': 0,
    'running': False
}

# Variabile pentru stocarea datelor senzorilor (index 0=Dreapta, 1=StÃ¢nga, 2=FaÈ›Äƒ, 3=Spate)
sensor_data = ["Eroare"] * 4  # Redus la 4 senzori
buffer = ""

# Parametri camerei
MAX_DISTANCE = 400  # DistanÈ›a maximÄƒ a senzorilor (cm)
ROOM_WIDTH = 400    # LÄƒÈ›imea camerei (cm)
ROOM_HEIGHT = 400   # Lungimea camerei (cm)
SPEAKER_POSITION = [ROOM_WIDTH / 2, ROOM_HEIGHT / 2]  # PoziÈ›ie iniÈ›ialÄƒ
SPEAKER_POSITION_LOCK = threading.Lock()
SPEAKER_WIDTH = 50  # LÄƒÈ›imea boxei (cm)

HISTORY_LENGTH = 5  # NumÄƒrul de citiri pentru a detecta stabilitate
TOLERANCE = 5.0     # ToleranÈ›Äƒ pentru fluctuaÈ›ii (cm)
MIN_CHANGE = 20.0   # Schimbare minimÄƒ pentru a detecta o persoanÄƒ

# Istoricul citirilor senzorilor
sensor_history = [deque(maxlen=HISTORY_LENGTH) for _ in range(4)]  # Doar pentru 4 senzori

# Baseline-ul pentru fiecare senzor
sensor_baselines = [MAX_DISTANCE] * 4

# Lista cu poziÈ›iile persoanelor detectate (x, y)
people_positions = []

# Flag pentru a verifica dacÄƒ baseline-ul a fost stabilit
baseline_established = False

# Cozi pentru date audio
audio_queue_in = queue.Queue(maxsize=10)
audio_queue_out = queue.Queue(maxsize=10)
audio_buffer_in = deque(maxlen=5)
audio_buffer_out = deque(maxlen=5)
processor = None
processor_lock = threading.Lock()
should_run = False

# Ultima actualizare a datelor
last_sensor_update = 0
last_logs_update = 0
last_audio_update = 0

# Liste globale pentru stocarea mesajelor de debug separate
sensor_logs = []
people_logs = []
audio_logs = []
general_logs = []

def log_debug(category, message):
    """AdaugÄƒ un mesaj de debug Ã®n lista corespunzÄƒtoare cu timestamp."""
    timestamp = time.strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    if category == "sensors":
        sensor_logs.append(log_entry)
        if len(sensor_logs) > 100:
            sensor_logs.pop(0)
    elif category == "people":
        people_logs.append(log_entry)
        if len(people_logs) > 100:
            people_logs.pop(0)
    elif category == "audio":
        audio_logs.append(log_entry)
        if len(audio_logs) > 100:
            audio_logs.pop(0)
    else:  # general
        general_logs.append(log_entry)
        if len(general_logs) > 100:
            general_logs.pop(0)

def calculate_speaker_position():
    """CalculeazÄƒ poziÈ›ia boxei pe baza datelor senzorilor."""
    global SPEAKER_POSITION
    with SPEAKER_POSITION_LOCK:
        distances = sensor_data[:4]
        x = distances[1] if distances[1] != -1.0 else ROOM_WIDTH - distances[0]
        y = distances[2] if distances[2] != -1.0 else ROOM_HEIGHT - distances[3]
        x = max(0, min(ROOM_WIDTH, x))
        y = max(0, min(ROOM_HEIGHT, y))
        SPEAKER_POSITION[0] = x
        SPEAKER_POSITION[1] = y
    log_debug("people", f"Calculate speaker position: x={x} cm, y={y} cm, distances={distances}")

def establish_baseline():
    """StabileÈ™te baseline-ul pentru fiecare senzor la pornire."""
    global sensor_baselines, baseline_established
    log_debug("general", "ÃŽncep stabilirea baseline-ului...")
    start_time = time.time()
    timeout = 10

    while time.time() - start_time < timeout:
        for i in range(4):
            history = list(sensor_history[i])
            if len(history) < HISTORY_LENGTH:
                continue
            values = np.array(history[-HISTORY_LENGTH:])
            if np.all(np.abs(values - values[0]) <= TOLERANCE):
                sensor_baselines[i] = values[0]
                log_debug("general", f"Baseline stabilit pentru senzor {i}: {sensor_baselines[i]} cm")
        if all(baseline != MAX_DISTANCE for baseline in sensor_baselines):
            break
        time.sleep(0.2)

    for i, baseline in enumerate(sensor_baselines):
        if baseline == MAX_DISTANCE:
            log_debug("general", f"Timeout: Folosesc valoarea maximÄƒ ca baseline pentru senzor {i}: {MAX_DISTANCE} cm")
            sensor_baselines[i] = MAX_DISTANCE

    baseline_established = True
    log_debug("general", "Stabilirea baseline-ului s-a Ã®ncheiat.")

def detect_people():
    """DetecteazÄƒ persoanele bazÃ¢ndu-se pe schimbÄƒrile Ã®n distanÈ›e È™i stabilitate."""
    global people_positions, sensor_baselines

    people_positions.clear()

    distances = sensor_data[:4]
    for i in range(4):
        sensor_history[i].append(distances[i])

    calculate_speaker_position()

    if not baseline_established:
        return

    for i in range(4):
        history = list(sensor_history[i])
        if len(history) < HISTORY_LENGTH:
            continue

        values = np.array(history[-HISTORY_LENGTH:])
        current_distance = values[-1]
        baseline = sensor_baselines[i]

        if len(values) >= 2:
            diff = baseline - current_distance
            if diff > MIN_CHANGE and np.all(np.abs(values[-2:] - current_distance) <= TOLERANCE):
                if i == 0:  # Dreapta
                    x = ROOM_WIDTH - current_distance
                    y = ROOM_HEIGHT / 2
                elif i == 1:  # StÃ¢nga
                    x = current_distance
                    y = ROOM_HEIGHT / 2
                elif i == 2:  # FaÈ›Äƒ
                    x = ROOM_WIDTH / 2
                    y = current_distance
                elif i == 3:  # Spate
                    x = ROOM_WIDTH / 2
                    y = ROOM_HEIGHT - current_distance
                people_positions.append((x, y))
                log_debug("people", f"PersoanÄƒ detectatÄƒ la senzor {i}, poziÈ›ie: ({x}, {y}) cm")

    if len(people_positions) > 1:
        avg_x = np.mean([pos[0] for pos in people_positions])
        avg_y = np.mean([pos[1] for pos in people_positions])
        people_positions = [(avg_x, avg_y)]
        log_debug("people", f"Mai multe persoane detectate, poziÈ›ie medie: ({avg_x}, {avg_y}) cm")

def adjust_time_alignment():
    """AjusteazÄƒ delay_l È™i delay_r bazÃ¢ndu-se pe poziÈ›ia utilizatorului È™i a difuzoarelor."""
    global params
    with SPEAKER_POSITION_LOCK:
        speaker_pos = (SPEAKER_POSITION[0], SPEAKER_POSITION[1])
    if not people_positions:
        params['delay_l'] = 0
        params['delay_r'] = 0
        log_debug("people", "Nicio persoanÄƒ detectatÄƒ, time alignment resetat: delay_l=0 ms, delay_r=0 ms")
        return

    closest_person = min(people_positions, key=lambda pos: ((pos[0] - speaker_pos[0])**2 + (pos[1] - speaker_pos[1])**2)**0.5)
    person_x, person_y = closest_person

    speaker_left_x = speaker_pos[0] - SPEAKER_WIDTH / 2
    speaker_right_x = speaker_pos[0] + SPEAKER_WIDTH / 2
    speaker_y = speaker_pos[1]

    dist_to_left = ((person_x - speaker_left_x)**2 + (person_y - speaker_y)**2)**0.5
    dist_to_right = ((person_x - speaker_right_x)**2 + (person_y - speaker_y)**2)**0.5

    time_diff_ms = ((dist_to_right - dist_to_left) / 34.3) * 1000
    min_delay = 1
    max_delay = 50

    if time_diff_ms > 0:
        params['delay_l'] = max(min_delay, min(int(abs(time_diff_ms)), max_delay))
        params['delay_r'] = min_delay
    else:
        params['delay_l'] = min_delay
        params['delay_r'] = max(min_delay, min(int(abs(time_diff_ms)), max_delay))

    log_debug("people", f"Adjust time alignment: delay_l={params['delay_l']} ms, delay_r={params['delay_r']} ms, person=({person_x}, {person_y}) cm, speaker=({speaker_pos[0]}, {speaker_pos[1]}) cm")

def read_serial():
    global sensor_data, buffer, ser
    while True:
        try:
            if not ser.is_open:
                try:
                    ser = serial.Serial(
                        port=SERIAL_PORT,
                        baudrate=BAUD_RATE,
                        timeout=1,
                        write_timeout=1,
                        bytesize=serial.EIGHTBITS,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                        xonxoff=False,
                        rtscts=False
                    )
                    log_debug("sensors", f"Date despre senzori: Reconectat la portul serial: {SERIAL_PORT}, baud: {BAUD_RATE}, 8N1")
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                except serial.SerialException as e:
                    log_debug("sensors", f"Date despre senzori: Eroare la reconectare: {e}")
                    time.sleep(5)
                    continue
            log_debug("sensors", f"Date despre senzori: Port deschis, bytes disponibile: {ser.in_waiting}")
            data = ser.read(ser.in_waiting or 1).decode('utf-8', errors='ignore').strip()
            if data:
                log_debug("sensors", f"Date despre senzori: Date brute citite: {repr(data)}")
                buffer += data
                log_debug("sensors", f"Date despre senzori: Buffer actual: {repr(buffer)}")
                while '[' in buffer and ']' in buffer:
                    start = buffer.find('[')
                    end = buffer.find(']', start) + 1
                    if end <= start:
                        log_debug("sensors", f"Date despre senzori: Delimitator ] lipsÄƒ, resetez buffer parÈ›ial")
                        buffer = buffer[end:]  # EliminÄƒ porÈ›iunea invalidÄƒ
                        break
                    json_str = buffer[start:end].strip()
                    log_debug("sensors", f"Date despre senzori: String JSON detectat: {repr(json_str)}")
                    if json_str.startswith('[') and json_str.endswith(']'):
                        try:
                            data_list = json.loads(json_str)
                            if len(data_list) == 4:  # AÈ™teptÄƒm doar 4 senzori
                                sensor_data = data_list  # ActualizÄƒm direct cu 4 valori
                                log_debug("sensors", f"Date despre senzori: Date senzor actualizate: {sensor_data}")
                                detect_people()
                                adjust_time_alignment()
                                socketio.emit('sensors', sensor_data)  # Emite mereu datele
                            else:
                                log_debug("sensors", f"Date despre senzori: StructurÄƒ JSON invalidÄƒ, lungime aÈ™teptatÄƒ 4, primitÄƒ: {len(data_list)}")
                        except json.JSONDecodeError as e:
                            log_debug("sensors", f"Date despre senzori: Eroare la parsarea JSON: {e}, Linie: {json_str}")
                    else:
                        log_debug("sensors", f"Date despre senzori: Fragment JSON invalid: {json_str}")
                    buffer = buffer[end:].strip()
                    if not buffer or '[' not in buffer:
                        break
            else:
                log_debug("sensors", f"Date despre senzori: Niciun date citite de la port")
                if ser.in_waiting == 0 and buffer and not '[' in buffer:
                    log_debug("sensors", f"Date despre senzori: Reset buffer din cauza datelor incomplete")
                    buffer = ""
        except serial.SerialException as e:
            log_debug("sensors", f"Date despre senzori: Eroare serial: {e}")
            ser.close()
            time.sleep(5)
            continue
        except Exception as e:
            log_debug("sensors", f"Date despre senzori: Eroare neaÈ™teptatÄƒ: {e}")
        time.sleep(0.01)

serial_thread = threading.Thread(target=read_serial, daemon=True)
serial_thread.start()

baseline_thread = threading.Thread(target=establish_baseline, daemon=True)
baseline_thread.start()

class AudioProcessor:
    def __init__(self):
        self.p = pyaudio.PyAudio()
        log_debug("audio", "Dispozitive disponibile:")
        for i in range(self.p.get_device_count()):
            log_debug("audio", str(self.p.get_device_info_by_index(i)))

        self.stream_in = None
        self.stream_out = None
        self.initialize_streams()

        max_delay = max(params['delay_l'], params['delay_r'])
        self.delay_buffer = np.zeros((2, max_delay + CHUNK))
        self.delay_index = 0

    def initialize_streams(self):
        try:
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
            log_debug("audio", "ModificÄƒri ale sunetului: Stream-uri audio iniÈ›ializate È™i pornite")
        except Exception as e:
            log_debug("audio", f"ModificÄƒri ale sunetului: Eroare la iniÈ›ializarea stream-urilor: {e}")
            self.cleanup()
            raise

    def apply_noise_filter(self, data):
        noise_threshold = 2
        filtered_data = np.array(data, dtype=np.float32)
        filtered_data = np.where(np.abs(filtered_data) > noise_threshold, filtered_data, 0)
        window_size = 5
        if len(filtered_data) >= window_size:
            smoothed = np.convolve(filtered_data, np.ones(window_size) / window_size, mode='same')
            log_debug("audio", f"ModificÄƒri ale sunetului: Noise filter applied, window={window_size}, threshold={noise_threshold}, output length={len(smoothed)}")
            return smoothed.astype(np.int16).tolist()
        log_debug("audio", f"ModificÄƒri ale sunetului: Noise filter applied, window={window_size}, threshold={noise_threshold}, output length={len(filtered_data)}")
        return filtered_data.astype(np.int16).tolist()

    def equalize_audio(self, data, mic_level):
        audio_array = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        left = audio_array[::2].copy()
        right = audio_array[1::2].copy()
        chunk_size = len(left)

        # Deoarece nu mai avem microfon, setÄƒm gain_factor la 1.0
        gain_factor = 1.0

        left = left * gain_factor
        right = right * gain_factor

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
        log_debug("audio", f"ModificÄƒri ale sunetului: Equalize audio applied, gain={gain_factor}, delay_l={params['delay_l']} ms, delay_r={params['delay_r']} ms")
        return output.astype(np.int16).tobytes()

    def run(self):
        global should_run, audio_buffer_in, audio_buffer_out, last_audio_update
        log_debug("audio", f"ModificÄƒri ale sunetului: RedirecÈ›ionare sunet de la hw:0,1 la hw:3,0 la {RATE} Hz...")

        while True:
            with processor_lock:
                if not should_run:
                    log_debug("audio", "ModificÄƒri ale sunetului: should_run este False, opresc bucla audio")
                    break

            try:
                if not self.stream_in or not self.stream_in.is_active():
                    log_debug("audio", "ModificÄƒri ale sunetului: Stream input nu este activ, opresc")
                    break

                data_in = self.stream_in.read(CHUNK, exception_on_overflow=False)

                with processor_lock:
                    if not should_run:
                        log_debug("audio", "ModificÄƒri ale sunetului: should_run devine False dupÄƒ read, opresc")
                        break

                data_out = self.equalize_audio(data_in, 0)  # mic_level setat la 0, fÄƒrÄƒ microfon

                if not self.stream_out or not self.stream_out.is_active():
                    log_debug("audio", "ModificÄƒri ale sunetului: Stream output nu este activ, opresc")
                    break

                self.stream_out.write(data_out)

                with processor_lock:
                    if not should_run:
                        break

                try:
                    audio_queue_in.put(data_in, block=False)
                except queue.Full:
                    try:
                        audio_queue_in.get_nowait()
                        audio_queue_in.put(data_in, block=False)
                    except queue.Empty:
                        pass

                try:
                    audio_queue_out.put(data_out, block=False)
                except queue.Full:
                    try:
                        audio_queue_out.get_nowait()
                        audio_queue_out.put(data_out, block=False)
                    except queue.Empty:
                        pass

                audio_buffer_in.append(list(np.frombuffer(data_in, dtype=np.int16)[::2]))
                audio_buffer_out.append(list(np.frombuffer(data_out, dtype=np.int16)[::2]))

                current_time = time.time()
                if current_time - last_audio_update >= 0.06:
                    with processor_lock:
                        if not should_run:
                            break

                    filtered_input = self.apply_noise_filter([item for sublist in audio_buffer_in for item in sublist])
                    filtered_output = self.apply_noise_filter([item for sublist in audio_buffer_out for item in sublist])

                    socketio.emit('data_input', {'input': filtered_input})
                    socketio.emit('data_output', {'output': filtered_output})
                    last_audio_update = current_time
                    audio_buffer_in.clear()
                    audio_buffer_out.clear()

            except OSError as e:
                log_debug("audio", f"ModificÄƒri ale sunetului: Eroare la citire: {e}")
                with processor_lock:
                    if not should_run:
                        break
                continue
            except Exception as e:
                log_debug("audio", f"ModificÄƒri ale sunetului: Eroare neaÈ™teptatÄƒ Ã®n audio loop: {e}")
                with processor_lock:
                    if not should_run:
                        break
                continue

        log_debug("audio", "ModificÄƒri ale sunetului: Thread audio oprit.")

    def cleanup(self):
        log_debug("audio", "ModificÄƒri ale sunetului: ÃŽncep cleanup...")
        try:
            if hasattr(self, 'stream_in') and self.stream_in:
                if self.stream_in.is_active():
                    self.stream_in.stop_stream()
                self.stream_in.close()
                log_debug("audio", "ModificÄƒri ale sunetului: Stream input Ã®nchis")
        except Exception as e:
            log_debug("audio", f"ModificÄƒri ale sunetului: Eroare la Ã®nchiderea stream_in: {e}")

        try:
            if hasattr(self, 'stream_out') and self.stream_out:
                if self.stream_out.is_active():
                    self.stream_out.stop_stream()
                self.stream_out.close()
                log_debug("audio", "ModificÄƒri ale sunetului: Stream output Ã®nchis")
        except Exception as e:
            log_debug("audio", f"ModificÄƒri ale sunetului: Eroare la Ã®nchiderea stream_out: {e}")

        try:
            if hasattr(self, 'p') and self.p:
                self.p.terminate()
                log_debug("audio", "ModificÄƒri ale sunetului: PyAudio terminat")
        except Exception as e:
            log_debug("audio", f"ModificÄƒri ale sunetului: Eroare la terminarea PyAudio: {e}")

        log_debug("audio", "ModificÄƒri ale sunetului: Cleanup finalizat.")

def start_processing():
    global processor, should_run
    with processor_lock:
        if processor is not None:
            should_run = False
            try:
                processor.cleanup()
            except Exception as e:
                log_debug("general", f"Eroare la cleanup: {e}")
            processor = None

        time.sleep(0.1)

        try:
            processor = AudioProcessor()
            should_run = True
            log_debug("general", "Procesare audio pornitÄƒ!")
            threading.Thread(target=processor.run, daemon=True).start()
        except Exception as e:
            log_debug("general", f"Eroare la pornirea procesÄƒrii: {e}")
            should_run = False
            processor = None

def websocket_data_thread():
    global last_sensor_update, last_logs_update
    while True:
        if not params['running']:
            socketio.sleep(0.1)
            continue

        current_time = time.time()

        if current_time - last_sensor_update >= 0.1:
            if sensor_data and any(isinstance(v, (int, float)) for v in sensor_data[:4]):
                socketio.emit('sensors', sensor_data)
            socketio.emit('people', {
                "count": len(people_positions),
                "positions": [{"x": pos[0], "y": pos[1]} for pos in people_positions]
            })
            with SPEAKER_POSITION_LOCK:
                socketio.emit('speaker_position', {'x': SPEAKER_POSITION[0], 'y': SPEAKER_POSITION[1]})
            last_sensor_update = current_time

        if current_time - last_logs_update >= 1.0:
            input_max = 0
            output_max = 0

            try:
                while not audio_queue_in.empty():
                    data_in = audio_queue_in.get_nowait()
                    if data_in:
                        audio_array_in = np.frombuffer(data_in, dtype=np.int16)
                        input_max = max(input_max, int(np.max(np.abs(audio_array_in))))
            except queue.Empty:
                pass

            try:
                while not audio_queue_out.empty():
                    data_out = audio_queue_out.get_nowait()
                    if data_out:
                        audio_array_out = np.frombuffer(data_out, dtype=np.int16)
                        output_max = max(output_max, int(np.max(np.abs(audio_array_out))))
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

        socketio.emit('params', params)
        socketio.sleep(0.01)

socketio.start_background_task(websocket_data_thread)

@app.route('/toggle', methods=['POST'])
def toggle_processing():
    global should_run, processor

    log_debug("general", "Cerere POST /toggle primitÄƒ!")
    log_debug("general", f"ÃŽnainte de toggle: running = {params['running']}")

    if params['running']:
        log_debug("general", "Oprim procesarea...")
        params['running'] = False

        with processor_lock:
            should_run = False

        if processor is not None:
            try:
                if hasattr(processor, 'stream_in') and processor.stream_in and processor.stream_in.is_active():
                    processor.stream_in.stop_stream()
                    log_debug("general", "Stream input oprit imediat")
                if hasattr(processor, 'stream_out') and processor.stream_out and processor.stream_out.is_active():
                    processor.stream_out.stop_stream()
                    log_debug("general", "Stream output oprit imediat")
            except Exception as e:
                log_debug("general", f"Eroare la oprirea stream-urilor: {e}")

        while not audio_queue_in.empty():
            try:
                audio_queue_in.get_nowait()
            except queue.Empty:
                break
        while not audio_queue_out.empty():
            try:
                audio_queue_out.get_nowait()
            except queue.Empty:
                break

        log_debug("general", "Procesare opritÄƒ")

    else:
        log_debug("general", "Pornesc procesarea...")
        params['running'] = True
        start_processing()
        log_debug("general", "Procesare pornitÄƒ")

    log_debug("general", f"DupÄƒ toggle: running = {params['running']}")
    return jsonify({'status': 'success', 'running': params['running']})

@app.route('/logs/sensors', methods=['GET'])
def get_sensor_logs():
    global sensor_logs
    return jsonify({'logs': sensor_logs})

@app.route('/logs/people', methods=['GET'])
def get_people_logs():
    global people_logs
    return jsonify({'logs': people_logs})

@app.route('/logs/audio', methods=['GET'])
def get_audio_logs():
    global audio_logs
    return jsonify({'logs': audio_logs})

@app.route('/logs/general', methods=['GET'])
def get_general_logs():
    global general_logs
    return jsonify({'logs': general_logs})

@socketio.on('connect')
def handle_connect():
    log_debug("general", "Client conectat!")

@socketio.on('disconnect')
def handle_disconnect():
    log_debug("general", "Client deconectat!")

if __name__ == '__main__':
    try:
        socketio.run(app, host='0.0.0.0', port=5500, debug=True)
    except KeyboardInterrupt:
        log_debug("general", "Oprire prin Ctrl+C...")
        with processor_lock:
            should_run = False
        if processor is not None:
            processor.cleanup()
        if ser.is_open:
            ser.close()
        log_debug("general", "AplicaÈ›ie Ã®nchisÄƒ.")
