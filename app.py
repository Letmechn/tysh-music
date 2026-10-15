import os
import subprocess
import json
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

CACHE_DIR = "/tmp/tysh_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

@app.route("/health")
def health():
    return jsonify({"status": "online", "service": "TySh Cloud Music Engine v1.0"})

@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"success": False, "error": "Query required"}), 400

    cmd = [
        "yt-dlp",
        "--default-search", "ytsearch8",
        query,
        "--dump-json",
        "--flat-playlist",
        "--no-warnings"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        tracks = []
        base_url = request.host_url.rstrip("/")
        for line in res.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                d = json.loads(line)
                v_id = d.get("id")
                title = d.get("title") or "Unknown"
                duration = d.get("duration") or 180
                uploader = d.get("uploader") or d.get("channel") or "Artist"
                thumbnails = d.get("thumbnails") or []
                thumb = thumbnails[-1].get("url") if thumbnails else f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg"

                if v_id and title:
                    tracks.append({
                        "id": "yt_" + v_id,
                        "videoId": v_id,
                        "title": title[:38],
                        "artist": uploader[:28],
                        "duration": int(duration),
                        "coverUrl": thumb,
                        "audioUrl": f"{base_url}/audio?id={v_id}",
                        "source": "Full Master Track (320k)"
                    })
            except Exception:
                pass

        return jsonify({"success": True, "results": tracks})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/audio")
def audio():
    v_id = request.args.get("id", "").strip()
    if not v_id:
        return "Video ID required", 400

    safe_id = "".join(c for c in v_id if c.isalnum() or c in "_-")[:20]
    target_file = os.path.join(CACHE_DIR, f"{safe_id}.mp3")

    if not os.path.exists(target_file):
        yt_url = f"https://www.youtube.com/watch?v={safe_id}"
        temp_output = os.path.join(CACHE_DIR, f"{safe_id}.%(ext)s")
        cmd = [
            "yt-dlp",
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "192K",
            "-o", temp_output,
            yt_url,
            "--no-warnings"
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        except Exception:
            pass

    if os.path.exists(target_file):
        return send_file(target_file, mimetype="audio/mpeg")
    return "Audio extraction failed", 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port)
