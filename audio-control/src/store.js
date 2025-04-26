import { createStore } from 'vuex';

export const store = createStore({
    state() {
        return {
            running: false,
            delayL: 10,
            delayR: 12,
            waveformData: { input: [], output: [] },
            logs: {
                input_max_amplitude: 0,
                output_max_amplitude: 0,
                temperature: 'N/A',
                cpu_load: 0,
                wifi_ssid: 'N/A',
                wifi_signal: 'N/A'
            },
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
            state.waveformData = waveformData;
        },
        setLogs(state, logs) {
            state.logs = logs;
        },
    }
});