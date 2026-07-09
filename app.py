from flask import Flask, request, jsonify, send_from_directory, render_template_string
import yt_dlp
import os
import uuid
import threading
import time
import json
from datetime import datetime

app = Flask(__name__)
DOWNLOAD_DIR = os.path.abspath("downloads")
HISTORY_FILE = os.path.abspath("history.json")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

PROGRESS_TRACKER = {}

# Load/Save History
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
        speed = d.get('speed', 0)
        eta = d.get('eta', 0)
        
        PROGRESS_TRACKER[task_id] = {
            "status": "downloading",
            "percent": percent,
            "speed": speed,
            "eta": eta,
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
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320'
            }],
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
        format_spec = quality_map.get(quality, 'best[height<=1080]+bestaudio/best')
        
        ydl_opts = {
            'format': format_spec,
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
            else:
                PROGRESS_TRACKER[task_id] = {"status": "failed", "error": "File not found after download"}
            
    except Exception as e:
        PROGRESS_TRACKER[task_id] = {"status": "failed", "error": str(e)}

# LANDING PAGE HTML
LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube Video/Audio Downloader</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;800&family=Orbitron:wght@500;800;900&family=Plus+Jakarta+Sans:wght@300;400;600&display=swap" rel="stylesheet">
    
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background-color: #010206;
            color: #ffffff;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            overflow: hidden;
            position: relative;
            font-family: 'Plus Jakarta Sans', sans-serif;
        }

        body::before {
            content: '';
            position: absolute;
            inset: 0;
            background: 
                linear-gradient(rgba(0, 210, 255, 0.02) 1px, transparent 1px) 0 0 / 60px 60px,
                linear-gradient(90deg, rgba(0, 210, 255, 0.02) 1px, transparent 1px) 0 0 / 60px 60px;
            mask-image: radial-gradient(circle at center, black 30%, transparent 75%);
            -webkit-mask-image: radial-gradient(circle at center, black 30%, transparent 75%);
            z-index: 0;
            pointer-events: none;
        }

        .glowing-core {
            position: absolute;
            width: 700px;
            height: 700px;
            background: radial-gradient(circle at center, rgba(0, 162, 255, 0.15) 0%, rgba(0, 50, 150, 0.04) 40%, transparent 70%);
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            z-index: 0;
            pointer-events: none;
            animation: atmosphericPulse 12s infinite alternate ease-in-out;
        }

        @keyframes atmosphericPulse {
            0% { transform: translate(-50%, -50%) scale(0.9); opacity: 0.7; }
            100% { transform: translate(-50%, -50%) scale(1.1); opacity: 1; filter: hue-rotate(-10deg); }
        }

        .container {
            text-align: center;
            z-index: 1;
            max-width: 530px;
            width: 90%;
            padding: 70px 45px;
            background: linear-gradient(180deg, rgba(5, 10, 25, 0.85) 0%, rgba(2, 4, 10, 0.95) 100%);
            border: 2px solid #00d2ff;
            border-radius: 48px;
            box-shadow: 
                0 0 35px rgba(0, 210, 255, 0.25),
                0 0 70px rgba(0, 80, 255, 0.15),
                inset 0 0 25px rgba(0, 210, 255, 0.08),
                inset 0 1px 3px rgba(255, 255, 255, 0.15);
            backdrop-filter: blur(40px);
            -webkit-backdrop-filter: blur(40px);
            position: relative;
            transition: all 0.6s cubic-bezier(0.2, 0.8, 0.2, 1);
        }

        .container:hover {
            transform: translateY(-4px);
            border-color: #ffffff;
            box-shadow: 
                0 0 50px rgba(0, 210, 255, 0.4),
                0 0 100px rgba(0, 80, 255, 0.25),
                inset 0 0 35px rgba(0, 210, 255, 0.12);
        }

        .container::before {
            content: '';
            position: absolute;
            top: 25px;
            left: 25px;
            right: 25px;
            bottom: 25px;
            border-radius: 32px;
            border: 1px solid rgba(0, 210, 255, 0.05);
            pointer-events: none;
        }

        h1 {
            font-size: 1.65rem;
            font-weight: 400;
            margin-bottom: 30px;
            color: #ffffff;
            line-height: 1.4;
            letter-spacing: 0.5px;
        }

        .welcome {
            font-family: 'Orbitron', sans-serif;
            font-size: 1.7rem;
            font-weight: 900;
            color: #ffffff;
            text-transform: uppercase;
            letter-spacing: 6px;
            margin-bottom: 20px;
            background: linear-gradient(180deg, #ffffff 40%, #00d2ff 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            filter: drop-shadow(0 0 15px rgba(0, 210, 255, 0.3));
        }

        p {
            font-size: 0.95rem;
            color: #94a3b8;
            margin-bottom: 45px;
            line-height: 1.7;
            font-weight: 300;
            letter-spacing: 0.3px;
        }

        .credits {
            font-size: 0.75rem;
            color: #475569;
            margin-bottom: 55px;
            text-transform: uppercase;
            letter-spacing: 5px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 10px;
        }

        .credits::before, .credits::after {
            content: '';
            width: 15px;
            height: 1px;
            background-color: rgba(0, 210, 255, 0.3);
        }

        .credits span {
            color: #00d2ff;
            font-weight: 800;
            letter-spacing: 6px;
            text-shadow: 0 0 10px rgba(0, 210, 255, 0.4);
        }

        .enter-btn {
            background: #ffffff;
            color: #010206;
            border: 1px solid #ffffff;
            padding: 18px 75px;
            font-family: 'Orbitron', sans-serif;
            font-size: 0.95rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 5px;
            cursor: pointer;
            border-radius: 100px;
            transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
            outline: none;
            text-decoration: none;
            display: inline-block;
        }

        .enter-btn:hover {
            background: transparent;
            color: #00d2ff;
            border-color: #00d2ff;
            transform: scale(1.03);
            box-shadow: 0 0 35px rgba(0, 210, 255, 0.6);
            letter-spacing: 7px;
        }

        .enter-btn:active {
            transform: scale(0.98);
        }

        footer {
            position: absolute;
            bottom: 35px;
            color: #334155;
            font-size: 0.75rem;
            letter-spacing: 3px;
            width: 100%;
            text-align: center;
            z-index: 1;
            font-weight: 600;
            text-transform: uppercase;
        }

        @media (max-width: 480px) {
            .container { padding: 40px 25px; }
            h1 { font-size: 1.2rem; }
            .welcome { font-size: 1.2rem; letter-spacing: 3px; }
            .enter-btn { padding: 15px 40px; font-size: 0.8rem; letter-spacing: 3px; }
        }
    </style>
</head>
<body>

    <div class="glowing-core"></div>

    <div class="container">
        <h1>🎬 YouTube Video/Audio Downloader</h1>
        <div class="welcome">Welcome!</div>
        <p>Download your favorite YouTube Videos and Audio (MP3) quickly and easily.</p>
        <div class="credits">𝐌𝐚𝐝𝐞 𝐛𝐲 :- <span><span>𝐒𝐀𝐌𝐀𝐑𝐓𝐇</span></span></div>
        
        <a href="/downloader" class="enter-btn">Enter</a>
    </div>

    <footer>
        &copy; 2026 All Rights Reserved to Samarth Website
    </footer>

</body>
</html>"""

# DOWNLOADER PAGE HTML
DOWNLOADER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Samarth - Video Downloader</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --bg-primary: #030712;
            --bg-secondary: #060c18;
            --bg-card: rgba(6, 12, 24, 0.95);
            --bg-input: #0f172a;
            --border-color: rgba(59, 130, 246, 0.4);
            --text-primary: #ffffff;
            --text-secondary: #94a3b8;
            --text-accent: #60a5fa;
            --shadow-color: rgba(37, 99, 235, 0.6);
        }

        [data-theme="light"] {
            --bg-primary: #f1f5f9;
            --bg-secondary: #ffffff;
            --bg-card: rgba(255, 255, 255, 0.95);
            --bg-input: #e2e8f0;
            --border-color: rgba(37, 99, 235, 0.3);
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --text-accent: #2563eb;
            --shadow-color: rgba(37, 99, 235, 0.3);
        }

        body {
            background-color: var(--bg-primary);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 16px;
            margin: 0;
            transition: background-color 0.3s ease;
        }

        .glass-card {
            background: var(--bg-card);
            backdrop-filter: blur(10px);
            border: 1px solid var(--border-color);
            transition: all 0.3s ease;
        }

        .neon-glow-blue {
            box-shadow: 0 0 25px var(--shadow-color);
        }

        .text-primary { color: var(--text-primary); }
        .text-secondary { color: var(--text-secondary); }
        .text-accent { color: var(--text-accent); }
        .bg-input { background: var(--bg-input); }

        .progress-fill {
            background: linear-gradient(90deg, #3b82f6, #38bdf8);
            transition: width 0.5s ease;
        }

        .download-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        @keyframes pulse-dot {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        .pulse-dot {
            animation: pulse-dot 1.5s ease-in-out infinite;
        }

        @keyframes gradient-shift {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }

        .gradient-btn {
            background: linear-gradient(135deg, #2563eb, #3b82f6, #6366f1);
            background-size: 200% 200%;
            animation: gradient-shift 3s ease infinite;
        }

        .gradient-btn:active {
            transform: scale(0.97);
        }

        .format-btn.active {
            background: rgba(59, 130, 246, 0.2) !important;
            border-color: #3b82f6 !important;
            color: #60a5fa !important;
        }

        .quality-btn.active {
            border-color: #3b82f6 !important;
            color: #60a5fa !important;
            background: rgba(59, 130, 246, 0.1) !important;
        }

        .modal {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.7);
            backdrop-filter: blur(5px);
            z-index: 999;
            display: none;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .modal.open {
            display: flex;
        }

        .modal-content {
            max-height: 80vh;
            overflow-y: auto;
            width: 100%;
            max-width: 500px;
        }

        .modal-content::-webkit-scrollbar {
            width: 4px;
        }

        .modal-content::-webkit-scrollbar-thumb {
            background: #3b82f6;
            border-radius: 10px;
        }

        .history-item {
            border-bottom: 1px solid rgba(255,255,255,0.05);
            padding: 12px 0;
        }

        [data-theme="light"] .history-item {
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }

        .video-preview {
            position: relative;
            padding-bottom: 56.25%;
            height: 0;
            overflow: hidden;
            border-radius: 12px;
            background: #000;
        }

        .video-preview iframe {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
        }

        .badge-counter {
            position: absolute;
            top: -5px;
            right: -5px;
            background: #ef4444;
            color: white;
            border-radius: 50%;
            width: 18px;
            height: 18px;
            font-size: 9px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
        }

        .theme-toggle {
            cursor: pointer;
            transition: all 0.3s;
        }

        .theme-toggle:hover {
            transform: rotate(30deg);
        }

        .back-btn {
            transition: all 0.3s;
        }
        .back-btn:hover {
            transform: translateX(-3px);
            color: #60a5fa;
        }

        @media (max-width: 480px) {
            .glass-card { padding: 16px; }
            .text-xs { font-size: 9px; }
        }

        .footer-badge {
            background: linear-gradient(135deg, rgba(59,130,246,0.1), rgba(99,102,241,0.1));
            border: 1px solid rgba(59,130,246,0.2);
        }

        .made-by {
            font-weight: 900;
            font-size: 13px;
            background: linear-gradient(135deg, #3b82f6, #6366f1, #8b5cf6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }
        
        .made-by .flag {
            -webkit-text-fill-color: initial;
            font-size: 16px;
        }

        .footer-credit {
            text-align: center;
            padding: 12px 0 4px 0;
            border-top: 1px solid rgba(255,255,255,0.05);
            margin-top: 8px;
        }
        
        [data-theme="light"] .footer-credit {
            border-top: 1px solid rgba(0,0,0,0.05);
        }
        
        .footer-credit .credit-text {
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1px;
            background: linear-gradient(135deg, #3b82f6, #8b5cf6, #ec4899);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        
        .footer-credit .credit-text .flag {
            -webkit-text-fill-color: initial;
            font-size: 18px;
        }
    </style>
</head>
<body>

<div id="app" class="w-full max-w-md glass-card rounded-3xl p-5 shadow-2xl relative overflow-hidden">
    
    <!-- Header -->
    <div class="flex justify-between items-center mb-4">
        <div class="flex items-center gap-2">
            <a href="/" class="back-btn w-10 h-10 rounded-xl bg-slate-900/80 border border-slate-800 flex items-center justify-center text-blue-400 hover:bg-slate-800 transition text-xl">
                <i class="fa-solid fa-arrow-left"></i>
            </a>
            <button onclick="playSound('click'); toggleTheme();" class="w-10 h-10 rounded-xl bg-slate-900/80 border border-slate-800 flex items-center justify-center text-blue-400 hover:bg-slate-800 transition theme-toggle">
                <i id="themeIcon" class="fa-solid fa-moon"></i>
            </button>
        </div>
        <div class="text-center">
            <h1 class="text-xl font-black tracking-widest text-primary flex items-center justify-center gap-2">
                <span class="text-accent">&lt;/&gt;</span> SAMARTH <span class="text-accent">&lt;/&gt;</span>
            </h1>
            <p class="text-[10px] text-accent tracking-widest font-semibold uppercase">YouTube Video Downloader</p>
        </div>
        <div class="relative">
            <button onclick="playSound('click'); openHistory();" class="w-10 h-10 rounded-xl bg-slate-900/80 border border-slate-800 flex items-center justify-center text-blue-400 hover:bg-slate-800 transition">
                <i class="fa-solid fa-clock-rotate-left"></i>
                <span id="historyBadge" class="badge-counter" style="display:none;">0</span>
            </button>
        </div>
    </div>

    <!-- Audio Engine Badge -->
    <div class="flex justify-center mb-4">
        <div class="bg-slate-900/90 border border-emerald-500/30 px-3 py-1.5 rounded-full flex items-center gap-2 text-[10px] text-emerald-400 font-bold tracking-wider">
            <i class="fa-solid fa-wave-square animate-pulse"></i> AUDIO-ENGINE ACTIVE
            <span class="w-2 h-2 rounded-full bg-emerald-400 block shadow-[0_0_8px_#34d399] pulse-dot"></span>
        </div>
    </div>

    <!-- Main Grid -->
    <div class="grid grid-cols-5 gap-3 mb-5 items-center">
        <div class="col-span-1 flex flex-col gap-2.5 justify-center items-center bg-slate-900/40 p-2 rounded-2xl border border-slate-800/60">
            <div class="flex flex-col items-center cursor-pointer group transition hover:scale-105" onclick="playSound('click')"><i class="fa-brands fa-google text-red-500 text-lg"></i><span class="text-[8px] mt-1 text-secondary font-semibold">Google</span></div>
            <div class="flex flex-col items-center cursor-pointer group transition hover:scale-105" onclick="playSound('click')"><i class="fa-brands fa-youtube text-red-600 text-lg"></i><span class="text-[8px] mt-1 text-secondary font-semibold">YouTube</span></div>
            <div class="flex flex-col items-center cursor-pointer group transition hover:scale-105" onclick="playSound('click')"><i class="fa-brands fa-google-drive text-emerald-500 text-lg"></i><span class="text-[8px] mt-1 text-secondary font-semibold">Drive</span></div>
            <div class="flex flex-col items-center cursor-pointer group transition hover:scale-105" onclick="playSound('click')"><i class="fa-solid fa-link text-blue-400 text-lg"></i><span class="text-[8px] mt-1 text-secondary font-semibold">Pastebin</span></div>
            <div class="flex flex-col items-center cursor-pointer group transition hover:scale-105" onclick="playSound('click')"><i class="fa-solid fa-clock-rotate-left text-purple-400 text-lg"></i><span class="text-[8px] mt-1 text-secondary font-semibold">History</span></div>
        </div>

        <div class="col-span-3 flex justify-center items-center relative py-3">
            <div class="absolute inset-0 flex items-center justify-between opacity-20 px-2 pointer-events-none">
                <span class="text-blue-500 text-2xl font-light">|||||||</span>
                <span class="text-blue-500 text-2xl font-light">|||||||</span>
            </div>
            <div class="relative" onclick="playSound('click'); previewVideo();">
                <div class="w-28 h-28 rounded-[2rem] bg-gradient-to-b from-blue-600 to-blue-900 flex items-center justify-center border-2 border-blue-400/60 neon-glow-blue cursor-pointer transform hover:scale-105 transition duration-300">
                    <div class="w-16 h-16 rounded-2xl bg-blue-950/80 flex items-center justify-center border border-blue-400/40 shadow-inner">
                        <i class="fa-solid fa-circle-play text-blue-400 text-3xl"></i>
                    </div>
                </div>
                <div class="absolute -bottom-1 -right-1 bg-white text-black w-8 h-8 rounded-xl flex items-center justify-center text-sm shadow-lg border-2 border-blue-400">
                    <i class="fa-solid fa-arrow-down"></i>
                </div>
            </div>
        </div>

        <div class="col-span-1 flex flex-col gap-2.5 justify-center items-center bg-slate-900/40 p-2 rounded-2xl border border-slate-800/60">
            <div class="flex flex-col items-center cursor-pointer group transition hover:scale-105" onclick="playSound('click')"><i class="fa-solid fa-cloud text-sky-400 text-lg"></i><span class="text-[8px] mt-1 text-secondary font-semibold">OneDrive</span></div>
            <div class="flex flex-col items-center cursor-pointer group transition hover:scale-105" onclick="playSound('click')"><i class="fa-brands fa-dropbox text-blue-500 text-lg"></i><span class="text-[8px] mt-1 text-secondary font-semibold">Dropbox</span></div>
            <div class="flex flex-col items-center cursor-pointer group transition hover:scale-105" onclick="playSound('click')"><i class="fa-solid fa-link-slash text-indigo-400 text-lg"></i><span class="text-[8px] mt-1 text-secondary font-semibold">Shortener</span></div>
            <div class="flex flex-col items-center cursor-pointer group transition hover:scale-105" onclick="playSound('click')"><i class="fa-solid fa-ellipsis text-gray-400 text-lg"></i><span class="text-[8px] mt-1 text-secondary font-semibold">More Tools</span></div>
        </div>
    </div>

    <!-- URL Input -->
    <div class="relative flex items-center bg-input border border-blue-900/60 rounded-xl p-1 mb-5 focus-within:border-blue-500 transition">
        <span class="pl-3 pr-2 text-blue-400/60"><i class="fa-solid fa-link"></i></span>
        <input id="urlInput" type="text" placeholder="Paste your video URL link here..." class="w-full bg-transparent py-2.5 text-xs text-primary placeholder-gray-500 focus:outline-none">
        <button onclick="playSound('click'); startDownload();" class="bg-blue-600/20 text-blue-400 border border-blue-500/40 text-xs font-bold px-4 py-2.5 rounded-lg hover:bg-blue-600 hover:text-white transition flex items-center gap-1 active:scale-95">
            <i class="fa-solid fa-paste"></i> PASTE
        </button>
    </div>

    <!-- Formats -->
    <div class="mb-4">
        <div class="flex justify-between items-center mb-2">
            <span class="text-[10px] uppercase tracking-widest font-bold text-secondary"><i class="fa-solid fa-sliders mr-1"></i> Choose Format</span>
            <span class="text-[9px] bg-purple-900/40 border border-purple-500/30 text-purple-300 font-bold px-2 py-0.5 rounded-full"><i class="fa-solid fa-star text-[7px] mr-1"></i>RECOMMENDED</span>
        </div>
        <div class="grid grid-cols-5 gap-2">
            <button class="format-btn active bg-blue-600/90 text-white border border-blue-400 rounded-xl py-2 text-xs font-bold flex flex-col items-center gap-1 shadow-[0_0_10px_rgba(37,99,235,0.4)]" data-format="mp4" onclick="playSound('click'); selectFormat(this)">
                <i class="fa-solid fa-video"></i> MP4
            </button>
            <button class="format-btn bg-slate-950 border border-slate-800 text-gray-400 rounded-xl py-2 text-xs font-bold flex flex-col items-center gap-1 hover:border-slate-700 transition" data-format="mp3" onclick="playSound('click'); selectFormat(this)">
                <i class="fa-solid fa-music"></i> MP3
            </button>
            <button class="format-btn bg-slate-950 border border-slate-800 text-gray-400 rounded-xl py-2 text-xs font-bold flex flex-col items-center gap-1 hover:border-slate-700 transition" data-format="webm" onclick="playSound('click'); selectFormat(this)">
                <i class="fa-solid fa-file-video"></i> WEBM
            </button>
            <button class="format-btn bg-slate-950 border border-slate-800 text-gray-400 rounded-xl py-2 text-xs font-bold flex flex-col items-center gap-1 hover:border-slate-700 transition" data-format="m4a" onclick="playSound('click'); selectFormat(this)">
                <i class="fa-solid fa-file-audio"></i> M4A
            </button>
            <button class="format-btn bg-slate-950 border border-slate-800 text-gray-400 rounded-xl py-2 text-xs font-bold flex flex-col items-center gap-1 hover:border-slate-700 transition" data-format="more" onclick="playSound('click'); selectFormat(this)">
                <i class="fa-solid fa-grid-2"></i> MORE
            </button>
        </div>
    </div>

    <!-- Quality -->
    <div class="mb-5">
        <div class="mb-2">
            <span class="text-[10px] uppercase tracking-widest font-bold text-secondary"><i class="fa-solid fa-display mr-1"></i> Select Quality</span>
        </div>
        <div class="grid grid-cols-5 gap-2">
            <button class="quality-btn active bg-transparent border border-blue-500/80 text-blue-400 rounded-xl py-1.5 text-center shadow-[0_0_8px_rgba(59,130,246,0.2)]" data-quality="1080" onclick="playSound('click'); selectQuality(this)">
                <div class="text-[11px] font-bold">1080p</div>
                <div class="text-[7px] text-blue-300 font-medium">FULL HD</div>
            </button>
            <button class="quality-btn bg-slate-950 border border-slate-800 text-gray-400 rounded-xl py-1.5 text-center hover:border-slate-700 transition" data-quality="720" onclick="playSound('click'); selectQuality(this)">
                <div class="text-[11px] font-bold">720p</div>
                <div class="text-[7px] font-medium">HD</div>
            </button>
            <button class="quality-btn bg-slate-950 border border-slate-800 text-gray-400 rounded-xl py-1.5 text-center hover:border-slate-700 transition" data-quality="480" onclick="playSound('click'); selectQuality(this)">
                <div class="text-[11px] font-bold">480p</div>
                <div class="text-[7px] font-medium">SD</div>
            </button>
            <button class="quality-btn bg-slate-950 border border-slate-800 text-gray-400 rounded-xl py-1.5 text-center hover:border-slate-700 transition" data-quality="360" onclick="playSound('click'); selectQuality(this)">
                <div class="text-[11px] font-bold">360p</div>
                <div class="text-[7px] font-medium">SD</div>
            </button>
            <button class="quality-btn bg-slate-950 border border-slate-800 text-gray-400 rounded-xl py-1.5 text-center hover:border-slate-700 transition" data-quality="144" onclick="playSound('click'); selectQuality(this)">
                <div class="text-[11px] font-bold">144p</div>
                <div class="text-[7px] font-medium">LOW</div>
            </button>
        </div>
    </div>

    <!-- Download Button -->
    <button id="downloadBtn" onclick="playSound('download'); triggerDownload();" class="gradient-btn w-full text-white rounded-xl py-3.5 px-4 font-black tracking-widest text-sm flex justify-between items-center border border-blue-400/40 shadow-lg hover:brightness-110 active:scale-[0.98] transition mb-5">
        <div></div>
        <span class="flex items-center gap-2"><i class="fa-solid fa-cloud-arrow-down"></i> DOWNLOAD ASSET</span>
        <div class="w-7 h-7 rounded-full bg-blue-950/40 flex items-center justify-center border border-blue-300/30 text-[10px]">
            <i class="fa-solid fa-rocket"></i>
        </div>
    </button>

    <!-- Progress -->
    <div id="progressWrap" class="bg-slate-950/70 border border-slate-900 rounded-2xl p-4 mb-4" style="display:none;">
        <div class="text-[10px] font-bold tracking-wider text-gray-400 uppercase mb-3 flex items-center gap-1">
            <i class="fa-solid fa-wave-square text-blue-400"></i> Download Status
        </div>
        <div class="mb-4">
            <div class="w-full bg-slate-900 rounded-full h-2 overflow-hidden border border-slate-800 relative">
                <div id="progressFill" class="progress-fill h-full rounded-full w-0"></div>
            </div>
            <div class="flex justify-end text-[10px] font-bold text-blue-400 mt-1"><span id="progressPercent">0</span>%</div>
        </div>
        <div class="grid grid-cols-4 gap-2 text-left">
            <div>
                <div class="text-[8px] text-gray-500 font-bold uppercase">ETA</div>
                <div id="etaDisplay" class="text-[11px] font-bold text-white mt-0.5">--:--:--</div>
            </div>
            <div>
                <div class="text-[8px] text-gray-500 font-bold uppercase">Speed</div>
                <div id="speedDisplay" class="text-[11px] font-bold text-emerald-400 mt-0.5">0 MB/s</div>
            </div>
            <div>
                <div class="text-[8px] text-gray-500 font-bold uppercase">Size</div>
                <div id="sizeDisplay" class="text-[11px] font-bold text-white mt-0.5">0 MB</div>
            </div>
            <div>
                <div class="text-[8px] text-gray-500 font-bold uppercase">Status</div>
                <div id="statusDisplay" class="text-[10px] font-bold text-amber-400 mt-0.5">PENDING</div>
            </div>
        </div>
    </div>

    <!-- Footer - Only Made By -->
    <div class="footer-credit">
        <span class="credit-text">
            𝐌𝐚𝐝𝐞 𝐛𝐲 𝐒𝐚𝐦𝐚𝐫𝐭𝐡 <span class="flag">🇮🇳</span>
        </span>
    </div>

</div>

<!-- Video Preview Modal -->
<div id="previewModal" class="modal">
    <div class="modal-content glass-card rounded-3xl p-6 relative">
        <button onclick="playSound('click'); closePreview();" class="absolute top-3 right-3 w-8 h-8 rounded-full bg-red-500/20 border border-red-500/40 text-red-400 flex items-center justify-center hover:bg-red-500 hover:text-white transition">
            <i class="fa-solid fa-xmark"></i>
        </button>
        <h3 class="text-lg font-bold text-primary mb-3">📹 Video Preview</h3>
        <div id="videoPreviewContainer" class="video-preview mb-3">
            <div id="previewPlaceholder" class="flex items-center justify-center h-full bg-slate-900 rounded-xl text-secondary text-sm">
                <div class="text-center">
                    <i class="fa-solid fa-play-circle text-4xl text-blue-400 mb-2"></i>
                    <p>Paste a URL and click the play button to preview</p>
                </div>
            </div>
        </div>
        <div id="videoInfo" class="text-xs text-secondary space-y-1">
            <p><span class="font-bold text-primary">Title:</span> <span id="previewTitle">-</span></p>
            <p><span class="font-bold text-primary">Channel:</span> <span id="previewChannel">-</span></p>
            <p><span class="font-bold text-primary">Duration:</span> <span id="previewDuration">-</span></p>
        </div>
    </div>
</div>

<!-- History Modal -->
<div id="historyModal" class="modal">
    <div class="modal-content glass-card rounded-3xl p-6 relative">
        <button onclick="playSound('click'); closeHistory();" class="absolute top-3 right-3 w-8 h-8 rounded-full bg-red-500/20 border border-red-500/40 text-red-400 flex items-center justify-center hover:bg-red-500 hover:text-white transition">
            <i class="fa-solid fa-xmark"></i>
        </button>
        <h3 class="text-lg font-bold text-primary mb-3">📋 Download History</h3>
        <div id="historyList" class="space-y-2 max-h-96 overflow-y-auto pr-2">
            <div class="text-center text-secondary text-sm py-8">
                <i class="fa-solid fa-inbox text-3xl mb-2 opacity-30"></i>
                <p>No downloads yet</p>
            </div>
        </div>
        <button onclick="playSound('click'); clearHistory();" class="mt-3 w-full bg-red-500/20 border border-red-500/40 text-red-400 rounded-xl py-2 text-xs font-bold hover:bg-red-500 hover:text-white transition">
            <i class="fa-solid fa-trash"></i> Clear All History
        </button>
    </div>
</div>

<script>
// ===== SOUND SYSTEM =====
function playSound(type) {
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        gainNode.gain.value = 0.15;
        
        switch(type) {
            case 'click':
                oscillator.frequency.value = 800;
                oscillator.type = 'sine';
                gainNode.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.1);
                oscillator.start(audioContext.currentTime);
                oscillator.stop(audioContext.currentTime + 0.08);
                break;
            case 'download':
                oscillator.frequency.value = 600;
                oscillator.type = 'square';
                gainNode.gain.value = 0.1;
                gainNode.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.2);
                oscillator.start(audioContext.currentTime);
                oscillator.stop(audioContext.currentTime + 0.15);
                break;
            case 'success':
                oscillator.frequency.value = 1200;
                oscillator.type = 'sine';
                gainNode.gain.value = 0.12;
                gainNode.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.3);
                oscillator.start(audioContext.currentTime);
                oscillator.stop(audioContext.currentTime + 0.25);
                setTimeout(() => {
                    const osc2 = audioContext.createOscillator();
                    const gain2 = audioContext.createGain();
                    osc2.connect(gain2);
                    gain2.connect(audioContext.destination);
                    gain2.gain.value = 0.08;
                    osc2.frequency.value = 1500;
                    osc2.type = 'sine';
                    gain2.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.2);
                    osc2.start(audioContext.currentTime);
                    osc2.stop(audioContext.currentTime + 0.15);
                }, 100);
                break;
            case 'error':
                oscillator.frequency.value = 300;
                oscillator.type = 'sawtooth';
                gainNode.gain.value = 0.1;
                gainNode.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.3);
                oscillator.start(audioContext.currentTime);
                oscillator.stop(audioContext.currentTime + 0.25);
                break;
            case 'complete':
                oscillator.frequency.value = 880;
                oscillator.type = 'sine';
                gainNode.gain.value = 0.12;
                gainNode.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.4);
                oscillator.start(audioContext.currentTime);
                oscillator.stop(audioContext.currentTime + 0.3);
                setTimeout(() => {
                    const osc2 = audioContext.createOscillator();
                    const gain2 = audioContext.createGain();
                    osc2.connect(gain2);
                    gain2.connect(audioContext.destination);
                    gain2.gain.value = 0.1;
                    osc2.frequency.value = 1108.73;
                    osc2.type = 'sine';
                    gain2.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.3);
                    osc2.start(audioContext.currentTime);
                    osc2.stop(audioContext.currentTime + 0.2);
                }, 150);
                break;
            default: return;
        }
    } catch(e) {}
}

// ===== REST OF THE CODE =====
let currentTaskId = null;
let progressInterval = null;
let selectedFormat = 'mp4';
let selectedQuality = '1080';
let currentTheme = localStorage.getItem('theme') || 'dark';

function toggleTheme() {
    if (currentTheme === 'dark') {
        currentTheme = 'light';
        document.documentElement.setAttribute('data-theme', 'light');
        document.getElementById('themeIcon').className = 'fa-solid fa-sun';
    } else {
        currentTheme = 'dark';
        document.documentElement.removeAttribute('data-theme');
        document.getElementById('themeIcon').className = 'fa-solid fa-moon';
    }
    localStorage.setItem('theme', currentTheme);
}

if (currentTheme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
    document.getElementById('themeIcon').className = 'fa-solid fa-sun';
}

function selectFormat(el) {
    document.querySelectorAll('.format-btn').forEach(b => {
        b.classList.remove('active', 'bg-blue-600/90', 'text-white', 'border-blue-400', 'shadow-[0_0_10px_rgba(37,99,235,0.4)]');
        b.classList.add('bg-slate-950', 'text-gray-400', 'border-slate-800');
    });
    el.classList.add('active', 'bg-blue-600/90', 'text-white', 'border-blue-400', 'shadow-[0_0_10px_rgba(37,99,235,0.4)]');
    selectedFormat = el.dataset.format;
}

function selectQuality(el) {
    document.querySelectorAll('.quality-btn').forEach(b => {
        b.classList.remove('active', 'border-blue-500/80', 'text-blue-400', 'shadow-[0_0_8px_rgba(59,130,246,0.2)]');
        b.classList.add('bg-slate-950', 'text-gray-400', 'border-slate-800');
    });
    el.classList.add('active', 'border-blue-500/80', 'text-blue-400', 'shadow-[0_0_8px_rgba(59,130,246,0.2)]');
    selectedQuality = el.dataset.quality;
}

function previewVideo() {
    const url = document.getElementById('urlInput').value.trim();
    if (!url) {
        playSound('error');
        alert('Please paste a YouTube URL first');
        return;
    }
    document.getElementById('previewModal').classList.add('open');
    document.getElementById('previewPlaceholder').innerHTML = '<div class="flex items-center justify-center h-full"><i class="fa-solid fa-spinner fa-spin text-3xl text-blue-400"></i></div>';
    fetch(`/api/metadata?url=${encodeURIComponent(url)}`)
        .then(res => res.json())
        .then(data => {
            const videoId = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\?\/]+)/);
            if (videoId) {
                document.getElementById('previewPlaceholder').innerHTML = `
                    <iframe src="https://www.youtube.com/embed/${videoId[1]}?autoplay=1" allowfullscreen allow="autoplay; encrypted-media"></iframe>
                `;
            }
            document.getElementById('previewTitle').textContent = data.title || 'Unknown';
            document.getElementById('previewChannel').textContent = data.uploader || 'Unknown';
            const mins = Math.floor(data.duration / 60);
            const secs = data.duration % 60;
            document.getElementById('previewDuration').textContent = `${mins}:${String(secs).padStart(2, '0')}`;
            playSound('success');
        })
        .catch(() => {
            playSound('error');
            document.getElementById('previewPlaceholder').innerHTML = `
                <div class="flex items-center justify-center h-full text-red-400">
                    <div class="text-center"><i class="fa-solid fa-circle-exclamation text-3xl mb-2"></i><p>Failed to load preview</p></div>
                </div>
            `;
        });
}

function closePreview() {
    document.getElementById('previewModal').classList.remove('open');
}

function openHistory() {
    document.getElementById('historyModal').classList.add('open');
    loadHistory();
}

function closeHistory() {
    document.getElementById('historyModal').classList.remove('open');
}

function loadHistory() {
    fetch('/api/history')
        .then(res => res.json())
        .then(data => {
            const list = document.getElementById('historyList');
            if (data.length === 0) {
                list.innerHTML = `<div class="text-center text-secondary text-sm py-8"><i class="fa-solid fa-inbox text-3xl mb-2 opacity-30"></i><p>No downloads yet</p></div>`;
                document.getElementById('historyBadge').style.display = 'none';
                return;
            }
            document.getElementById('historyBadge').style.display = 'flex';
            document.getElementById('historyBadge').textContent = data.length;
            list.innerHTML = data.reverse().map(item => `
                <div class="history-item">
                    <div class="flex justify-between items-start">
                        <div class="flex-1 min-w-0">
                            <p class="text-sm font-semibold text-primary truncate">${item.title || 'Unknown'}</p>
                            <p class="text-[10px] text-secondary truncate">${item.filename || 'Unknown'}</p>
                            <div class="flex gap-3 mt-1 text-[9px] text-secondary">
                                <span><i class="fa-regular fa-file"></i> ${item.format || 'Unknown'}</span>
                                <span><i class="fa-regular fa-calendar"></i> ${item.date || 'Unknown'}</span>
                                <span><i class="fa-regular fa-hard-drive"></i> ${item.size_str || '0 MB'}</span>
                            </div>
                        </div>
                        <span class="text-[9px] bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded-full whitespace-nowrap ml-2">
                            <i class="fa-regular fa-eye"></i> ${item.downloads || 1}x
                        </span>
                    </div>
                </div>
            `).join('');
        });
}

function clearHistory() {
    if (confirm('Clear all download history?')) {
        fetch('/api/history/clear', { method: 'POST' })
            .then(() => { loadHistory(); document.getElementById('historyBadge').style.display = 'none'; playSound('success'); });
    }
}

function startDownload() {
    const url = document.getElementById('urlInput').value.trim();
    if (!url) {
        playSound('error');
        alert('Please paste a YouTube URL');
        return;
    }
    const btn = document.getElementById('downloadBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="flex items-center gap-2"><i class="fa-solid fa-spinner fa-spin"></i> DOWNLOADING...</span><div class="w-7 h-7 rounded-full bg-blue-950/40 flex items-center justify-center border border-blue-300/30 text-[10px]"><i class="fa-solid fa-spinner fa-spin"></i></div>';
    const wrap = document.getElementById('progressWrap');
    wrap.style.display = 'block';
    document.getElementById('statusDisplay').textContent = '⏳ INITIALIZING';
    document.getElementById('progressPercent').textContent = '0';
    document.getElementById('progressFill').style.width = '0%';
    document.getElementById('etaDisplay').textContent = '--:--:--';
    document.getElementById('speedDisplay').textContent = '0 MB/s';
    document.getElementById('sizeDisplay').textContent = '0 MB';
    
    const isAudio = selectedFormat === 'mp3' || selectedFormat === 'm4a';
    const endpoint = isAudio ? '/api/start_audio' : '/api/start_video';
    
    fetch(`${endpoint}?url=${encodeURIComponent(url)}&quality=${selectedQuality}`)
        .then(res => res.json())
        .then(data => {
            if (data.task_id) {
                currentTaskId = data.task_id;
                if (progressInterval) clearInterval(progressInterval);
                progressInterval = setInterval(checkProgress, 500);
                playSound('download');
            } else {
                throw new Error('No task ID returned');
            }
        })
        .catch(err => {
            playSound('error');
            alert('Download failed: ' + err.message);
            resetButton();
        });
}

function checkProgress() {
    if (!currentTaskId) return;
    fetch(`/api/progress/${currentTaskId}`)
        .then(res => res.json())
        .then(data => {
            const percent = data.percent || 0;
            document.getElementById('progressPercent').textContent = percent;
            document.getElementById('progressFill').style.width = percent + '%';
            const statusEl = document.getElementById('statusDisplay');
            const statusMap = { 'pending': '⏳ PENDING', 'downloading': '⬇️ DOWNLOADING...', 'processing': '🔄 PROCESSING', 'completed': '✅ COMPLETED', 'failed': '❌ FAILED' };
            statusEl.textContent = statusMap[data.status] || data.status;
            if (data.speed) {
                const speedMB = (data.speed / 1024 / 1024).toFixed(2);
                document.getElementById('speedDisplay').textContent = speedMB + ' MB/s';
            }
            if (data.eta !== undefined && data.eta !== null && data.eta > 0) {
                const eta = data.eta;
                const hours = Math.floor(eta / 3600);
                const minutes = Math.floor((eta % 3600) / 60);
                const seconds = Math.floor(eta % 60);
                document.getElementById('etaDisplay').textContent = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
            }
            if (data.total_str) {
                document.getElementById('sizeDisplay').textContent = data.total_str;
            } else if (data.total) {
                const sizeMB = (data.total / 1024 / 1024).toFixed(1);
                document.getElementById('sizeDisplay').textContent = sizeMB + ' MB';
            }
            if (data.status === 'completed') {
                clearInterval(progressInterval);
                statusEl.textContent = '✅ DOWNLOAD COMPLETE!';
                statusEl.className = 'text-[10px] font-bold text-emerald-400 mt-0.5';
                resetButton();
                document.getElementById('downloadBtn').innerHTML = '<span class="flex items-center gap-2"><i class="fa-solid fa-check-circle"></i> DOWNLOADED</span><div class="w-7 h-7 rounded-full bg-green-950/40 flex items-center justify-center border border-green-300/30 text-[10px]"><i class="fa-solid fa-check"></i></div>';
                playSound('complete');
                setTimeout(() => { window.location.href = `/api/retrieve/${currentTaskId}`; }, 1500);
            } else if (data.status === 'failed') {
                clearInterval(progressInterval);
                statusEl.textContent = '❌ ' + (data.error || 'FAILED');
                statusEl.className = 'text-[10px] font-bold text-red-400 mt-0.5';
                resetButton();
                document.getElementById('downloadBtn').innerHTML = '<span class="flex items-center gap-2"><i class="fa-solid fa-cloud-arrow-down"></i> RETRY</span><div class="w-7 h-7 rounded-full bg-blue-950/40 flex items-center justify-center border border-blue-300/30 text-[10px]"><i class="fa-solid fa-rocket"></i></div>';
                playSound('error');
            }
        })
        .catch(err => console.error('Progress error:', err));
}

function resetButton() {
    document.getElementById('downloadBtn').disabled = false;
}

function triggerDownload() {
    if (!document.getElementById('downloadBtn').disabled) {
        startDownload();
    }
}

document.addEventListener('DOMContentLoaded', function() {
    fetch('/api/history')
        .then(res => res.json())
        .then(data => {
            if (data.length > 0) {
                document.getElementById('historyBadge').style.display = 'flex';
                document.getElementById('historyBadge').textContent = data.length;
            }
        });
});
</script>
</body>
</html>"""

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
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    try:
        ydl_opts = {'quiet': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return jsonify({
                "title": info.get('title', 'Unknown'),
                "thumbnail": info.get('thumbnail', ''),
                "duration": info.get('duration', 0),
                "uploader": info.get('uploader', 'Unknown')
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/start_audio')
def api_start_audio():
    url = request.args.get('url')
    quality = request.args.get('quality', '1080')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    task_id = str(uuid.uuid4())
    PROGRESS_TRACKER[task_id] = {"status": "pending", "percent": 0}
    threading.Thread(target=background_download, args=(url, task_id, True, quality)).start()
    return jsonify({"task_id": task_id})

@app.route('/api/start_video')
def api_start_video():
    url = request.args.get('url')
    quality = request.args.get('quality', '1080')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    task_id = str(uuid.uuid4())
    PROGRESS_TRACKER[task_id] = {"status": "pending", "percent": 0}
    threading.Thread(target=background_download, args=(url, task_id, False, quality)).start()
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
            history = load_history()
            for item in history:
                if item.get('id') == task_id:
                    item['downloads'] = item.get('downloads', 0) + 1
                    break
            save_history(history)
            return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)
        for file in os.listdir(DOWNLOAD_DIR):
            if task_id in file:
                return send_from_directory(DOWNLOAD_DIR, file, as_attachment=True)
        return "File not found", 404
    return "Download not complete", 404

if __name__ == '__main__':
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║     SAMARTH YouTube Downloader v2.5.0 PRO               ║
    ║                                                          ║
    ║     🌟 Features:                                        ║
    ║     - Premium Landing Page                              ║
    ║     - Dark/Light Theme Switching                        ║
    ║     - Video Preview with Metadata                      ║
    ║     - Download History with View Counter                ║
    ║     - Original Filename Preservation                   ║
    ║     - Click Sounds with Feedback                        ║
    ║     - Made by Samarth 🇮🇳                              ║
    ║                                                          ║
    ║     🚀 Running on: http://localhost:8080               ║
    ║     Press Ctrl+C to stop                                ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    app.run(debug=False, port=8080, host='0.0.0.0')
