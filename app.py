from flask import Flask, request, jsonify, send_from_directory, render_template_string
import yt_dlp, os, uuid, threading, time, json
from datetime import datetime

app = Flask(__name__)
DOWNLOAD_DIR = "downloads"
HISTORY_FILE = "history.json"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
PROGRESS_TRACKER = {}

def load_history():
    if os.path.exists(HISTORY_FILE):
        try: return json.load(open(HISTORY_FILE))
        except: return []
    return []

def save_history(h): 
    with open(HISTORY_FILE, 'w') as f: json.dump(h, f, indent=2)

def format_size(b):
    for u in ['B','KB','MB','GB']:
        if b < 1024: return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"

def ydl_hook(d, tid):
    if d.get('status') == 'downloading':
        PROGRESS_TRACKER[tid] = {"status": "downloading", "percent": min(99, int((d.get('downloaded_bytes',0)/ (d.get('total_bytes') or 1))*100))}
    elif d.get('status') == 'finished':
        PROGRESS_TRACKER[tid] = {"status": "processing", "percent": 99}

def background_download(url, tid, is_audio, q='1080'):
    try:
        out = os.path.join(DOWNLOAD_DIR, f'{tid}.%(ext)s')
        opts = {'outtmpl': out, 'quiet': True, 'progress_hooks': [lambda d: ydl_hook(d,tid)]}
        if is_audio:
            opts.update({'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]})
        else:
            opts['format'] = f'best[height<={q}]+bestaudio/best'
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title','Unknown')
        
        filename = next((f for f in os.listdir(DOWNLOAD_DIR) if f.startswith(tid)), None)
        if filename:
            size = os.path.getsize(os.path.join(DOWNLOAD_DIR, filename))
            history = load_history()
            history.append({"id":tid,"url":url,"title":title,"filename":filename,"format":"MP3" if is_audio else "MP4","quality":q,"size":size,"size_str":format_size(size),"date":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"downloads":1})
            save_history(history)
            PROGRESS_TRACKER[tid] = {"status":"completed","percent":100,"filename":filename,"size":size,"size_str":format_size(size),"title":title}
    except Exception as e:
        PROGRESS_TRACKER[tid] = {"status":"failed","error":str(e)}

# === PASTE YOUR LANDING_HTML and DOWNLOADER_HTML HERE (keep them unchanged) ===

@app.route('/') 
def landing(): return render_template_string(LANDING_HTML)

@app.route('/downloader') 
def downloader(): return render_template_string(DOWNLOADER_HTML)

@app.route('/api/history') 
def api_history(): return jsonify(load_history())

@app.route('/api/history/clear', methods=['POST']) 
def clear(): save_history([]); return jsonify({"status":"cleared"})

@app.route('/api/start_audio')
def start_audio():
    url = request.args.get('url')
    tid = str(uuid.uuid4())
    PROGRESS_TRACKER[tid] = {"status":"pending","percent":0}
    threading.Thread(target=background_download, args=(url,tid,True,request.args.get('quality','1080')), daemon=True).start()
    return jsonify({"task_id":tid})

@app.route('/api/start_video')
def start_video():
    url = request.args.get('url')
    tid = str(uuid.uuid4())
    PROGRESS_TRACKER[tid] = {"status":"pending","percent":0}
    threading.Thread(target=background_download, args=(url,tid,False,request.args.get('quality','1080')), daemon=True).start()
    return jsonify({"task_id":tid})

@app.route('/api/progress/<tid>')
def progress(tid): return jsonify(PROGRESS_TRACKER.get(tid, {"status":"unknown","percent":0}))

@app.route('/api/retrieve/<tid>')
def retrieve(tid):
    t = PROGRESS_TRACKER.get(tid)
    if t and t.get('status') == 'completed':
        fn = t.get('filename')
        if fn and os.path.exists(p:=os.path.join(DOWNLOAD_DIR,fn)):
            return send_from_directory(DOWNLOAD_DIR, fn, as_attachment=True)
    return "404", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
