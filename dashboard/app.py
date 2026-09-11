from flask import Flask, render_template
import pandas as pd

app = Flask(__name__)

def load_stats():
    df = pd.read_csv("flow_stats.csv", names=[
        "timestamp", "src_mac", "dst_mac", "proto", "dst_port",
        "switch_id", "bitrate", "duration", "avg_pkt_size"
    ])
    return df.tail(50)  # Ultimi 50 flussi

@app.route("/")
def dashboard():
    df = load_stats()
    data = df.to_dict(orient="records")
    return render_template("dashboard.html", records=data)


if __name__ == "__main__":
    print("Flask sta partendo...")
    app.run(debug=True)
