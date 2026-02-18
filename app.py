"""
VidGrab - Video Downloader API
YouTube, Instagram, Twitter supported
"""

from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import yt_dlp
import os
import re
import threading
import time
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

# Configuration
DOWNLOAD_FOLDER = '/tmp/downloads'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def sanitize_filename(filename):
    """Clean filename for saving"""
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    return secure_filename(filename)[:50]

def cleanup_old_files():
    """Delete files older than 1 hour"""
    while True:
        time.sleep(3600)
        current_time = time.time()
        for filename in os.listdir(DOWNLOAD_FOLDER):
            file_path = os.path.join(DOWNLOAD_FOLDER, filename)
            try:
                if os.path.getmtime(file_path) < current_time - 3600:
                    os.remove(file_path)
                    print(f"Cleaned: {filename}")
            except:
                pass

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

@app.route('/')
def index():
    """Home page with frontend"""
    return render_template('index.html')

@app.route('/api/info', methods=['POST'])
def get_video_info():
    """Get video information"""
    try:
        data = request.get_json()
        url = data.get('url', '')
        
        if not url:
            return jsonify({'success': False, 'error': 'No URL provided'}), 400

        # yt-dlp options
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'referer': 'https://www.youtube.com/',
            'headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = []
            seen_qualities = set()
            
            # Video formats
            for f in info.get('formats', []):
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    height = f.get('height', 0)
                    if height and height not in seen_qualities:
                        seen_qualities.add(height)
                        formats.append({
                            'format_id': f['format_id'],
                            'quality': f'{height}p',
                            'height': height,
                            'ext': f['ext']
                        })
            
            # Sort by quality
            formats.sort(key=lambda x: x['height'], reverse=True)
            
            return jsonify({
                'success': True,
                'title': info.get('title', 'Unknown'),
                'uploader': info.get('uploader', 'Unknown'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'webpage_url': info.get('webpage_url', url),
                'platform': info.get('extractor', 'Unknown'),
                'formats': formats
            })
            
    except Exception as e:
        print(f"Error in get_video_info: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'Failed to extract video info: {str(e)}'
        }), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    """Download video or audio"""
    try:
        data = request.get_json()
        url = data.get('url', '')
        download_format = data.get('format', 'video')
        quality = data.get('quality', '720p')
        
        if not url:
            return jsonify({'success': False, 'error': 'No URL provided'}), 400

        # Get video info first
        ydl_opts_info = {
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(url, download=False)
            title = sanitize_filename(info['title'])
        
        # Set filename and options
        if download_format == 'audio':
            filename_base = f"{title}_audio"
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(DOWNLOAD_FOLDER, f'{filename_base}.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': quality.replace('kbps', ''),
                }],
                'quiet': True,
                'no_warnings': True,
            }
            final_ext = 'mp3'
        else:
            height = int(quality.replace('p', ''))
            filename_base = f"{title}_{quality}"
            ydl_opts = {
                'format': f'bestvideo[height<={height}]+bestaudio/best[height<={height}]',
                'outtmpl': os.path.join(DOWNLOAD_FOLDER, f'{filename_base}.%(ext)s'),
                'merge_output_format': 'mp4',
                'quiet': True,
                'no_warnings': True,
            }
            final_ext = 'mp4'
        
        # Download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Find downloaded file
        final_filename = f"{filename_base}.{final_ext}"
        final_path = os.path.join(DOWNLOAD_FOLDER, final_filename)
        
        # Check if exists
        if not os.path.exists(final_path):
            for f in os.listdir(DOWNLOAD_FOLDER):
                if f.startswith(filename_base):
                    final_filename = f
                    final_path = os.path.join(DOWNLOAD_FOLDER, f)
                    break
        
        return jsonify({
            'success': True,
            'filename': final_filename,
            'download_url': f'/api/file/{final_filename}'
        })
        
    except Exception as e:
        print(f"Error in download_video: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'Download failed: {str(e)}'
        }), 500

@app.route('/api/file/<filename>')
def serve_file(filename):
    """Serve downloaded file"""
    try:
        file_path = os.path.join(DOWNLOAD_FOLDER, filename)
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
        
        return send_file(file_path, as_attachment=True)
        
    except Exception as e:
        print(f"Error in serve_file: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'OK',
        'timestamp': time.time(),
        'downloads_folder': os.path.exists(DOWNLOAD_FOLDER)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)