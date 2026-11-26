"""Spike: Python SDK. Env: SPIKE_API_URL, SPIKE_EVENTS_URL, SPIKE_ENV_KEY (fake)."""
import os

from flagsmith import EventProcessorConfig, Flagsmith

kw = {}
if os.environ.get("SPIKE_API_URL"):
    kw["api_url"] = os.environ["SPIKE_API_URL"]
# SPIKE_PY_MAXBUF=1 reproduces the official prompt's advice (max_buffer_items=1); default = SDK default (1000)
cfg = {"max_buffer_items": int(os.environ["SPIKE_PY_MAXBUF"])} if os.environ.get("SPIKE_PY_MAXBUF") else {}
if os.environ.get("SPIKE_EVENTS_URL"):
    cfg["events_api_url"] = os.environ["SPIKE_EVENTS_URL"]
fs = Flagsmith(environment_key=os.environ.get("SPIKE_ENV_KEY", "spike-fake-key"),
               enable_events=True, event_processor_config=EventProcessorConfig(**cfg), **kw)
flag = fs.get_experiment_flag("spike_flag", identifier="spike-1")
print("flag:", flag)
fs.track_event("spike_event", identifier="spike-1", value=1.5)
fs.flush_events()
fs.close()
