<template>
  <div class="container">
    <h1 class="title">Audio and Sensor Control Panel</h1>

    <div class="control-panel">
      <div class="delay-controls">
        <label>
          Delay Left: <span class="value">{{ delayL }} ms</span>
        </label>
        <label>
          Delay Right: <span class="value">{{ delayR }} ms</span>
        </label>
      </div>
      <div class="button-group">
        <button @click="toggleProcessing" class="start-stop">
          {{ running ? 'Stop' : 'Start' }}
        </button>
      </div>
    </div>

    <div class="chart-container">
      <div class="chart-box">
        <h2>Input Waveform</h2>
        <Chart type="line" :data="inputChartData" :options="inputChartOptions" class="chart" />
      </div>
      <div class="chart-box">
        <h2>Output Waveform</h2>
        <Chart type="line" :data="outputChartData" :options="outputChartOptions" class="chart" />
      </div>
      <div class="chart-box">
        <h2>Microfon Waveform</h2>
        <Chart type="line" :data="micChartData" :options="micChartOptions" class="chart" />
      </div>
    </div>

    <div class="stats-container">
      <div class="stats-box">
        <h2>Raspberry Pi Stats</h2>
        <ul>
          <li>Input Max Amplitude: {{ logs.input_max_amplitude }}</li>
          <li>Output Max Amplitude: {{ logs.output_max_amplitude }}</li>
          <li>Temperature: {{ logs.temperature }}</li>
          <li>CPU Load: {{ logs.cpu_load }}%</li>
          <li>Wi-Fi SSID: {{ logs.wifi_ssid }}</li>
          <li>Wi-Fi Signal: {{ logs.wifi_signal }} dBm</li>
        </ul>
      </div>
      <div class="stats-box sensor-section">
        <h2>Sensor Distances</h2>
        <div class="sensors-content">
          <ul>
            <li>Dreapta: {{ sensors.Dreapta }} cm</li>
            <li>Stânga: {{ sensors.Stânga }} cm</li>
            <li>Față: {{ sensors.Față }} cm</li>
            <li>Spate: {{ sensors.Spate }} cm</li>
            <li>Microfon: {{ sensors.Microfon }} (unități)</li>
            <li>Persoane detectate: {{ peopleCount }}</li>
          </ul>
          <div class="room-map">
            <div class="sensor-marker" id="sensor-fata" :data-distance="sensors.Față + ' cm'" style="top: 0; left: 50%; transform: translateX(-50%);"></div>
            <div class="sensor-marker" id="sensor-spate" :data-distance="sensors.Spate + ' cm'" style="bottom: 0; left: 50%; transform: translateX(-50%);"></div>
            <div class="sensor-marker" id="sensor-stanga" :data-distance="sensors.Stânga + ' cm'" style="top: 50%; left: 0; transform: translateY(-50%);"></div>
            <div class="sensor-marker" id="sensor-dreapta" :data-distance="sensors.Dreapta + ' cm'" style="top: 50%; right: 0; transform: translateY(-50%);"></div>
            <div class="speaker-marker" id="speaker" :style="getSpeakerPositionStyle(speakerPos)"></div>
            <div class="speaker-center-marker" style="left: 50%; top: 50%; transform: translate(-50%, -50%);"></div>
            <div v-for="(person, index) in peoplePositions" :key="index" class="person-marker" :style="getPersonPositionStyle(person)"></div>
          </div>
        </div>
      </div>
    </div>

    <div class="logs-container">
      <div class="log-box" v-if="sensorLogs.length">
        <h2>Date despre Senzori</h2>
        <ul class="scrollable-logs">
          <li v-for="(log, index) in sensorLogs" :key="index">{{ log }}</li>
        </ul>
      </div>
      <div class="log-box" v-if="peopleLogs.length">
        <h2>Persoană Detectată</h2>
        <ul class="scrollable-logs">
          <li v-for="(log, index) in peopleLogs" :key="index">{{ log }}</li>
        </ul>
      </div>
      <div class="log-box" v-if="speakerPositionLogs.length">
        <h2>Calculate Speaker Position</h2>
        <ul class="scrollable-logs">
          <li v-for="(log, index) in speakerPositionLogs" :key="index">{{ log }}</li>
        </ul>
      </div>
      <div class="log-box" v-if="timeAlignmentLogs.length">
        <h2>Adjust Time Alignment</h2>
        <ul class="scrollable-logs">
          <li v-for="(log, index) in timeAlignmentLogs" :key="index">{{ log }}</li>
        </ul>
      </div>
      <div class="log-box" v-if="audioModificationsLogs.length">
        <h2>Modificări ale Sunetului</h2>
        <ul class="scrollable-logs">
          <li v-for="(log, index) in audioModificationsLogs" :key="index">{{ log }}</li>
        </ul>
      </div>
      <div class="log-box" v-if="generalLogs.length">
        <h2>Loguri Generale</h2>
        <ul class="scrollable-logs">
          <li v-for="(log, index) in generalLogs" :key="index">{{ log }}</li>
        </ul>
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
import { computed, onMounted, onUnmounted, ref } from 'vue';
import axios from 'axios';
import { useToast } from '@brackets/vue-toastification';
import { io } from 'socket.io-client';

// Înregistrăm componentele Chart.js
ChartJS.register(LineElement, PointElement, LinearScale, Title, CategoryScale);

// Inițializează store-ul
const store = useStore();

// Computed properties
const running = computed(() => store.state.running);
const delayL = computed(() => store.state.delayL);
const delayR = computed(() => store.state.delayR);
const waveformData = computed(() => store.state.waveformData);
const logs = computed(() => store.state.logs);
const sensors = computed(() => {
  const data = store.state.sensors;
  return {
    Dreapta: data[0] !== undefined && data[0] !== "Eroare" && data[0] !== -1.0 ? data[0] : 'Eroare',
    Stânga: data[1] !== undefined && data[1] !== "Eroare" && data[1] !== -1.0 ? data[1] : 'Eroare',
    Față: data[2] !== undefined && data[2] !== "Eroare" && data[2] !== -1.0 ? data[2] : 'Eroare',
    Spate: data[3] !== undefined && data[3] !== "Eroare" && data[3] !== -1.0 ? data[3] : 'Eroare',
    Microfon: data[4] !== undefined && data[4] !== "Eroare" && data[4] !== -1.0 ? data[4] : 'Eroare',
  };
});

// Date despre persoane și boxă
const peopleCount = ref(0);
const peoplePositions = ref([]);
const speakerPos = ref({ x: 200, y: 200 });

// Loguri separate
const debugLogs = ref([]);
const sensorLogs = ref([]);
const peopleLogs = ref([]);
const speakerPositionLogs = ref([]);
const timeAlignmentLogs = ref([]);
const audioModificationsLogs = ref([]);
const generalLogs = ref([]);

// Inițializează toast
const toast = useToast();

// Numărul maxim de puncte de afișat în grafic
const MAX_POINTS = 400;

// Stocarea datelor microfonului pentru waveform
const micData = ref([]);

// Funcție pentru subeșantionare
const downsample = (data, maxPoints) => {
  if (!data || data.length <= 0) return [];
  if (data.length <= maxPoints) return data;
  const step = Math.floor(data.length / maxPoints);
  const downsampled = [];
  for (let i = 0; i < data.length; i += step) {
    downsampled.push(data[i]);
    if (downsampled.length >= maxPoints) break;
  }
  return downsampled;
};

// Subeșantionează indicii anomaliilor
const downsampleAnomalies = (indices, dataLength, maxPoints) => {
  if (!indices || dataLength <= 0 || dataLength <= maxPoints) return [];
  const step = Math.floor(dataLength / maxPoints);
  const downsampledIndices = [];
  indices.forEach(idx => {
    const downsampledIdx = Math.floor(idx / step);
    if (downsampledIdx < maxPoints && !downsampledIndices.includes(downsampledIdx)) {
      downsampledIndices.push(downsampledIdx);
    }
  });
  return downsampledIndices;
};

// Calculează amplitudinea maximă cu o marjă
const getDynamicRange = (data) => {
  if (!data || data.length === 0) {
    return { min: -35000, max: 35000 };
  }
  const maxAmplitude = Math.max(...data.map(Math.abs));
  const margin = maxAmplitude * 0.1 || 3500;
  return {
    min: -maxAmplitude - margin,
    max: maxAmplitude + margin,
  };
};

// Configurare grafice
const inputChartData = computed(() => {
  const downsampledData = downsample(waveformData.value.input, MAX_POINTS);
  return {
    labels: Array(downsampledData.length).fill(''),
    datasets: [
      {
        label: 'Input',
        data: downsampledData,
        borderColor: '#0000FF',
        fill: false,
        pointRadius: 0,
      },
    ],
  };
});

const outputChartData = computed(() => {
  const downsampledData = downsample(waveformData.value.output, MAX_POINTS);
  const downsampledAnomalies = downsampleAnomalies(waveformData.value.anomalies || [], waveformData.value.output.length, MAX_POINTS);
  return {
    labels: Array(downsampledData.length).fill(''),
    datasets: [
      {
        label: 'Output',
        data: downsampledData,
        borderColor: '#00FF00',
        fill: false,
        pointRadius: 0,
      },
      {
        label: 'Anomalies',
        data: downsampledAnomalies.map(idx => ({ x: idx, y: getDynamicRange(downsampledData).max * 0.9 })),
        borderColor: '#FF0000',
        backgroundColor: 'rgba(255, 0, 0, 0.3)',
        pointRadius: 2,
        pointHoverRadius: 5,
        fill: false,
        showLine: false,
      },
    ],
  };
});

const micChartData = computed(() => {
  const downsampledData = downsample(micData.value, MAX_POINTS);
  return {
    labels: Array(downsampledData.length).fill(''),
    datasets: [
      {
        label: 'Microfon',
        data: downsampledData,
        borderColor: '#FF4500', // Portocaliu pentru microfon
        fill: false,
        pointRadius: 0,
      },
    ],
  };
});

// Opțiuni grafice cu axa Y dinamică
const inputChartOptions = computed(() => {
  const range = getDynamicRange(waveformData.value.input);
  return {
    animation: false,
    maintainAspectRatio: false,
    scales: {
      x: { display: false },
      y: {
        min: range.min,
        max: range.max,
        ticks: { color: '#000000' },
      },
    },
    plugins: {
      legend: { labels: { color: '#000000' } },
    },
  };
});

const outputChartOptions = computed(() => {
  const range = getDynamicRange(waveformData.value.output);
  return {
    animation: false,
    maintainAspectRatio: false,
    scales: {
      x: { display: false },
      y: {
        min: range.min,
        max: range.max,
        ticks: { color: '#000000' },
      },
    },
    plugins: {
      legend: { labels: { color: '#000000' } },
      tooltip: {
        callbacks: {
          label: (context) => {
            if (context.dataset.label === 'Anomalies') {
              return 'Anomaly detected';
            }
            return `${context.dataset.label}: ${context.parsed.y}`;
          },
        },
      },
    },
  };
});

const micChartOptions = computed(() => {
  const range = getDynamicRange(micData.value);
  return {
    animation: false,
    maintainAspectRatio: false,
    scales: {
      x: { display: false },
      y: {
        min: range.min,
        max: range.max,
        ticks: { color: '#000000' },
      },
    },
    plugins: {
      legend: { labels: { color: '#000000' } },
    },
  };
});

// Calculează poziția persoanelor pe hartă
const getPersonPositionStyle = (person) => {
  const mapSize = 200;
  const roomSize = 400;
  const xPixel = (person.x / roomSize) * mapSize;
  const yPixel = (person.y / roomSize) * mapSize;
  return {
    left: `${xPixel}px`,
    top: `${yPixel}px`,
    transform: 'translate(-50%, -50%)',
  };
};

// Calculează poziția boxei pe hartă
const getSpeakerPositionStyle = (pos) => {
  const mapSize = 200;
  const roomSize = 400;
  const xPixel = (pos.x / roomSize) * mapSize;
  const yPixel = (pos.y / roomSize) * mapSize;
  return {
    left: `${xPixel}px`,
    top: `${yPixel}px`,
    transform: 'translate(-50%, -50%)',
  };
};

// Configurare WebSocket
const socket = io('http://192.168.3.28:5500');

onMounted(() => {
  socket.on('connect', () => {
    console.log('Conectat la server WebSocket');
  });

  socket.on('data_input', (data) => {
    store.commit('setWaveformData', { input: data.input || [], output: waveformData.value.output, anomalies: waveformData.value.anomalies });
  });

  socket.on('data_output', (data) => {
    store.commit('setWaveformData', { input: waveformData.value.input, output: data.output || [], anomalies: data.anomalies || [] });
  });

  socket.on('sensors', (data) => {
    store.commit('setSensors', data);
    // Actualizează waveform-ul microfonului cu valorile din sensors.Microfon
    micData.value = [data[4]]; // Adaugă doar ultima valoare ca punct de pornire
  });

  socket.on('people', (data) => {
    peopleCount.value = data.count;
    peoplePositions.value = data.positions || [];
  });

  socket.on('params', (data) => {
    store.commit('setDelayL', data.delay_l || 0);
    store.commit('setDelayR', data.delay_r || 0);
    store.commit('setRunning', data.running || false);
  });

  socket.on('speaker_position', (data) => {
    speakerPos.value = { x: data.x || 200, y: data.y || 200 };
  });

  socket.on('logs', (data) => {
    store.commit('setLogs', data || {});
  });

  // Fetch debug logs periodically
  const fetchDebugLogs = async () => {
    try {
      const response = await axios.get('http://192.168.3.28:5500/debug_logs');
      debugLogs.value = response.data.debug_logs || [];

      sensorLogs.value = debugLogs.value.filter(log => log.includes('[Date despre senzori:'));
      peopleLogs.value = debugLogs.value.filter(log => log.includes('[Persoană detectată'));
      speakerPositionLogs.value = debugLogs.value.filter(log => log.includes('[Calculate speaker position:'));
      timeAlignmentLogs.value = debugLogs.value.filter(log => log.includes('[Adjust time alignment:'));
      audioModificationsLogs.value = debugLogs.value.filter(log => log.includes('[Modificări ale sunetului:'));
      generalLogs.value = debugLogs.value.filter(log =>
          !log.includes('[Date despre senzori:') &&
          !log.includes('[Persoană detectată') &&
          !log.includes('[Calculate speaker position:') &&
          !log.includes('[Adjust time alignment:') &&
          !log.includes('[Modificări ale sunetului:'));
    } catch (error) {
      console.error('Eroare la obținerea logurilor:', error);
    }
  };

  fetchDebugLogs(); // Inițializare
  setInterval(fetchDebugLogs, 5000); // Actualizare la fiecare 5 secunde

  socket.on('disconnect', () => {
    console.log('Deconectat de la server WebSocket');
    store.commit('setWaveformData', { input: [], output: [], anomalies: [] });
    store.commit('setSensors', ["Eroare", "Eroare", "Eroare", "Eroare", "Eroare"]);
    peopleCount.value = 0;
    peoplePositions.value = [];
    speakerPos.value = { x: 200, y: 200 };
    micData.value = [];
  });
});

onUnmounted(() => {
  socket.disconnect();
});

// Funcție pentru toggle procesare
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
  background-color: #f9f9f9;
  border-radius: 10px;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
}

.title {
  text-align: center;
  color: #333;
  margin-bottom: 20px;
}

.control-panel {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #e0e0e0;
  padding: 15px;
  border-radius: 8px;
  margin-bottom: 20px;
}

.delay-controls {
  display: flex;
  gap: 20px;
}

.delay-controls label {
  font-size: 16px;
  color: #444;
}

.value {
  font-weight: bold;
  color: #000;
}

.button-group {
  margin-top: 0;
}

.start-stop {
  padding: 10px 20px;
  background-color: #4CAF50;
  color: white;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-size: 16px;
}

.start-stop:hover {
  background-color: #45a049;
}

.chart-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.chart-box {
  background-color: #fff;
  padding: 15px;
  border-radius: 8px;
  box-shadow: 0 0 5px rgba(0, 0, 0, 0.1);
}

.chart-box h2 {
  color: #333;
  margin-bottom: 10px;
}

.chart {
  height: 200px;
  width: 100%;
}

.stats-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.stats-box {
  background-color: #fff;
  padding: 15px;
  border-radius: 8px;
  box-shadow: 0 0 5px rgba(0, 0, 0, 0.1);
}

.stats-box h2 {
  color: #333;
  margin-bottom: 10px;
}

.stats-box ul {
  list-style: none;
  padding: 0;
}

.stats-box li {
  margin-bottom: 10px;
  color: #555;
}

.sensor-section .sensors-content {
  display: flex;
  gap: 20px;
}

.room-map {
  position: relative;
  width: 200px;
  height: 200px;
  border: 2px solid #ccc;
  background-color: #f0f0f0;
  border-radius: 5px;
}

.sensor-marker {
  position: absolute;
  width: 10px;
  height: 10px;
  background-color: #FF0000;
  border-radius: 50%;
}

.sensor-marker:hover::after {
  content: attr(data-distance);
  position: absolute;
  top: -20px;
  left: 50%;
  transform: translateX(-50%);
  background-color: #333;
  color: #fff;
  padding: 2px 5px;
  border-radius: 3px;
  font-size: 12px;
  white-space: nowrap;
}

.speaker-marker {
  position: absolute;
  width: 12px;
  height: 12px;
  background-color: #0000FF;
  border-radius: 50%;
}

.speaker-center-marker {
  position: absolute;
  width: 8px;
  height: 8px;
  background-color: #808080;
  border-radius: 50%;
  border: 1px solid #000;
}

.person-marker {
  position: absolute;
  width: 8px;
  height: 8px;
  background-color: #00FF00;
  border-radius: 50%;
}

.logs-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
}

.log-box {
  background-color: #fff;
  padding: 15px;
  border-radius: 8px;
  box-shadow: 0 0 5px rgba(0, 0, 0, 0.1);
}

.log-box h2 {
  color: #333;
  margin-bottom: 10px;
}

.scrollable-logs {
  max-height: 200px;
  overflow-y: auto;
  list-style: none;
  padding: 0;
  margin: 0;
}

.scrollable-logs li {
  margin-bottom: 5px;
  padding: 5px;
  background-color: #f9f9f9;
  border-radius: 3px;
  color: #444;
}

@media (max-width: 768px) {
  .control-panel {
    flex-direction: column;
    gap: 10px;
  }

  .chart-container, .stats-container, .logs-container {
    grid-template-columns: 1fr;
  }

  .sensor-section .sensors-content {
    flex-direction: column;
    align-items: center;
  }

  .room-map {
    margin-top: 10px;
  }
}
</style>