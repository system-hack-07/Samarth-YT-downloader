from flask import Flask, request, jsonify, send_from_directory, render_template_string
import yt_dlp
import os
import uuid
import threading
import time
import json
from datetime import datetime

app = Flask(__name__)

DOWNLOAD_DIR = "downloads"
HISTORY_FILE = "history.json"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

PROGRESS_TRACKER = {}

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_history(history):
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def format_size(bytes):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024.0:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.1f} TB"

def ydl_hook(d, task_id):
    if d.get('status') == 'downloading':
        downloaded = d.get('downloaded_bytes', 0)
        total = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
        percent = max(0, min(99, int((downloaded / total) * 100)))
        PROGRESS_TRACKER[task_id] = {
            "status": "downloading",
            "percent": percent,
            "speed": d.get('speed', 0),
            "eta": d.get('eta', 0),
            "downloaded": downloaded,
            "total": total,
            "downloaded_str": format_size(downloaded),
            "total_str": format_size(total)
        }
    elif d.get('status') == 'finished':
        PROGRESS_TRACKER[task_id] = {"status": "processing", "percent": 99}

def background_download(url, task_id, is_audio, quality='1080'):
    outtmpl = os.path.join(DOWNLOAD_DIR, f'{task_id}.%(ext)s')
    
    if is_audio:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': outtmpl,
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}],
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [lambda d: ydl_hook(d, task_id)]
        }
    else:
        quality_map = {
            '1080': 'best[height<=1080][fps<=60]+bestaudio/best',
            '720': 'best[height<=720][fps<=60]+bestaudio/best',
            '480': 'best[height<=480]+bestaudio/best',
            '360': 'best[height<=360]+bestaudio/best',
            '144': 'best[height<=144]+bestaudio/best'
        }
        ydl_opts = {
            'format': quality_map.get(quality, 'best[height<=1080]+bestaudio/best'),
            'outtmpl': outtmpl,
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [lambda d: ydl_hook(d, task_id)]
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Unknown')
            
            time.sleep(1)
            
            filename = None
            for file in os.listdir(DOWNLOAD_DIR):
                if file.startswith(task_id):
                    filename = file
                    break
            
            if filename:
                file_path = os.path.join(DOWNLOAD_DIR, filename)
                file_size = os.path.getsize(file_path)
                
                history = load_history()
                history.append({
                    "id": task_id,
                    "url": url,
                    "title": title,
                    "filename": filename,
                    "format": "MP3" if is_audio else "MP4",
                    "quality": quality,
                    "size": file_size,
                    "size_str": format_size(file_size),
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "downloads": 1
                })
                save_history(history)
                
                PROGRESS_TRACKER[task_id] = {
                    "status": "completed",
                    "percent": 100,
                    "filename": filename,
                    "size": file_size,
                    "size_str": format_size(file_size),
                    "title": title
                }
    except Exception as e:
        PROGRESS_TRACKER[task_id] = {"status": "failed", "error": str(e)}

# === PASTE YOUR TWO BIG HTML TEMPLATES HERE (LANDING_HTML and DOWNLOADER_HTML) ===
# Keep them exactly as you had them before

@app.route('/')
def landing():
    return render_template_string(LANDING_HTML)

@app.route('/downloader')
def downloader():
    return render_template_string(DOWNLOADER_HTML)

@app.route('/api/history')
def api_history():
    return jsonify(load_history())

@app.route('/api/history/clear', methods=['POST'])
def api_clear_history():
    save_history([])
    return jsonify({"status": "cleared"})

@app.route('/api/metadata')
def api_metadata():
    url = request.args.get('url')
    if not url: return jsonify({"error": "No URL"}), 400
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return jsonify({
                "title": info.get('title', 'Unknown'),
                "duration": info.get('duration', 0),
                "uploader": info.get('uploader', 'Unknown')
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/start_audio')
def api_start_audio():
    url = request.args.get('url')
    quality = request.args.get('quality', '1080')
    if not url: return jsonify({"error": "No URL"}), 400
    task_id = str(uuid.uuid4())
    PROGRESS_TRACKER[task_id] = {"status": "pending", "percent": 0}
    threading.Thread(target=background_download, args=(url, task_id, True, quality), daemon=True).start()
    return jsonify({"task_id": task_id})

@app.route('/api/start_video')
def api_start_video():
    url = request.args.get('url')
    quality = request.args.get('quality', '1080')
    if not url: return jsonify({"error": "No URL"}), 400
    task_id = str(uuid.uuid4())
    PROGRESS_TRACKER[task_id] = {"status": "pending", "percent": 0}
    threading.Thread(target=background_download, args=(url, task_id, False, quality), daemon=True).start()
    return jsonify({"task_id": task_id})

@app.route('/api/progress/<task_id>')
def api_progress(task_id):
    return jsonify(PROGRESS_TRACKER.get(task_id, {"status": "unknown", "percent": 0}))

@app.route('/api/retrieve/<task_id>')
def api_retrieve(task_id):
    task = PROGRESS_TRACKER.get(task_id)
    if task and task.get('status') == 'completed':
        filename = task.get('filename')
        if filename and os.path.exists(os.path.join(DOWNLOAD_DIR, filename)):
            return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)
        for file in os.listdir(DOWNLOAD_DIR):
            if task_id in file:
                return send_from_directory(DOWNLOAD_DIR, file, as_attachment=True)
    return "Not found", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=False, host='0.0.0.0', port=port)
