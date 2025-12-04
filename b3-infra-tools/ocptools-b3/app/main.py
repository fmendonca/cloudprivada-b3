from __future__ import annotations
import os
from flask import Flask, render_template, jsonify
from kubevirt_client import collect_data

app = Flask(__name__)

# Valor padrão: 10000 ms (10s) se não vier do ambiente
POLL_INTERVAL_MS = int(os.environ.get("POLL_INTERVAL_MS", "10000"))


@app.route("/")
def index():
    return render_template("index.html", poll_interval_ms=POLL_INTERVAL_MS)


@app.route("/api/vms")
def api_vms():
    rows = collect_data()
    return jsonify(rows)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
