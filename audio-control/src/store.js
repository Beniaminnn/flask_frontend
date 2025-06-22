import { createStore } from 'vuex';

export const store = createStore({
    state() {
        return {
            running: false,
            delayL: 0,
            delayR: 0,
            waveformData: { input: [], output: [], anomalies: [], input_max_amplitude: 0, output_max_amplitude: 0 },
            micWaveformData: [],
            logs: {
                input_max_amplitude: 0,
                output_max_amplitude: 0,
                mic_max_amplitude: 0,
                temperature: 'N/A',
                cpu_load: 0,
                wifi_ssid: 'N/A',
                wifi_signal: 'N/A',
            },
            sensors: { distances: ['Eroare', 'Eroare', 'Eroare', 'Eroare'], positions: [] },
        };
    },
    mutations: {
        setRunning(state, running) {
            state.running = running;
        },
        setDelayL(state, delayL) {
            state.delayL = delayL;
        },
        setDelayR(state, delayR) {
            state.delayR = delayR;
        },
        setWaveformData(state, waveformData) {
            state.waveformData = { ...state.waveformData, ...waveformData };
        },
        setMicWaveformData(state, micWaveformData) {
            state.micWaveformData = micWaveformData;
        },
        setLogs(state, logs) {
            state.logs = { ...state.logs, ...logs };
        },
        setSensors(state, sensors) {
            state.sensors = sensors;
        },
    },
});