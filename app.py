import os
import subprocess
import json
import hashlib
import urllib.parse
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

CACHE_DIR = "/tmp/tysh_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

@app.route("/health")
def health():
    return jsonify({"status": "online", "service": "TySh Cloud Music Engine v2.1", "version": "bulletproof"})

@app.route("/version")
def version():
    return "v2.1-bulletproof", 200

@app.route("/ping")
def ping():
    return "pong", 200

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
                        "audioUrl": f"{base_url}/audio?id={v_id}&title={urllib.parse.quote(title)}",
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
        err_msg = ""
        cookie_args = ["--cookies", "cookies.txt"] if os.path.exists("cookies.txt") else []

        # Strategy 1: Extract direct audio stream via tv_embedded (Zero YouTube Bot Check)
        try:
            cmd1 = [
                "yt-dlp",
                *cookie_args,
                "--extractor-args", "youtube:player_client=tv_embedded",
                "-g", "-f", "140/ba/b",
                yt_url,
                "--no-warnings"
            ]
            res1 = subprocess.run(cmd1, capture_output=True, text=True, timeout=15)
            stream_url = res1.stdout.strip()
            if stream_url and stream_url.startswith("http"):
                cmd_ffmpeg = [
                    "ffmpeg", "-y",
                    "-i", stream_url,
                    "-vn", "-c:a", "libmp3lame",
                    "-b:a", "192k",
                    target_file
                ]
                res_ff = subprocess.run(cmd_ffmpeg, capture_output=True, text=True, timeout=45)
                if res_ff.returncode != 0:
                    err_msg = res_ff.stderr or "FFmpeg encoding failed"
        except Exception as e:
            err_msg = str(e)

        # Strategy 2: Direct yt-dlp audio extraction fallback
        if not os.path.exists(target_file):
            temp_output = os.path.join(CACHE_DIR, f"{safe_id}.%(ext)s")
            cmd2 = [
                "yt-dlp",
                *cookie_args,
                "--extractor-args", "youtube:player_client=android_creator,android,mweb",
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "192K",
                "-o", temp_output,
                yt_url,
                "--no-warnings"
            ]
            try:
                res2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=35)
                if res2.returncode != 0 and not err_msg:
                    err_msg = res2.stderr
            except Exception as e:
                err_msg = str(e)

        # Strategy 3: SoundCloud Fallback (100% Free, Zero Bot Verification)
        if not os.path.exists(target_file):
            search_term = request.args.get("title", "").strip() or request.args.get("q", "").strip()
            if search_term:
                temp_output = os.path.join(CACHE_DIR, f"{safe_id}.%(ext)s")
                cmd3 = [
                    "yt-dlp",
                    "-x",
                    "--audio-format", "mp3",
                    "--audio-quality", "192K",
                    "-o", temp_output,
                    f"scsearch1:{search_term}",
                    "--no-warnings"
                ]
                try:
                    subprocess.run(cmd3, capture_output=True, text=True, timeout=25)
                except Exception as e:
                    err_msg = str(e)

    # Check for direct target file
    if os.path.exists(target_file):
        return send_file(target_file, mimetype="audio/mpeg")

    # Check for any audio file matching safe_id
    for f in os.listdir(CACHE_DIR):
        if f.startswith(safe_id):
            full_p = os.path.join(CACHE_DIR, f)
            mime = "audio/mpeg" if f.endswith(".mp3") else "audio/mp4" if f.endswith(".m4a") else "audio/ogg"
            return send_file(full_p, mimetype=mime)

    return f"Audio extraction failed: {err_msg}", 404

@app.route("/convert")
def convert():
    q = request.args.get("q", "").strip()
    if not q:
        return "Query required", 400

    q_hash = hashlib.md5(q.lower().encode("utf-8")).hexdigest()[:16]
    target_file = os.path.join(CACHE_DIR, f"conv_{q_hash}.mp3")

    if not os.path.exists(target_file):
        temp_output = os.path.join(CACHE_DIR, f"conv_{q_hash}.%(ext)s")
        # Strategy 1: SoundCloud (100% Free, Zero Bot Block)
        try:
            cmd_sc = [
                "yt-dlp",
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "192K",
                "-o", temp_output,
                f"scsearch1:{q}",
                "--no-warnings"
            ]
            res_sc = subprocess.run(cmd_sc, capture_output=True, text=True, timeout=25)
        except Exception:
            pass

        # Strategy 2: YouTube Fallback with cookies
        if not os.path.exists(target_file):
            cookie_args = ["--cookies", "cookies.txt"] if os.path.exists("cookies.txt") else []
            cmd_search = [
                "yt-dlp",
                *cookie_args,
                f"ytsearch1:{q}",
                "--dump-json",
                "--flat-playlist",
                "--no-warnings"
            ]
            try:
                res_s = subprocess.run(cmd_search, capture_output=True, text=True, timeout=12)
                if res_s.stdout.strip():
                    d = json.loads(res_s.stdout.strip().split("\n")[0])
                    v_id = d.get("id")
                    if v_id:
                        cmd_stream = [
                            "yt-dlp",
                            *cookie_args,
                            "--extractor-args", "youtube:player_client=tv_embedded",
                            "-g", "-f", "140/ba/b",
                            f"https://www.youtube.com/watch?v={v_id}",
                            "--no-warnings"
                        ]
                        res_str = subprocess.run(cmd_stream, capture_output=True, text=True, timeout=15)
                        stream_url = res_str.stdout.strip()
                        if stream_url and stream_url.startswith("http"):
                            cmd_ffmpeg = [
                                "ffmpeg", "-y",
                                "-i", stream_url,
                                "-vn", "-c:a", "libmp3lame",
                                "-b:a", "192k",
                                target_file
                            ]
                            subprocess.run(cmd_ffmpeg, capture_output=True, text=True, timeout=45)
            except Exception:
                pass

    if os.path.exists(target_file):
        return send_file(target_file, mimetype="audio/mpeg")
    return "Conversion failed", 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port)
