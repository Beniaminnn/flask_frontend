<template>
  <div class="container">
    <h1>Audio and Sensor Control Panel</h1>

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
      <div class="logs-box">
        <h2>Sensor Distances</h2>
        <div class="sensors-content">
          <ul>
            <li>Dreapta: {{ sensors.Dreapta }} cm</li>
            <li>Stânga: {{ sensors.Stânga }} cm</li>
            <li>Față: {{ sensors.Față }} cm</li>
            <li>Spate: {{ sensors.Spate }} cm</li>
          </ul>
          <div class="room-map">
            <div class="sensor-marker" id="sensor-fata" :data-distance="sensors.Față + ' cm'" style="top: 0; left: 50%; transform: translateX(-50%);"></div>
            <div class="sensor-marker" id="sensor-spate" :data-distance="sensors.Spate + ' cm'" style="bottom: 0; left: 50%; transform: translateX(-50%);"></div>
            <div class="sensor-marker" id="sensor-stanga" :data-distance="sensors.Stânga + ' cm'" style="top: 50%; left: 0; transform: translateY(-50%);"></div>
            <div class="sensor-marker" id="sensor-dreapta" :data-distance="sensors.Dreapta + ' cm'" style="top: 50%; right: 0; transform: translateY(-50%);"></div>
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
  set: (value) => store.commit('setDelayL', value),
});
const delayR = computed({
  get: () => store.state.delayR,
  set: (value) => store.commit('setDelayR', value),
});
const waveformData = computed(() => store.state.waveformData);
const logs = computed(() => store.state.logs);
const sensors = computed(() => store.state.sensors);

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

// Calculează amplitudinea maximă cu o marjă
const getDynamicRange = (data) => {
  if (!data || data.length === 0) {
    return { min: -35000, max: 35000 }; // Valori implicite dacă nu sunt date
  }
  const maxAmplitude = Math.max(...data.map(Math.abs));
  const margin = maxAmplitude * 0.1; // Marjă de 10%
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
  };
});

// Funcții pentru cereri HTTP
const fetchWaveformData = async () => {
  const maxRetries = 3;
  let retries = 0;

  while (retries < maxRetries) {
    try {
      const [inputRes, outputRes] = await Promise.all([
        axios.get('http://raspberrypi.local:5500/data_input'),
        axios.get('http://raspberrypi.local:5500/data_output'),
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
      const res = await axios.get('http://raspberrypi.local:5500/logs');
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

const fetchSensors = async () => {
  const maxRetries = 3;
  let retries = 0;

  while (retries < maxRetries) {
    try {
      const res = await axios.get('http://raspberrypi.local:5500/sensors');
      store.commit('setSensors', res.data);
      return;
    } catch (error) {
      retries++;
      console.error(`Eroare la obținerea datelor senzorilor (încercarea ${retries}/${maxRetries}):`, error);
      if (retries === maxRetries) {
        console.error('Maxim de încercări atins pentru senzori.');
        toast.error('Eroare la obținerea datelor senzorilor');
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
};

// Controlează polling-ul
let waveformInterval = null;
let logsInterval = null;
let sensorsInterval = null;

const startPolling = () => {
  if (waveformInterval) clearInterval(waveformInterval);
  if (logsInterval) clearInterval(logsInterval);
  if (sensorsInterval) clearInterval(sensorsInterval);
  waveformInterval = setInterval(fetchWaveformData, 40);
  logsInterval = setInterval(fetchLogs, 500);
  sensorsInterval = setInterval(fetchSensors, 2000);
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
  if (sensorsInterval) {
    clearInterval(sensorsInterval);
    sensorsInterval = null;
  }
  store.commit('setWaveformData', {input: [], output: []});
  store.commit('setSensors', {Dreapta: 'Eroare', Stânga: 'Eroare', Față: 'Eroare', Spate: 'Eroare'});
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
    const res = await axios.post('http://raspberrypi.local:5500/toggle');
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
    await axios.post('http://raspberrypi.local:5500/update', params);
    toast.success('Parametrii au fost actualizați');
  } catch (error) {
    console.error('Eroare la update:', error);
    toast.error('Eroare la actualizarea parametrilor');
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

.start-stop,
.update {
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
</style>