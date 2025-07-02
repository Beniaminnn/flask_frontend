<template>
  <div class="container">
    <h1 class="title">Audio and Sensor Control Panel</h1>

    <div class="control-form">
      <label>
        Delay Left:
        <span>{{ delayL }} samples</span>
      </label>
      <br />
      <label>
        Delay Right:
        <span>{{ delayR }} samples</span>
      </label>
      <br />

      <div class="button-group">
        <button @click="toggleProcessing" class="start-stop" :class="{ 'active': running }">
          {{ running ? 'Stop' : 'Start' }}
        </button>
        <button @click="resetCharts" class="reset-button">Reset Charts</button>
      </div>
    </div>

    <div class="chart-container">
      <div class="chart-row">
        <div class="chart-box">
          <h2 class="chart-title">Input Waveform</h2>
          <Chart type="line" :data="inputChartData" :options="inputChartOptions" class="chart" />
        </div>
        <div class="chart-box">
          <h2 class="chart-title">Output Waveform</h2>
          <Chart type="line" :data="outputChartData" :options="outputChartOptions" class="chart" />
        </div>
      </div>
    </div>

    <div class="logs-container">
      <div class="logs-row">
        <div class="logs-box sensors-section">
          <h2 class="section-title">Raspberry Pi Stats</h2>
          <ul class="stats-list">
            <li>Input Max Amplitude: {{ waveformData.input_max_amplitude }}</li>
            <li>Output Max Amplitude: {{ waveformData.output_max_amplitude }}</li>
            <li>Temperature: {{ logs.temperature || 'N/A' }}</li>
            <li>CPU Load: {{ logs.cpu_load || 'N/A' }}%</li>
            <li>Wi-Fi SSID: {{ logs.wifi_ssid || 'N/A' }}</li>
            <li>Wi-Fi Signal: {{ logs.wifi_signal || 'N/A' }} dBm</li>
          </ul>
        </div>
        <div class="logs-box sensors-section">
          <h2 class="section-title">Room Map & Sensors</h2>
          <div class="sensors-content">
            <div class="room-map-wrapper">
              <div class="room-map" :style="{ width: mapSize + 'px', height: mapSize + 'px' }">
                <div class="speaker-center-marker" style="left: 50%; top: 50%; transform: translate(-50%, -50%);"></div>
                <!-- Senzor Față (în față, la 0° din perspectiva difuzorului) -->
                <div class="sensor-marker" id="sensor-fata" :data-distance="sensors.distances[2] !== -1 ? `${sensors.distances[2]} cm` : 'Eroare cm'" style="top: 0; left: 50%; transform: translateX(-50%);"></div>
                <!-- Senzor Spate (în spate, la 180°) -->
                <div class="sensor-marker" id="sensor-spate" :data-distance="sensors.distances[3] !== -1 ? `${sensors.distances[3]} cm` : 'Eroare cm'" style="bottom: 0; left: 50%; transform: translateX(-50%);"></div>
                <!-- Senzor Stânga (la 90° stânga) -->
                <div class="sensor-marker" id="sensor-stanga" :data-distance="sensors.distances[1] !== -1 ? `${sensors.distances[1]} cm` : 'Eroare cm'" style="top: 50%; left: 0; transform: translateY(-50%);"></div>
                <!-- Senzor Dreapta (la 270° dreapta) -->
                <div class="sensor-marker" id="sensor-dreapta" :data-distance="sensors.distances[0] !== -1 ? `${sensors.distances[0]} cm` : 'Eroare cm'" style="top: 50%; right: 0; transform: translateY(-50%);"></div>
                <div class="speaker-marker" id="speaker" :style="getSpeakerPositionStyle(speakerPos)" :data-position="`x: ${speakerPos.x.toFixed(1)} cm, y: ${speakerPos.y.toFixed(1)} cm`"></div>
                <div v-for="(person, index) in peoplePositions" :key="index" class="person-marker" :style="getPersonPositionStyle(person)" :data-position="`x: ${person.x.toFixed(1)} cm, y: ${person.y.toFixed(1)} cm`"></div>
                <div v-for="(angle, index) in sensorAngles" :key="'angle-' + index" class="angle-indicator" :style="getAngleIndicatorStyle(index, angle)" v-if="isDataReady"></div>
              </div>
            </div>
            <ul class="sensors-list" v-if="isDataReady">
              <li>Dreapta: {{ sensors.distances[0] !== -1 ? `${sensors.distances[0]} cm` : 'Eroare' }} (Unghi: {{ getSafeAngle(sensorAngles[0]) }})</li>
              <li>Stanga: {{ sensors.distances[1] !== -1 ? `${sensors.distances[1]} cm` : 'Eroare' }} (Unghi: {{ getSafeAngle(sensorAngles[1]) }})</li>
              <li>Fata: {{ sensors.distances[2] !== -1 ? `${sensors.distances[2]} cm` : 'Eroare' }} (Unghi: {{ getSafeAngle(sensorAngles[2]) }})</li>
              <li>Spate: {{ sensors.distances[3] !== -1 ? `${sensors.distances[3]} cm` : 'Eroare' }} (Unghi: {{ getSafeAngle(sensorAngles[3]) }})</li>
              <li>Persoane detectate: {{ peopleCount }}</li>
            </ul>
            <p v-if="hasOverlap" class="overlap-warning">Atenție: Detectări multiple pot indica suprapuneri sau reflexii (unghiuri largi).</p>
          </div>
          <!-- Container nou pentru persoanele detectate -->
          <div class="people-container" v-if="peopleCount > 0 && isDataReady">
            <h3 class="people-title">Detected People</h3>
            <div class="people-cards">
              <div v-for="(person, index) in peoplePositions" :key="index" class="person-card">
                <div class="person-card-header">
                  <span class="person-number">Person {{ index + 1 }}</span>
                  <span class="person-confidence" :style="{ color: getConfidenceColor(sensors.confidence[0] || 0) }">
                    Confidence: {{ (sensors.confidence[0] || 0).toFixed(2) }}
                  </span>
                </div>
                <div class="person-details">
                  <p>Position: x={{ person.x.toFixed(1) }} cm, y={{ person.y.toFixed(1) }} cm</p>
                  <p>Velocity: vx={{ sensors.velocities[index * 2] || 0 }} cm/s, vy={{ sensors.velocities[index * 2 + 1] || 0 }} cm/s</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="logs-box logs-section">
        <h2 class="section-title">System Logs</h2>
        <div class="tabs">
          <button @click="activeTab = 'general'" :class="{ active: activeTab === 'general' }">General</button>
          <button @click="activeTab = 'sensors'" :class="{ active: activeTab === 'sensors' }">Sensors</button>
          <button @click="activeTab = 'people'" :class="{ active: activeTab === 'people' }">People</button>
          <button @click="toggleCompactMode" class="compact-toggle" :class="{ active: compactMode }">{{ compactMode ? 'Full' : 'Compact' }}</button>
        </div>
        <div class="log-content" v-if="activeTab === 'general'">
          <ul class="log-list">
            <li v-for="log in logsGeneral" :key="log" class="log-item" :class="{ compact: compactMode }">{{ log }}</li>
          </ul>
        </div>
        <div class="log-content" v-if="activeTab === 'sensors'">
          <ul class="log-list">
            <li v-for="log in logsSensors" :key="log" class="log-item" :class="{ compact: compactMode }">{{ log }}</li>
          </ul>
        </div>
        <div class="log-content" v-if="activeTab === 'people'">
          <ul class="log-list">
            <li v-for="log in logsPeople" :key="log" class="log-item" :class="{ compact: compactMode }">{{ log }}</li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Chart } from 'vue-chartjs';
import {
  Chart as ChartJS,
  LineElement,
  PointElement,
  LinearScale,
  Title,
  CategoryScale,
} from 'chart.js';
import { useStore } from 'vuex';
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import axios from 'axios';
import { useToast } from '@brackets/vue-toastification';
import { io } from 'socket.io-client';

ChartJS.register(LineElement, PointElement, LinearScale, Title, CategoryScale);

const store = useStore();
const running = computed(() => store.state.running);
const delayL = computed(() => store.state.delayL);
const delayR = computed(() => store.state.delayR);
const waveformData = computed(() => store.state.waveformData);
const logs = computed(() => store.state.logs);
const sensors = computed(() => store.state.sensors);

const peopleCount = ref(0);
const peoplePositions = ref([]);
const speakerPos = ref({ x: 200, y: 200 });
const logsGeneral = ref([]);
const logsSensors = ref([]);
const logsPeople = ref([]);
const activeTab = ref('general');
const mapSize = ref(200);
const compactMode = ref(false);
const MAX_POINTS = 400;
const sensorAngles = ref([0, 0, 0, 0]);
const hasOverlap = ref(false);
const isDataReady = ref(false);

const downsample = (data, maxPoints) => {
  if (!data || data.length <= maxPoints) return data || [];
  const step = Math.floor(data.length / maxPoints);
  return data.filter((_, i) => i % step === 0).slice(0, maxPoints);
};

const getDynamicRange = (data, maxAmplitude) => {
  if (!data || data.length === 0) return { min: -35000, max: 35000 };
  const amplitude = maxAmplitude || Math.max(...data.map(Math.abs), 1);
  const margin = amplitude * 0.1;
  return { min: -amplitude - margin, max: amplitude + margin };
};

const inputChartData = computed(() => ({
  labels: Array(downsample(waveformData.value.input, MAX_POINTS).length).fill(''),
  datasets: [{
    label: 'Input',
    data: downsample(waveformData.value.input, MAX_POINTS),
    borderColor: '#007bff',
    fill: false,
    pointRadius: 0,
  }],
}));

const outputChartData = computed(() => ({
  labels: Array(downsample(waveformData.value.output, MAX_POINTS).length).fill(''),
  datasets: [
    {
      label: 'Output',
      data: downsample(waveformData.value.output, MAX_POINTS),
      borderColor: '#28a745',
      fill: false,
      pointRadius: 0,
    },
    ...(waveformData.value.anomalies.length > 0 ? [{
      label: 'Anomalies',
      data: downsample(waveformData.value.anomalies.map(i => ({ x: i, y: getDynamicRange(waveformData.value.output, waveformData.value.output_max_amplitude).max * 0.9 })), MAX_POINTS),
      borderColor: '#dc3545',
      pointRadius: 2,
      fill: false,
    }] : []),
  ],
}));

const inputChartOptions = computed(() => ({
  animation: false,
  maintainAspectRatio: false,
  scales: {
    x: { display: false },
    y: { min: getDynamicRange(waveformData.value.input, waveformData.value.input_max_amplitude).min, max: getDynamicRange(waveformData.value.input, waveformData.value.input_max_amplitude).max },
  },
}));

const outputChartOptions = computed(() => ({
  animation: false,
  maintainAspectRatio: false,
  scales: {
    x: { display: false },
    y: { min: getDynamicRange(waveformData.value.output, waveformData.value.output_max_amplitude).min, max: getDynamicRange(waveformData.value.output, waveformData.value.output_max_amplitude).max },
  },
  plugins: {
    tooltip: {
      callbacks: {
        label: (context) => (context.dataset.label === 'Anomalies' ? 'Anomaly detected' : `${context.dataset.label}: ${context.parsed.y}`),
      },
    },
  },
}));

const getPersonPositionStyle = (person) => ({
  left: `${(person.x / 400) * mapSize.value}px`,
  top: `${(person.y / 400) * mapSize.value}px`,
  transform: 'translate(-50%, -50%)',
});

const getSpeakerPositionStyle = (pos) => ({
  left: `${(pos.x / 400) * mapSize.value}px`,
  top: `${(pos.y / 400) * mapSize.value}px`,
  transform: 'translate(-50%, -50%)',
});

const getAngleIndicatorStyle = (index, angle) => {
  const centerX = (speakerPos.value.x / 400) * mapSize.value;
  const centerY = (speakerPos.value.y / 400) * mapSize.value;
  let startX, startY;
  switch (index) {
    case 0: // Dreapta (270°)
      startX = mapSize.value; startY = centerY;
      break;
    case 1: // Stânga (90°)
      startX = 0; startY = centerY;
      break;
    case 2: // Față (0°)
      startX = centerX; startY = 0;
      break;
    case 3: // Spate (180°)
      startX = centerX; startY = mapSize.value;
      break;
  }
  const length = 50;
  const endX = centerX + length * Math.cos((angle - 90) * Math.PI / 180);
  const endY = centerY + length * Math.sin((angle - 90) * Math.PI / 180);
  return {
    position: 'absolute',
    left: `${centerX}px`,
    top: `${centerY}px`,
    width: `${Math.sqrt((endX - centerX) ** 2 + (endY - centerY) ** 2)}px`,
    height: '2px',
    backgroundColor: 'rgba(255, 0, 0, 0.5)',
    transform: `rotate(${angle}deg)`,
    transformOrigin: '0 0',
  };
};

const getSafeAngle = (angle) => {
  return angle !== null && angle !== undefined && !isNaN(angle) ? `${angle.toFixed(1)}°` : 'N/A';
};

const getConfidenceColor = (confidence) => {
  if (confidence >= 0.7) return '#28a745';
  if (confidence >= 0.4) return '#ffc107';
  return '#dc3545';
};

const calculateAngles = () => {
  if (!peoplePositions.value.length || !sensors.value.distances.every(d => d > 0 && d !== -1)) {
    sensorAngles.value = [0, 0, 0, 0];
    hasOverlap.value = false;
    isDataReady.value = false;
    return;
  }

  const angles = [0, 0, 0, 0]; // [Dreapta, Stânga, Față, Spate]
  const speakerX = speakerPos.value.x;
  const speakerY = speakerPos.value.y;

  peoplePositions.value.forEach(person => {
    const dx = person.x - speakerX;
    const dy = person.y - speakerY;
    const angleRad = Math.atan2(dy, dx);
    const angleDeg = (angleRad * 180 / Math.PI + 360) % 360;

    if (Math.abs(angleDeg - 0) < 45 || Math.abs(angleDeg - 360) < 45) angles[2] = angleDeg; // Față
    if (Math.abs(angleDeg - 180) < 45) angles[3] = angleDeg; // Spate
    if (Math.abs(angleDeg - 90) < 45) angles[1] = angleDeg; // Stânga
    if (Math.abs(angleDeg - 270) < 45) angles[0] = angleDeg; // Dreapta
  });

  sensorAngles.value = angles;
  hasOverlap.value = peopleCount.value > 1 && angles.some(a => a !== 0 && Math.abs(a - angles.find(a2 => a2 !== 0)) > 90);
  isDataReady.value = true;
};

const socket = io('http://192.168.100.100:5500');

onMounted(() => {
  socket.on('connect', () => console.log('Conectat la server WebSocket'));

  socket.on('data_input', (data) => {
    store.commit('setWaveformData', {
      input: data.input || [],
      input_max_amplitude: data.max_amplitude || 0,
      output: waveformData.value.output,
      anomalies: waveformData.value.anomalies,
      output_max_amplitude: waveformData.value.output_max_amplitude,
    });
  });
  socket.on('data_output', (data) => {
    store.commit('setWaveformData', {
      output: data.output || [],
      output_max_amplitude: data.max_amplitude || 0,
      input: waveformData.value.input,
      anomalies: data.anomalies || [],
      input_max_amplitude: waveformData.value.input_max_amplitude,
    });
  });
  socket.on('sensors', (data) => {
    console.log('Received sensors data:', data);
    store.commit('setSensors', {
      distances: data.distances || [-1, -1, -1, -1],
      positions: data.positions || [],
      velocities: data.velocities || [],
      confidence: data.confidence || [],
      timestamp: data.timestamp || 0,
    });
  });
  socket.on('people', (data) => {
    peopleCount.value = data.count || 0;
    peoplePositions.value = data.positions.map(pos => ({ x: pos.x, y: pos.y })) || [];
  });
  socket.on('params', (data) => {
    store.commit('setDelayL', data.delay_l || 0);
    store.commit('setDelayR', data.delay_r || 0);
    store.commit('setRunning', data.running || false);
  });
  socket.on('speaker_position', (data) => (speakerPos.value = { x: data.x || 200, y: data.y || 200 }));
  socket.on('logs', (data) => store.commit('setLogs', { ...logs.value, ...data }));

  const fetchLogs = async () => {
    try {
      const [generalRes, sensorsRes, peopleRes] = await Promise.all([
        axios.get('http://192.168.100.100:5500/logs/general'),
        axios.get('http://192.168.100.100:5500/logs/sensors'),
        axios.get('http://192.168.100.100:5500/logs/people'),
      ]);
      logsGeneral.value = generalRes.data.logs.reverse().slice(0, 200) || [];
      logsSensors.value = sensorsRes.data.logs.reverse().slice(0, 200) || [];
      logsPeople.value = peopleRes.data.logs.reverse().slice(0, 200) || [];
    } catch (error) {
      console.error('Eroare la incarcarea logurilor:', error);
      toast.error('Eroare la incarcarea logurilor');
    }
  };

  fetchLogs();
  setInterval(fetchLogs, 5000);

  watch([peoplePositions, speakerPos, sensors], () => {
    calculateAngles();
  }, { immediate: true });

  const updateMapSize = () => {
    mapSize.value = Math.min(window.innerWidth * 0.4, 300);
  };
  updateMapSize();
  window.addEventListener('resize', updateMapSize);

  socket.on('disconnect', () => {
    console.log('Deconectat de la server WebSocket');
    store.commit('setWaveformData', { input: [], output: [], anomalies: [], input_max_amplitude: 0, output_max_amplitude: 0 });
    store.commit('setSensors', { distances: [-1, -1, -1, -1], positions: [], velocities: [], confidence: [], timestamp: 0 });
    peopleCount.value = 0;
    peoplePositions.value = [];
    logsGeneral.value = [];
    logsSensors.value = [];
    logsPeople.value = [];
    sensorAngles.value = [0, 0, 0, 0];
    hasOverlap.value = false;
    isDataReady.value = false;
  });
});

onUnmounted(() => {
  window.removeEventListener('resize', updateMapSize);
  socket.disconnect();
});

const toggleProcessing = async () => {
  try {
    const res = await axios.post('http://192.168.100.100:5500/toggle');
    store.commit('setRunning', res.data.running);
    toast.success(res.data.running ? 'Procesare pornita' : 'Procesare oprita');
  } catch (error) {
    console.error('Eroare la toggle:', error);
    toast.error('Eroare la toggle procesare');
  }
};

const resetCharts = () => {
  store.commit('setWaveformData', { input: [], output: [], anomalies: [], input_max_amplitude: 0, output_max_amplitude: 0 });
  toast.success('Grafice resetate');
};

const toggleCompactMode = () => {
  compactMode.value = !compactMode.value;
  toast.success(compactMode.value ? 'Mod compact activat' : 'Mod detaliat activat');
};

const toast = useToast();
</script>

<style scoped>
.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  background: linear-gradient(135deg, #f0f4f8, #d9e2ec);
  border-radius: 10px;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
}

.title {
  text-align: center;
  color: #333;
  text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.1);
  margin-bottom: 20px;
  font-size: 2rem;
}

.control-form {
  margin-bottom: 20px;
  padding: 15px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.05);
  transform: perspective(500px) rotateX(5deg);
  transition: transform 0.3s;
}

.control-form:hover {
  transform: perspective(500px) rotateX(0deg);
}

.button-group {
  margin-top: 10px;
  display: flex;
  gap: 10px;
}

.start-stop, .reset-button, .compact-toggle {
  padding: 10px 20px;
  color: #fff;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  transition: background-color 0.3s, transform 0.2s;
}

.start-stop {
  background-color: #dc3545;
}

.start-stop.active {
  background-color: #28a745;
}

.reset-button {
  background-color: #dc3545;
}

.compact-toggle {
  background-color: #6c757d;
}

.start-stop:hover, .reset-button:hover, .compact-toggle:hover {
  transform: translateY(-2px);
}

.start-stop:hover {
  background-color: #c82333;
}

.start-stop.active:hover {
  background-color: #218838;
}

.reset-button:hover {
  background-color: #c82333;
}

.compact-toggle:hover {
  background-color: #5a6268;
}

.chart-container {
  margin-bottom: 20px;
}

.chart-row {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 20px;
}

.chart-box {
  flex: 1;
  padding: 15px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.05);
  transform: perspective(500px) rotateX(5deg);
  transition: transform 0.3s;
}

.chart-box:hover {
  transform: perspective(500px) rotateX(0deg);
}

.chart-title {
  text-align: center;
  color: #333;
  margin-bottom: 10px;
  font-size: 1.2rem;
}

.chart {
  height: 250px;
}

.logs-container {
  width: 100%;
  margin-top: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.logs-row {
  display: flex;
  gap: 20px;
  width: 100%;
}

.logs-box {
  padding: 20px;
  background: #f8f9fa;
  border-radius: 8px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.05);
  transform: perspective(500px) rotateX(5deg);
  transition: transform 0.3s;
  flex: 1;
}

.logs-box:hover {
  transform: perspective(500px) rotateX(0deg);
}

.sensors-section {
  display: flex;
  flex-direction: column;
}

.section-title {
  text-align: center;
  color: #333;
  margin-bottom: 15px;
  font-size: 1.5rem;
}

.stats-list, .sensors-list, .log-list {
  list-style: none;
  padding: 0;
  font-size: 1.1rem;
  line-height: 1.6;
}

.stats-list li, .sensors-list li, .log-item {
  margin-bottom: 10px;
  padding: 8px;
  background: #fff;
  border-radius: 4px;
  transition: background 0.3s;
}

.sensors-list li:hover, .stats-list li:hover, .log-item:hover {
  background: #e9ecef;
}

.sensors-content {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  width: 100%;
  gap: 20px;
}

.room-map-wrapper {
  flex: 1;
  margin-bottom: 0;
}

.room-map {
  position: relative;
  border: 2px solid #ccc;
  background: linear-gradient(45deg, #fff, #f0f4f8);
  border-radius: 8px;
  box-shadow: inset 0 2px 5px rgba(0, 0, 0, 0.1);
}

.angle-indicator {
  position: absolute;
  transform-origin: 0 0;
}

.sensor-marker, .speaker-marker, .person-marker {
  position: absolute;
  border-radius: 50%;
  transition: transform 0.2s;
}

.sensor-marker {
  width: 10px;
  height: 10px;
  background-color: red;
}

.speaker-marker {
  width: 12px;
  height: 12px;
  background-color: blue;
}

.person-marker {
  width: 8px;
  height: 8px;
  background-color: green;
}

.sensor-marker:hover, .speaker-marker:hover, .person-marker:hover {
  transform: scale(1.2);
}

.sensor-marker:hover::after, .speaker-marker:hover::after, .person-marker:hover::after {
  content: attr(data-distance) attr(data-position);
  position: absolute;
  top: -25px;
  left: 50%;
  transform: translateX(-50%);
  background-color: #333;
  color: #fff;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  white-space: nowrap;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
}

.speaker-center-marker {
  position: absolute;
  width: 8px;
  height: 8px;
  background-color: gray;
  border-radius: 50%;
  border: 1px solid black;
}

.overlap-warning {
  color: #dc3545;
  font-weight: bold;
  margin-top: 10px;
  text-align: center;
}

.people-container {
  flex: 1;
  max-width: 300px;
}

.people-title {
  font-size: 1.3rem;
  color: #333;
  margin-bottom: 10px;
  text-align: center;
}

.people-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.person-card {
  background: #fff;
  border-radius: 8px;
  padding: 10px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
  transition: transform 0.2s, box-shadow 0.2s;
}

.person-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.15);
}

.person-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 5px;
}

.person-number {
  font-weight: bold;
  color: #28a745;
}

.person-confidence {
  font-size: 0.9rem;
}

.person-details {
  margin: 0;
  font-size: 1rem;
  color: #555;
}

.logs-section {
  width: 100%;
  min-height: 200px;
}

.tabs {
  display: flex;
  gap: 10px;
  margin-bottom: 15px;
  justify-content: center;
}

.tabs button {
  padding: 10px 20px;
  border: 1px solid #ccc;
  background-color: #f1f1f1;
  cursor: pointer;
  border-radius: 5px;
  font-size: 1.1rem;
  transition: all 0.3s;
}

.tabs button.active {
  background-color: #007bff;
  color: #fff;
  border-color: #007bff;
  transform: translateY(-2px);
}

.log-content {
  border: 1px solid #ddd;
  padding: 15px;
  border-radius: 8px;
  background: #fff;
  font-size: 1rem;
  line-height: 1.8;
  max-height: 300px;
  overflow-y: auto;
}

.log-item {
  margin-bottom: 10px;
  padding: 8px;
  background: #f1f1f1;
  border-left: 4px solid #007bff;
}

.log-item.compact {
  font-size: 0.9rem;
  padding: 4px;
  margin-bottom: 5px;
}

@media (max-width: 768px) {
  .chart-row {
    flex-direction: column;
  }
  .chart-box {
    width: 100%;
    margin-bottom: 20px;
  }
  .logs-row {
    flex-direction: column;
  }
  .logs-box {
    width: 100%;
    margin-bottom: 20px;
  }
  .sensors-content {
    flex-direction: column;
  }
  .room-map {
    margin-left: 0;
    margin-top: 10px;
  }
  .people-container {
    max-width: 100%;
    margin-top: 20px;
  }
  .chart {
    height: 200px;
  }
  .log-content {
    max-height: 200px;
  }
}
</style>