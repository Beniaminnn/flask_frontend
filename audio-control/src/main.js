import { createApp } from 'vue';
import './style.css';
import App from './App.vue';
import { store } from './store';
import Toast from '@brackets/vue-toastification';
import '@brackets/vue-toastification/dist/index.css';

const app = createApp(App);
app.use(store);
app.use(Toast, {
    transition: 'Vue-Toastification__bounce',
    maxToasts: 20,
    newestOnTop: true,
});
app.mount('#app');