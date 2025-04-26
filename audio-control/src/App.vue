<template>
  <div class="container">
    <h1>Audio Control Panel</h1>

    <div class="control-form">
      <label>
        Delay Left:
        <input
            type="number"
            min="0"
            max="50"
            v-model.number="delayL"
        />
      </label>
      <br />
      <label>
        Delay Right:
        <input
            type="number"
            min="0"
            max="50"
            v-model.number="delayR"
        />
      </label>
      <br />
      <div class="button-group">
        <button @click="toggleProcessing" class="start-stop">
          {{ running ? 'Stop' : 'Start' }}
        </button>
        <button @click="updateParams" class="update">
          Update
        </button>
      </div>
    </div>

    <div class="chart-container">
      <div class="chart-box">
        <h2>Input</h2>
        <Chart type="line" :data="inputChartData" :options="chartOptions" class="chart" />
      </div>
      <div class="chart-box">
        <h2>Output</h2>
        <Chart type="line" :data="outputChartData" :options="chartOptions" class="chart" />
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
import { computed, onMounted, onUnmounted, watch } from 'vue';
import axios from 'axios';
import { useToast } from '@brackets/vue-toastification';

// Înregistrăm componentele Chart.js
ChartJS.register(LineElement, PointElement, LinearScale, Title, CategoryScale);

// Vuex store
const store = useStore();
const running = computed(() => store.state.running);
const delayL = computed({
  get: () => store.state.delayL,
  set: (value) => store.commit('setDelayL', value)
});
const delayR = computed({
  get: () => store.state.delayR,
  set: (value) => store.commit('setDelayR', value)
});
const waveformData = computed(() => store.state.waveformData);
const logs = computed(() => store.state.logs);

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
    ],
  };
});

const chartOptions = {
  animation: false,
  maintainAspectRatio: false,
  scales: {
    x: { display: false },
    y: { min: -32768, max: 32767 },
  },
};

// Funcții pentru cereri HTTP
const fetchWaveformData = async () => {
  const maxRetries = 3;
  let retries = 0;

  while (retries < maxRetries) {
    try {
      const [inputRes, outputRes] = await Promise.all([
        axios.get('http://192.168.3.28:5500/data_input'),
        axios.get('http://192.168.3.28:5500/data_output'),
      ]);
      store.commit('setWaveformData', {
        input: inputRes.data.input || [],
        output: outputRes.data.output || [],
      });
      return;
    } catch (error) {
      retries++;
      console.error(`Eroare la polling waveform (încercarea ${retries}/${maxRetries}):`, error);
      if (retries === maxRetries) {
        console.error('Maxim de încercări atins. Polling oprit temporar.');
        toast.error('Eroare la obținerea datelor waveform');
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
};

const fetchLogs = async () => {
  const maxRetries = 3;
  let retries = 0;

  while (retries < maxRetries) {
    try {
      const res = await axios.get('http://192.168.3.28:5500/logs');
      store.commit('setLogs', res.data);
      return;
    } catch (error) {
      retries++;
      console.error(`Eroare la obținerea logurilor (încercarea ${retries}/${maxRetries}):`, error);
      if (retries === maxRetries) {
        console.error('Maxim de încercări atins pentru loguri.');
        toast.error('Eroare la obținerea logurilor');
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
};


// Controlează polling-ul în funcție de running
let waveformInterval = null;
let logsInterval = null;
let shairportInterval = null;

const startPolling = () => {
  if (waveformInterval) clearInterval(waveformInterval);
  if (logsInterval) clearInterval(logsInterval);
  if (shairportInterval) clearInterval(shairportInterval);
  waveformInterval = setInterval(fetchWaveformData, 100);
  logsInterval = setInterval(fetchLogs, 1000);
};

const stopPolling = () => {
  if (waveformInterval) {
    clearInterval(waveformInterval);
    waveformInterval = null;
  }
  if (logsInterval) {
    clearInterval(logsInterval);
    logsInterval = null;
  }
  if (shairportInterval) {
    clearInterval(shairportInterval);
    shairportInterval = null;
  }
  store.commit('setWaveformData', { input: [], output: [] });
};

// Monitorizăm starea running
watch(running, (newValue) => {
  if (newValue) {
    startPolling();
  } else {
    stopPolling();
  }
});

// Începe polling-ul la montare dacă running este true
onMounted(() => {
  if (running.value) startPolling();
});

// Oprește polling-ul la demontare
onUnmounted(() => {
  stopPolling();
});

// Funcții pentru cereri HTTP
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

const updateParams = async () => {
  const params = {delay_l: delayL.value, delay_r: delayR.value};
  try {
    await axios.post('http://192.168.3.28:5500/update', params);
    toast.success('Parametrii au fost actualizați');
  } catch (error) {
    console.error('Eroare la update:', error);
    toast.error('Eroare la actualizarea parametrilor');
  }
};
</script>