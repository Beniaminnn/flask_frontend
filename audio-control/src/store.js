import { createStore } from 'vuex';

export const store = createStore({
    state() {
        return {
            running: false,
            delayL: 10,
            delayR: 12,
            waveformData: { input: [], output: [], anomalies: [] },
            logs: {
                input_max_amplitude: 0,
                output_max_amplitude: 0,
                temperature: 'N/A',
                cpu_load: 0,
                wifi_ssid: 'N/A',
                wifi_signal: 'N/A'
            },
            sensors: {
                Dreapta: 'Eroare',
                Stânga: 'Eroare',
                Față: 'Eroare',
                Spate: 'Eroare'
            },
            logsGeneral: [],
            logsSensors: [],
            logsPeople: [],
            logsAudio: []
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
        setSensors(state, sensors) {
            state.sensors = sensors;
        },
        setLogsGeneral(state, logs) {
            state.logsGeneral = logs;
        },
        setLogsSensors(state, logs) {
            state.logsSensors = logs;
        },
        setLogsPeople(state, logs) {
            state.logsPeople = logs;
        },
        setLogsAudio(state, logs) {
            state.logsAudio = logs;
        }
    }
});