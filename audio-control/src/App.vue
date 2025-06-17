<template>
  <div class="container">
    <h1 class="title">Audio and Sensor Control Panel</h1>

    <div class="control-form">
      <label>
        Delay Left:
        <span>{{ delayL }} ms</span>
      </label>
      <br />
      <label>
        Delay Right:
        <span>{{ delayR }} ms</span>
      </label>
      <br />
      <label>
        Audio Amplitude (Mic):
        <span>{{ audioAmplitude }} units</span>
      </label>
      <br />

      <div class="button-group">
        <button @click="toggleProcessing" class="start-stop">
          {{ running ? 'Stop' : 'Start' }}
        </button>
      </div>
    </div>

    <div class="chart-container">
      <div class="chart-box">
        <h2 class="chart-title">Input</h2>
        <Chart type="line" :data="inputChartData" :options="inputChartOptions" class="chart" />
      </div>
      <div class="chart-box">
        <h2 class="chart-title">Output</h2>
        <Chart type="line" :data="outputChartData" :options="outputChartOptions" class="chart" />
      </div>
    </div>

    <div class="eq-chart-container">
      <div class="chart-box">
        <h2 class="chart-title">Equalization Gains</h2>
        <Chart type="bar" :data="eqChartData" :options="eqChartOptions" class="chart" />
      </div>
    </div>

    <div class="audio-chart-container">
      <div class="chart-box">
        <h2 class="chart-title">Microphone Waveform</h2>
        <Chart type="line" :data="audioChartData" :options="audioChartOptions" class="chart" />
      </div>
    </div>

    <div class="logs-container">
      <div class="logs-box">
        <h2 class="section-title">Raspberry Pi Stats</h2>
        <ul class="stats-list">
          <li>Input Max Amplitude: {{ logs.input_max_amplitude }}</li>
          <li>Output Max Amplitude: {{ logs.output_max_amplitude }}</li>
          <li>Temperature: {{ logs.temperature }}</li>
          <li>CPU Load: {{ logs.cpu_load }}%</li>
          <li>Wi-Fi SSID: {{ logs.wifi_ssid }}</li>
          <li>Wi-Fi Signal: {{ logs.wifi_signal }} dBm</li>
        </ul>
      </div>
      <div class="logs-box sensors-section">
        <h2 class="section-title">Sensor Distances</h2>
        <div class="sensors-content">
          <ul class="sensors-list">
            <li>Dreapta: {{ sensors.distances[0] || 'Eroare' }} cm</li>
            <li>Stânga: {{ sensors.distances[1] || 'Eroare' }} cm</li>
            <li>Față: {{ sensors.distances[2] || 'Eroare' }} cm</li>
            <li>Spate: {{ sensors.distances[3] || 'Eroare' }} cm</li>
            <li>Persoane detectate: {{ peopleCount }}</li>
          </ul>
          <div class="room-map">
            <div class="sensor-marker" id="sensor-fata" :data-distance="sensors.distances[2] + ' cm' || 'Eroare cm'" style="top: 0; left: 50%; transform: translateX(-50%);"></div>
            <div class="sensor-marker" id="sensor-spate" :data-distance="sensors.distances[3] + ' cm' || 'Eroare cm'" style="bottom: 0; left: 50%; transform: translateX(-50%);"></div>
            <div class="sensor-marker" id="sensor-stanga" :data-distance="sensors.distances[1] + ' cm' || 'Eroare cm'" style="top: 50%; left: 0; transform: translateY(-50%);"></div>
            <div class="sensor-marker" id="sensor-dreapta" :data-distance="sensors.distances[0] + ' cm' || 'Eroare cm'" style="top: 50%; right: 0; transform: translateY(-50%);"></div>
            <div class="speaker-marker" id="speaker" :style="getSpeakerPositionStyle(speakerPos)"></div>
            <div class="speaker-center-marker" style="left: 50%; top: 50%; transform: translate(-50%, -50%);"></div>
            <div v-for="(person, index) in peoplePositions" :key="index" class="person-marker" :style="getPersonPositionStyle(person)"></div>
          </div>
        </div>
      </div>
      <div class="logs-box logs-section">
        <h2 class="section-title">System Logs</h2>
        <div class="tabs">
          <button @click="activeTab = 'general'" :class="{ active: activeTab === 'general' }">General</button>
          <button @click="activeTab = 'sensors'" :class="{ active: activeTab === 'sensors' }">Sensors</button>
          <button @click="activeTab = 'people'" :class="{ active: activeTab === 'people' }">People</button>
          <button @click="activeTab = 'audio'" :class="{ active: activeTab === 'audio' }">Audio</button>
        </div>
        <div class="log-content" v-if="activeTab === 'general'">
          <ul class="log-list">
            <li v-for="log in logsGeneral" :key="log" class="log-item">{{ log }}</li>
          </ul>
        </div>
        <div class="log-content" v-if="activeTab === 'sensors'">
          <ul class="log-list">
            <li v-for="log in logsSensors" :key="log" class="log-item">{{ log }}</li>
          </ul>
        </div>
        <div class="log-content" v-if="activeTab === 'people'">
          <ul class="log-list">
            <li v-for="log in logsPeople" :key="log" class="log-item">{{ log }}</li>
          </ul>
        </div>
        <div class="log-content" v-if="activeTab === 'audio'">
          <ul class="log-list">
            <li v-for="log in logsAudio" :key="log" class="log-item">{{ log }}</li>
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
  BarElement,
} from 'chart.js';
import { useStore } from 'vuex';
import { computed, onMounted, onUnmounted, ref } from 'vue';
import axios from 'axios';
import { useToast } from '@brackets/vue-toastification';
import { io } from 'socket.io-client';

// Înregistrăm componentele Chart.js
ChartJS.register(LineElement, PointElement, LinearScale, Title, CategoryScale, BarElement);

// Vuex store
const store = useStore();
const running = computed(() => store.state.running);
const delayL = computed(() => store.state.delayL);
const delayR = computed(() => store.state.delayR);
const waveformData = computed(() => store.state.waveformData);
const logs = computed(() => store.state.logs);
const sensors = computed(() => store.state.sensors);

// Date despre persoane, boxă și audio
const peopleCount = ref(0);
const peoplePositions = ref([]);
const speakerPos = ref({ x: 200, y: 200 });
const audioAmplitude = ref(0); // Amplitudinea maximă a microfonului
const micWaveformData = ref([]); // Date brute ale microfonului

// Loguri
const logsGeneral = ref([]);
const logsSensors = ref([]);
const logsPeople = ref([]);
const logsAudio = ref([]);
const activeTab = ref('general');

// Date pentru egalizare
const eqData = ref({ bass: 1.0, mid: 1.0, treble: 1.0 });

// Date pentru anomalii
const anomalyIndices = ref([]);

// Toast
const toast = useToast();

// Numărul maxim de puncte de afișat în grafic
const MAX_POINTS = 400;

// Funcție pentru subeșantionare
const downsample = (data, maxPoints) => {
  if (data.length <= maxPoints) return data;
  const step = Math.floor(data.length / maxPoints);
  return data.filter((_, i) => i % step === 0).slice(0, maxPoints);
};

// Subeșantionează indicii anomaliilor
const downsampleAnomalies = (indices, dataLength, maxPoints) => {
  if (dataLength <= maxPoints) return indices;
  const step = Math.floor(dataLength / maxPoints);
  return indices.map(idx => Math.floor(idx / step)).filter(idx => idx < maxPoints);
};

// Calculează amplitudinea maximă cu o marjă
const getDynamicRange = (data) => {
  if (!data || data.length === 0) return { min: -35000, max: 35000 };
  const maxAmplitude = Math.max(...data.map(Math.abs));
  const margin = maxAmplitude * 0.1;
  return { min: -maxAmplitude - margin, max: maxAmplitude + margin };
};

// Configurare grafice
const inputChartData = computed(() => ({
  labels: Array(downsample(waveformData.value.input, MAX_POINTS).length).fill(''),
  datasets: [{
    label: 'Input',
    data: downsample(waveformData.value.input, MAX_POINTS),
    borderColor: 'blue',
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
      borderColor: 'green',
      fill: false,
      pointRadius: 0,
    },
  ],
}));

const eqChartData = computed(() => ({
  labels: ['Bass (20-250 Hz)', 'Mid (250-4000 Hz)', 'Treble (4000-20000 Hz)'],
  datasets: [{
    label: 'Gain Factor',
    data: [eqData.value.bass, eqData.value.mid, eqData.value.treble],
    backgroundColor: ['#FF6384', '#36A2EB', '#FFCE56'],
    borderColor: ['#FF6384', '#36A2EB', '#FFCE56'],
    borderWidth: 1,
  }],
}));

const audioChartData = computed(() => {
  console.log('Audio Chart Data:', downsample(micWaveformData.value, MAX_POINTS)); // Log pentru verificare
  return {
    labels: Array(downsample(micWaveformData.value, MAX_POINTS).length).fill(''),
    datasets: [{
      label: 'Mic Waveform',
      data: downsample(micWaveformData.value, MAX_POINTS),
      borderColor: 'purple',
      fill: false,
      pointRadius: 0,
    }],
  };
});

const inputChartOptions = computed(() => ({
  animation: false,
  maintainAspectRatio: false,
  scales: {
    x: { display: false },
    y: { min: getDynamicRange(waveformData.value.input).min, max: getDynamicRange(waveformData.value.input).max },
  },
}));

const outputChartOptions = computed(() => ({
  animation: false,
  maintainAspectRatio: false,
  scales: {
    x: { display: false },
    y: { min: getDynamicRange(waveformData.value.output).min, max: getDynamicRange(waveformData.value.output).max },
  },
  plugins: {
    tooltip: {
      callbacks: {
        label: (context) => (context.dataset.label === 'Anomalies' ? 'Anomaly detected' : `${context.dataset.label}: ${context.parsed.y}`),
      },
    },
  },
}));

const eqChartOptions = computed(() => ({
  animation: false,
  maintainAspectRatio: false,
  scales: {
    y: {
      beginAtZero: true,
      min: 0,
      max: 1.5,
      title: { display: true, text: 'Gain' },
    },
  },
  plugins: {
    legend: { position: 'top' },
    tooltip: {
      callbacks: {
        label: (context) => `${context.label}: ${context.parsed.y.toFixed(2)}x`,
      },
    },
  },
}));

const audioChartOptions = computed(() => ({
  animation: false,
  maintainAspectRatio: false,
  scales: {
    x: { display: false },
    y: { min: -32768, max: 32768 }, // Scală pentru date int16 brute
  },
}));

// Calculează poziția persoanelor pe hartă
const getPersonPositionStyle = (person) => {
  const mapSize = 200;
  const roomSize = 400;
  return {
    left: `${(person.x / roomSize) * mapSize}px`,
    top: `${(person.y / roomSize) * mapSize}px`,
    transform: 'translate(-50%, -50%)',
  };
};

// Calculează poziția boxei pe hartă
const getSpeakerPositionStyle = (pos) => {
  const mapSize = 200;
  const roomSize = 400;
  return {
    left: `${(pos.x / roomSize) * mapSize}px`,
    top: `${(pos.y / roomSize) * mapSize}px`,
    transform: 'translate(-50%, -50%)',
  };
};

// Configurare WebSocket
const socket = io('http://192.168.3.28:5500');

onMounted(() => {
  socket.on('connect', () => console.log('Conectat la server WebSocket'));

  socket.on('data_input', (data) => store.commit('setWaveformData', {
    input: data.input || [],
    output: waveformData.value.output,
    anomalies: waveformData.value.anomalies,
  }));
  socket.on('data_output', (data) => store.commit('setWaveformData', {
    input: waveformData.value.input,
    output: data.output || [],
    anomalies: data.anomalies || [],
  }));
  socket.on('sensors', (data) => {
    console.log('Received sensors data:', data);
    store.commit('setSensors', data);
  });
  socket.on('people', (data) => {
    peopleCount.value = data.count;
    peoplePositions.value = data.positions.map(pos => ({x: pos.x, y: pos.y}));
  });
  socket.on('params', (data) => {
    store.commit('setDelayL', data.delay_l);
    store.commit('setDelayR', data.delay_r);
    store.commit('setRunning', data.running);
  });
  socket.on('speaker_position', (data) => (speakerPos.value = {x: data.x, y: data.y}));
  socket.on('equalization_data', (data) => {
    eqData.value.bass = data.bass;
    eqData.value.mid = data.mid;
    eqData.value.treble = data.treble;
  });
  socket.on('audio_data', (data) => {
    audioAmplitude.value = data.amplitude || 0;
  });
  socket.on('microphone_data', (data) =>  {
    console.log('Received microphone data:', data); // Log pentru verificare
    micWaveformData.value = data.input || [];
  });
  socket.on('logs', (data) => store.commit('setLogs', data));

  const fetchLogs = async () => {
    try {
      const [generalRes, sensorsRes, peopleRes, audioRes] = await Promise.all([
        axios.get('http://192.168.3.28:5500/logs/general'),
        axios.get('http://192.168.3.28:5500/logs/sensors'),
        axios.get('http://192.168.3.28:5500/logs/people'),
        axios.get('http://192.168.3.28:5500/logs/audio'),
      ]);
      logsGeneral.value = generalRes.data.logs.reverse().slice(0, 200);
      logsSensors.value = sensorsRes.data.logs.reverse().slice(0, 200);
      logsPeople.value = peopleRes.data.logs.reverse().slice(0, 200);
      logsAudio.value = audioRes.data.logs.reverse().slice(0, 200);
    } catch (error) {
      console.error('Eroare la încărcarea logurilor:', error);
      toast.error('Eroare la încărcarea logurilor');
    }
  };

  fetchLogs();
  setInterval(fetchLogs, 5000);

  socket.on('disconnect', () => {
    console.log('Deconectat de la server WebSocket');
    store.commit('setWaveformData', {input: [], output: [], anomalies: []});
    store.commit('setSensors', {distances: ['Eroare', 'Eroare', 'Eroare', 'Eroare'], positions: []});
    peopleCount.value = 0;
    peoplePositions.value = [];
    audioAmplitude.value = 0;
    micWaveformData.value = [];
    logsGeneral.value = [];
    logsSensors.value = [];
    logsPeople.value = [];
    logsAudio.value = [];
  });
});

onUnmounted(() => socket.disconnect());

const toggleProcessing = async () => {
  try {
    const res = await axios.post('http://192.168.3.28:5500/toggle');
    store.commit('setRunning', res.data.running);
    toast.success(res.data.running ? 'Procesare pornită' : 'Procesare oprită');
  } catch (error) {
    console.error('Eroare la toggle:', error);
    toast.error('Eroare la toggle procesare');
  }
};
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
}

.start-stop {
  padding: 10px 20px;
  margin-right: 10px;
  background-color: #007bff;
  color: #fff;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  transition: background-color 0.3s, transform 0.2s;
}

.start-stop:hover {
  background-color: #0056b3;
  transform: translateY(-2px);
}

.chart-container {
  display: flex;
  justify-content: space-between;
  margin-bottom: 20px;
  gap: 20px;
}

.eq-chart-container {
  margin-bottom: 20px;
}

.audio-chart-container {
  margin-bottom: 20px;
}

.chart-box {
  width: 48%;
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
}

.chart {
  height: 300px;
}

.logs-container {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 20px;
}

.logs-box {
  width: 48%;
  padding: 15px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.05);
  transform: perspective(500px) rotateX(5deg);
  transition: transform 0.3s;
}

.logs-box:hover {
  transform: perspective(500px) rotateX(0deg);
}

.section-title {
  text-align: center;
  color: #333;
  margin-bottom: 10px;
}

.stats-list, .sensors-list, .log-list {
  list-style: none;
  padding: 0;
  max-height: 250px;
  overflow-y: auto;
}

.stats-list li, .sensors-list li, .log-item {
  margin-bottom: 10px;
  padding: 5px;
  background: #f9f9f9;
  border-radius: 4px;
  transition: background 0.3s;
}

.stats-list li:hover, .sensors-list li:hover, .log-item:hover {
  background: #e9ecef;
}

.sensors-section {
  position: relative;
}

.sensors-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.room-map {
  position: relative;
  width: 200px;
  height: 200px;
  border: 2px solid #ccc;
  background: linear-gradient(45deg, #fff, #f0f4f8);
  margin-left: 20px;
  border-radius: 8px;
  box-shadow: inset 0 2px 5px rgba(0, 0, 0, 0.1);
}

.sensor-marker {
  position: absolute;
  width: 10px;
  height: 10px;
  background-color: red;
  border-radius: 50%;
  transition: transform 0.2s;
}

.sensor-marker:hover {
  transform: scale(1.2);
}

.sensor-marker:hover::after {
  content: attr(data-distance);
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

.speaker-marker {
  position: absolute;
  width: 12px;
  height: 12px;
  background-color: blue;
  border-radius: 50%;
  transition: transform 0.2s;
}

.speaker-marker:hover {
  transform: scale(1.2);
}

.speaker-center-marker {
  position: absolute;
  width: 8px;
  height: 8px;
  background-color: gray;
  border-radius: 50%;
  border: 1px solid black;
}

.person-marker {
  position: absolute;
  width: 8px;
  height: 8px;
  background-color: green;
  border-radius: 50%;
  transition: transform 0.2s;
}

.person-marker:hover {
  transform: scale(1.2);
}

.logs-section {
  width: 100%;
}

.tabs {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
  justify-content: center;
}

.tabs button {
  padding: 8px 15px;
  border: 1px solid #ccc;
  background-color: #f1f1f1;
  cursor: pointer;
  border-radius: 5px;
  transition: all 0.3s;
}

.tabs button.active {
  background-color: #007bff;
  color: #fff;
  border-color: #007bff;
  transform: translateY(-2px);
}

.log-content {
  border: 1px solid #ccc;
  padding: 10px;
  max-height: 250px;
  overflow-y: auto;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.05);
}

.log-content ul {
  list-style: none;
  padding: 0;
}

@media (max-width: 768px) {
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

  .logs-section {
    width: 100%;
  }

  .chart-container {
    flex-direction: column;
  }

  .chart-box {
    width: 100%;
  }

  .eq-chart-container {
    margin-top: 20px;
  }

  .audio-chart-container {
    margin-top: 20px;
  }
}
</style>