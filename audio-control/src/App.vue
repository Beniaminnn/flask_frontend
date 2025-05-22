<template>
  <div class="container">
    <h1>Audio and Sensor Control Panel</h1>

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

      <div class="button-group">
        <button @click="toggleProcessing" class="start-stop">
          {{ running ? 'Stop' : 'Start' }}
        </button>
      </div>
    </div>

    <div class="chart-container">
      <div class="chart-box">
        <h2>Input</h2>
        <Chart type="line" :data="inputChartData" :options="inputChartOptions" class="chart" />
      </div>
      <div class="chart-box">
        <h2>Output</h2>
        <Chart type="line" :data="outputChartData" :options="outputChartOptions" class="chart" />
      </div>
    </div>

    <div class="logs-container">
      <div class="logs-box">
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
      <div class="logs-box sensors-section">
        <h2>Sensor Distances</h2>
        <div class="sensors-content">
          <ul>
            <li>Dreapta: {{ sensors.Dreapta }} cm</li>
            <li>Stânga: {{ sensors.Stânga }} cm</li>
            <li>Față: {{ sensors.Față }} cm</li>
            <li>Spate: {{ sensors.Spate }} cm</li>
            <li>Persoane detectate: {{ peopleCount }}</li>
          </ul>
          <div class="room-map">
            <!-- Sensor markers -->
            <div class="sensor-marker" id="sensor-fata" :data-distance="sensors.Față + ' cm'" style="top: 0; left: 50%; transform: translateX(-50%);"></div>
            <div class="sensor-marker" id="sensor-spate" :data-distance="sensors.Spate + ' cm'" style="bottom: 0; left: 50%; transform: translateX(-50%);"></div>
            <div class="sensor-marker" id="sensor-stanga" :data-distance="sensors.Stânga + ' cm'" style="top: 50%; left: 0; transform: translateY(-50%);"></div>
            <div class="sensor-marker" id="sensor-dreapta" :data-distance="sensors.Dreapta + ' cm'" style="top: 50%; right: 0; transform: translateY(-50%);"></div>
            <!-- Speaker marker -->
            <div
                class="speaker-marker"
                id="speaker"
                :style="getSpeakerPositionStyle(speakerPos)"
            ></div>
            <div class="speaker-center-marker" style="left: 50%; top: 50%; transform: translate(-50%, -50%);"></div>
            <!-- People markers -->
            <div
                v-for="(person, index) in peoplePositions"
                :key="index"
                class="person-marker"
                :style="getPersonPositionStyle(person)"
            ></div>
          </div>
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
import { computed, onMounted, onUnmounted, ref } from 'vue';
import axios from 'axios';
import { useToast } from '@brackets/vue-toastification';
import { io } from 'socket.io-client';

// Înregistrăm componentele Chart.js
ChartJS.register(LineElement, PointElement, LinearScale, Title, CategoryScale);

// Vuex store
const store = useStore();
const running = computed(() => store.state.running);
const delayL = computed(() => store.state.delayL);
const delayR = computed(() => store.state.delayR);
const waveformData = computed(() => store.state.waveformData);
const logs = computed(() => store.state.logs);
const sensors = computed(() => store.state.sensors);

// Date despre persoane și boxă
const peopleCount = ref(0);
const peoplePositions = ref([]);
const speakerPos = ref({ x: 200, y: 200 });

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
  const downsampled = [];
  for (let i = 0; i < data.length; i += step) {
    downsampled.push(data[i]);
    if (downsampled.length >= maxPoints) break;
  }
  return downsampled;
};

// Subeșantionează indicii anomaliilor
const downsampleAnomalies = (indices, dataLength, maxPoints) => {
  if (dataLength <= maxPoints) return indices;
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
  const margin = maxAmplitude * 0.1;
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
        borderColor: 'blue',
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
        borderColor: 'green',
        fill: false,
        pointRadius: 0,
      },
      {
        label: 'Anomalies',
        data: downsampledAnomalies.map(idx => ({ x: idx, y: getDynamicRange(downsampledData).max * 0.9 })),
        borderColor: 'red',
        backgroundColor: 'rgba(255, 0, 0, 0.3)',
        pointRadius: 2,
        pointHoverRadius: 5,
        fill: false,
        showLine: false,
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
      },
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
      },
    },
    plugins: {
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
const socket = io('http://raspberrypi.local:5500');

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
  });

  socket.on('people', (data) => {
    peopleCount.value = data.count;
    peoplePositions.value = data.positions;
  });

  socket.on('params', (data) => {
    store.commit('setDelayL', data.delay_l);
    store.commit('setDelayR', data.delay_r);
    store.commit('setRunning', data.running);
  });

  socket.on('speaker_position', (data) => {
    speakerPos.value = { x: data.x, y: data.y };
  });

  socket.on('logs', (data) => {
    store.commit('setLogs', data);
  });

  socket.on('disconnect', () => {
    console.log('Deconectat de la server WebSocket');
    store.commit('setWaveformData', { input: [], output: [], anomalies: [] });
    store.commit('setSensors', { Dreapta: 'Eroare', Stânga: 'Eroare', Față: 'Eroare', Spate: 'Eroare' });
    peopleCount.value = 0;
    peoplePositions.value = [];
  });
});

onUnmounted(() => {
  socket.disconnect();
});

// Funcție pentru toggle procesare
const toggleProcessing = async () => {
  try {
    const res = await axios.post('http://raspberrypi.local:5500/toggle');
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
}

.control-form {
  margin-bottom: 20px;
}

.button-group {
  margin-top: 10px;
}

.start-stop {
  padding: 10px 20px;
  margin-right: 10px;
}

.chart-container {
  display: flex;
  justify-content: space-between;
  margin-bottom: 20px;
}

.chart-box {
  width: 48%;
}

.chart {
  height: 300px;
}

.logs-container {
  display: flex;
  justify-content: space-between;
}

.logs-box {
  width: 48%;
}

.logs-box ul {
  list-style: none;
  padding: 0;
}

.logs-box li {
  margin-bottom: 10px;
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
  border: 1px solid #ccc;
  background-color: #f9f9f9;
  margin-left: 20px;
}

.sensor-marker {
  position: absolute;
  width: 10px;
  height: 10px;
  background-color: red;
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
  background-color: blue;
  border-radius: 50%;
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
}
</style>