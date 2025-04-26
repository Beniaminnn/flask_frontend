<template>
  <div class="p-4 max-w-4xl mx-auto">
    <h1 class="text-2xl mb-4">Audio Control Panel</h1>

    <div class="mb-4">
      <label>
        Delay Left:
        <input
            type="number"
            min="0"
            max="50"
            v-model.number="delayL"
            class="ml-2 border p-1"
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
            class="ml-2 border p-1"
        />
      </label>
      <br />
      <button @click="toggleProcessing" class="mt-2 p-2 bg-blue-500 text-white">
        {{ running ? 'Stop' : 'Start' }}
      </button>
      <button @click="updateParams" class="mt-2 ml-2 p-2 bg-green-500 text-white">
        Update
      </button>
    </div>

    <div class="mb-4">
      <label>
        <input type="radio" v-model="showInput" :value="true" /> Input
      </label>
      <label class="ml-4">
        <input type="radio" v-model="showInput" :value="false" /> Output
      </label>
      <div class="h-48">
        <Chart type="line" :data="chartData" :options="chartOptions" />
      </div>
    </div>

    <div class="mb-4">
      <h2 class="text-xl mb-2">Waveform Data</h2>
      <p><strong>Input:</strong> {{ waveformData.input.slice(0, 10) }}...</p>
      <p><strong>Output:</strong> {{ waveformData.output.slice(0, 10) }}...</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { Chart } from 'vue-chartjs';
import {
  Chart as ChartJS,
  LineElement,
  PointElement,
  LinearScale,
  Title,
  CategoryScale,
} from 'chart.js';

// Înregistrăm componentele Chart.js
ChartJS.register(LineElement, PointElement, LinearScale, Title, CategoryScale);

// Starea aplicației
const running = ref(false);
const delayL = ref(10);
const delayR = ref(12);
const waveformData = ref({ input: [], output: [] });
const showInput = ref(true);
let pollingInterval = null;

// Funcție pentru polling date waveform cu retry
const fetchWaveformData = async () => {
  const maxRetries = 3;
  let retries = 0;

  while (retries < maxRetries) {
    try {
      const [inputRes, outputRes] = await Promise.all([
        fetch('http://192.168.3.28:5500/data_input', { method: 'GET' }),
        fetch('http://192.168.3.28:5500/data_output', { method: 'GET' }),
      ]);

      if (!inputRes.ok) throw new Error(`Eroare input: ${inputRes.status}`);
      if (!outputRes.ok) throw new Error(`Eroare output: ${outputRes.status}`);

      const inputData = await inputRes.json();
      const outputData = await outputRes.json();

      waveformData.value = {
        input: inputData.input || [],
        output: outputData.output || [],
      };

      console.log('Waveform primit:', waveformData.value);
      return;
    } catch (error) {
      retries++;
      console.error(`Eroare la polling (încercarea ${retries}/${maxRetries}):`, error);
      if (retries === maxRetries) {
        console.error('Maxim de încercări atins. Polling oprit temporar.');
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
};

// Controlează polling-ul în funcție de running
const startPolling = () => {
  if (pollingInterval) clearInterval(pollingInterval);
  pollingInterval = setInterval(fetchWaveformData, 100); // Reducem frecvența la 100ms
};

const stopPolling = () => {
  if (pollingInterval) {
    clearInterval(pollingInterval);
    pollingInterval = null;
  }
  waveformData.value = { input: [], output: [] }; // Resetăm datele
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
    console.log('Trimit cerere /toggle...');
    const res = await fetch('http://192.168.3.28:5500/toggle', { method: 'POST' });
    if (!res.ok) throw new Error(`Răspuns invalid: ${res.status}`);
    const data = await res.json();
    running.value = data.running;
    console.log('Toggle response:', data);
  } catch (error) {
    console.error('Eroare la toggle:', error);
  }
};

const updateParams = async () => {
  const params = { delay_l: delayL.value, delay_r: delayR.value };
  try {
    console.log('Trimit cerere /update...');
    const res = await fetch('http://192.168.3.28:5500/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) throw new Error(`Răspuns invalid: ${res.status}`);
    const data = await res.json();
    console.log('Update response:', data);
  } catch (error) {
    console.error('Eroare la update:', error);
  }
};

// Configurare grafic
const chartData = computed(() => ({
  labels: Array(waveformData.value[showInput.value ? 'input' : 'output'].length).fill(''),
  datasets: [
    {
      label: showInput.value ? 'Input' : 'Output',
      data: waveformData.value[showInput.value ? 'input' : 'output'],
      borderColor: 'blue',
      fill: false,
      pointRadius: 0,
    },
  ],
}));

const chartOptions = {
  animation: false,
  maintainAspectRatio: false,
  scales: {
    x: { display: false },
    y: { min: -32768, max: 32767 },
  },
};
</script>

<style scoped>
/* Stiluri opționale */
</style>