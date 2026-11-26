// Spike: Node SDK. Env: SPIKE_API_URL, SPIKE_EVENTS_URL, SPIKE_ENV_KEY (fake).
import { Flagsmith } from '@flagsmith/nodejs';
const opts = { environmentKey: process.env.SPIKE_ENV_KEY || 'spike-fake-key', enableEvents: true };
if (process.env.SPIKE_API_URL) opts.apiUrl = process.env.SPIKE_API_URL;
if (process.env.SPIKE_EVENTS_URL) opts.eventProcessorConfig = { eventsApiUrl: process.env.SPIKE_EVENTS_URL };
const fs = new Flagsmith(opts);
const flag = await fs.getExperimentFlag('spike_flag', 'spike-1');
console.log('flag:', JSON.stringify(flag));
fs.trackEvent('spike_event', { identifier: 'spike-1', value: 1.5 });
await fs.flushEvents();
await fs.close();
