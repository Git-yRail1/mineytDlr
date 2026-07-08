from flask import Flask, render_template, request, jsonify, send_from_directory
import yt_dlp
import os
import subprocess
import re
import shutil

app = Flask(__name__)

# Core directory configurations
STORAGE_DIR = "/tmp"
DOWNLOADS_DIR = os.path.join(STORAGE_DIR, "downloads")

os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# Path where the temporary cookies file will be generated on the server
COOKIE_FILE_PATH = os.path.join(STORAGE_DIR, "youtube_cookies.txt")

def clean_filename(title):
    return re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')

# --- COOKIE ENGINE SHIELD ---
cookies_data = os.environ.get("YOUTUBE_COOKIES", "").strip()
if cookies_data:
    try:
        with open(COOKIE_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(cookies_data)
        print("✅ Cookie asset written successfully.")
    except Exception as e:
        print(f"❌ Failed to write temporary cookie file: {e}")

BYPASS_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'geo_bypass': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['web', 'ios'],
            'skip': ['dash', 'hls']
        }
    },
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
}

if os.path.exists(COOKIE_FILE_PATH):
    BYPASS_OPTS['cookiefile'] = COOKIE_FILE_PATH

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/files', methods=['GET'])
def list_files():
    try:
        files = os.listdir(DOWNLOADS_DIR)
        return jsonify({'files': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/files/<filename>', methods=['GET'])
def get_file(filename):
    # Safely deliver static download files without directory traversal vulnerabilities
    return send_from_directory(DOWNLOADS_DIR, filename, as_attachment=True)

@app.route('/clear', methods=['POST'])
def clear_storage():
    try:
        for item in os.listdir(DOWNLOADS_DIR):
            path = os.path.join(DOWNLOADS_DIR, item)
            if os.path.isfile(path) or os.path.islink(path):
                os.unlink(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        return jsonify({'message': 'Permanent file store cleared successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/scan', methods=['POST'])
def scan_video():
    data = request.json or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'error': 'URL cannot be empty'}), 400

    try:
        scan_opts = BYPASS_OPTS.copy()
        with yt_dlp.YoutubeDL(scan_opts) as ydl:
            meta = ydl.extract_info(url, download=False)
            formats = meta.get('formats', [])
            
        seen_heights = set()
        available_resolutions = []
        
        for f in formats:
            height = f.get('height')
            if height and f.get('vcodec') != 'none' and height not in seen_heights:
                seen_heights.add(height)
                available_resolutions.append({
                    'height': height,
                    'ext': 'mp4' if f.get('ext') == 'mp4' else f.get('ext')
                })
        
        available_resolutions.sort(key=lambda x: x['height'], reverse=True)
        return jsonify({
            'title': meta.get('title', 'Unknown Video'),
            'resolutions': available_resolutions
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])
def download_video():
    data = request.json or {}
    url = data.get('url', '').strip()
    target_height = data.get('resolution')

    if not url or not target_height:
        return jsonify({'error': 'Missing URL or Resolution parameters'}), 400

    try:
        with yt_dlp.YoutubeDL(BYPASS_OPTS) as ydl:
            meta = ydl.extract_info(url, download=False)
            safe_title = clean_filename(meta.get('title', 'video'))

        video_pattern = os.path.join(STORAGE_DIR, f"temp_v_{safe_title}")
        audio_pattern = os.path.join(STORAGE_DIR, f"temp_a_{safe_title}")
        
        # CHANGED: The target path points directly into the permanent directory location
        output_filename = f"{safe_title}_{target_height}p.mp4"
        output_file = os.path.join(DOWNLOADS_DIR, output_filename)

        video_opts = BYPASS_OPTS.copy()
        video_opts.update({
            'format': f'bestvideo[height={target_height}]/bestvideo[height<={target_height}]',
            'outtmpl': f"{video_pattern}.%(ext)s"
        })

        audio_opts = BYPASS_OPTS.copy()
        audio_opts.update({
            'format': 'bestaudio',
            'outtmpl': f"{audio_pattern}.%(ext)s"
        })

        with yt_dlp.YoutubeDL(video_opts) as ydl:
            ydl.download([url])
        with yt_dlp.YoutubeDL(audio_opts) as ydl:
            ydl.download([url])

        files = os.listdir(STORAGE_DIR)
        v_match = [f for f in files if f.startswith(f"temp_v_{safe_title}")]
        a_match = [f for f in files if f.startswith(f"temp_a_{safe_title}")]

        if not v_match or not a_match:
            return jsonify({'error': 'Failed to capture structural source streams'}), 500

        video_file = os.path.join(STORAGE_DIR, v_match[0])
        audio_file = os.path.join(STORAGE_DIR, a_match[0])

        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-i', video_file,
            '-i', audio_file,
            '-c:v', 'copy',
            '-c:a', 'aac',
            output_file
        ]
        
        process = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if os.path.exists(video_file): os.remove(video_file)
        if os.path.exists(audio_file): os.remove(audio_file)

        if process.returncode == 0 and os.path.exists(output_file):
            # Return JSON instead of binary data streams
            return jsonify({'success': True, 'filename': output_filename})
        else:
            return jsonify({'error': f'Muxing compilation failed: {process.stderr}'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)