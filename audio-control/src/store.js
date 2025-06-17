import { createStore } from 'vuex';

export const store = createStore({
    state() {
        return {
            running: false,
            delayL: 10,
            delayR: 12,
            waveformData: { input: [], output: [], anomalies: [] },
            micWaveformData: [], // Nou: date brute ale microfonului
            logs: {
                input_max_amplitude: 0,
                output_max_amplitude: 0,
                temperature: 'N/A',
                cpu_load: 0,
                wifi_ssid: 'N/A',
                wifi_signal: 'N/A'
            },
            sensors: {
                distances: ['Eroare', 'Eroare', 'Eroare', 'Eroare'],
                positions: []
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
        setMicWaveformData(state, micWaveformData) { // Nou: mutație pentru datele microfonului
            state.micWaveformData = micWaveformData;
        },
        setLogs(state, logs) {
            state.logs = logs;
        },
        setSensors(state, sensors) {
            state.sensors = sensors; // Acum acceptă un obiect cu distances și positions
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