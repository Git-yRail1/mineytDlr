from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import os
import subprocess
import re

app = Flask(__name__)

# Ensure absolute temporary and download storage zones exist
STORAGE_DIR = "/tmp"
os.makedirs(STORAGE_DIR, exist_ok=True)

def clean_filename(title):
    return re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/scan', methods=['POST'])
def scan_video():
    data = request.json or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'error': 'URL cannot be empty'}), 400

    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
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
        # Step 1: Gather clean title information
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            meta = ydl.extract_info(url, download=False)
            safe_title = clean_filename(meta.get('title', 'video'))

        # Construct temporary operational paths
        video_pattern = os.path.join(STORAGE_DIR, f"temp_v_{safe_title}")
        audio_pattern = os.path.join(STORAGE_DIR, f"temp_a_{safe_title}")
        output_file = os.path.join(STORAGE_DIR, f"{safe_title}_{target_height}p.mp4")

        # Step 2: Download isolated tracks
        video_opts = {
            'format': f'bestvideo[height={target_height}]/bestvideo[height<={target_height}]',
            'outtmpl': f"{video_pattern}.%(ext)s",
            'quiet': True
        }
        audio_opts = {
            'format': 'bestaudio',
            'outtmpl': f"{audio_pattern}.%(ext)s",
            'quiet': True
        }

        with yt_dlp.YoutubeDL(video_opts) as ydl:
            ydl.download([url])
        with yt_dlp.YoutubeDL(audio_opts) as ydl:
            ydl.download([url])

        # Step 3: Dynamically scan for extension formats downloaded
        files = os.listdir(STORAGE_DIR)
        v_match = [f for f in files if f.startswith(f"temp_v_{safe_title}")]
        a_match = [f for f in files if f.startswith(f"temp_a_{safe_title}")]

        if not v_match or not a_match:
            return jsonify({'error': 'Failed to capture structural source streams'}), 500

        video_file = os.path.join(STORAGE_DIR, v_match[0])
        audio_file = os.path.join(STORAGE_DIR, a_match[0])

        # Step 4: Combine via system ffmpeg
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-i', video_file,
            '-i', audio_file,
            '-c:v', 'copy',
            '-c:a', 'aac',
            output_file
        ]
        
        process = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # Cleanup temporary chunks immediately
        if os.path.exists(video_file): os.remove(video_file)
        if os.path.exists(audio_file): os.remove(audio_file)

        if process.returncode == 0 and os.path.exists(output_file):
            return send_file(output_file, as_attachment=True, download_name=os.path.basename(output_file))
        else:
            return jsonify({'error': f'Muxing compilation failed: {process.stderr}'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Railway passes a dynamic PORT environment variable we must listen to
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)