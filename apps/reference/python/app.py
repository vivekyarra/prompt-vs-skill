import os
import uuid

from flask import Flask, g, jsonify, render_template, request
from flagsmith import Flagsmith
from flagsmith.analytics import EventProcessorConfig

app = Flask(__name__)

FLAG = os.environ.get("FLAGSMITH_FLAG", "join_button_text")
CONTROL_TEXT = "Join"

# Server-side key: only ever read here, on the server. Never sent to the browser.
flagsmith = None
if os.environ.get("FLAGSMITH_SERVER_KEY"):
    _kwargs = {}
    if os.environ.get("FLAGSMITH_EVENTS_URL"):
        _kwargs["event_processor_config"] = EventProcessorConfig(
            events_api_url=os.environ["FLAGSMITH_EVENTS_URL"]
        )
    flagsmith = Flagsmith(
        environment_key=os.environ["FLAGSMITH_SERVER_KEY"],
        api_url=os.environ.get("FLAGSMITH_API_URL", "https://edge.api.flagsmith.com/api/v1/"),
        enable_events=True,
        **_kwargs,
    )


# Visitor identity: a long-lived cookie `vid`, set in before_request / after_request.
@app.before_request
def ensure_visitor_id():
    g.vid = request.cookies.get("vid")
    g.new_vid = g.vid is None
    if g.new_vid:
        g.vid = str(uuid.uuid4())


@app.after_request
def persist_visitor_id(response):
    if g.get("new_vid"):
        response.set_cookie("vid", g.vid, max_age=365 * 24 * 3600, httponly=True, samesite="Lax")
    return response


@app.get("/")
def index():
    text = CONTROL_TEXT
    if flagsmith:
        try:
            # Experiment method: reads the flag AND records the exposure for this identity.
            flag = flagsmith.get_experiment_flag(FLAG, g.vid)
            flagsmith.flush_events()  # send the exposure now, not on the timer
            if isinstance(flag.value, str) and flag.value:
                text = flag.value
        except Exception as exc:  # fall back to control, never crash the page
            app.logger.error("flagsmith error: %s", exc)
    return render_template("index.html", button_text=text)


@app.post("/join")
def join():
    if flagsmith:
        try:
            # Conversion: only on click, with the same identity as the exposure.
            flagsmith.track_event("join_clicked", identifier=g.vid)
            flagsmith.flush_events()
        except Exception as exc:
            app.logger.error("flagsmith error: %s", exc)
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
