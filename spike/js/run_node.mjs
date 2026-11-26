// Spike: JS SDK (isomorphic build, global fetch) run under Node. Same env vars.
import flagsmith from '@flagsmith/flagsmith/isomorphic';
const opts = { environmentID: process.env.SPIKE_ENV_KEY || 'spike-fake-key', enableEvents: true };
if (process.env.SPIKE_API_URL) opts.api = process.env.SPIKE_API_URL;
if (process.env.SPIKE_EVENTS_URL) opts.eventProcessorConfig = { eventsApiUrl: process.env.SPIKE_EVENTS_URL };
await flagsmith.init(opts);
await flagsmith.identify('spike-1');
const flag = flagsmith.getExperimentFlag('spike_flag');
console.log('flag:', JSON.stringify(flag));
flagsmith.trackEvent('spike_event', { value: 1.5 });
await flagsmith.flushEvents();
