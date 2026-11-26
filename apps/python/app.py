import uuid

from flask import Flask, g, jsonify, render_template, request

app = Flask(__name__)


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
    return render_template("index.html", button_text="Join")


@app.post("/join")
def join():
    return jsonify(ok=True)


if __name__ == "__main__":
    import os

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
