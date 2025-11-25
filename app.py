from flask import Flask, render_template, request, redirect, session, url_for, flash, send_file, jsonify
import mysql.connector
from mysql.connector import Error
import os
import threading
import time
import re
import subprocess
import shutil
import json
from database import get_db_connection
from downloader import download_youtube_video, extract_audio_from_video, transcribe_audio, get_video_title_from_youtube, validate_video_file, repair_video_file
import warnings
warnings.filterwarnings("ignore", category=UserWarning)
# Use this import:
from enhanced_qa_processor import clean_qa_processor as qa_processor
from database import add_question, update_answer, get_video_questions, add_feedback
import hashlib


app = Flask(__name__)
app.secret_key = "your_secret_key_here"
BASE_DOWNLOAD_FOLDER = "static/downloads"
os.makedirs(BASE_DOWNLOAD_FOLDER, exist_ok=True)

# Initialize database
from database import init_db
init_db()

# Download concurrency control
DOWNLOAD_SEMAPHORE = threading.Semaphore(2)  # Max 2 concurrent downloads

# ----- Validation Functions -----
def is_valid_youtube_url(url):
    """Validate YouTube URL"""
    patterns = [
        r'^https?://(www\.)?youtube\.com/watch\?v=[\w-]+',
        r'^https?://youtu\.be/[\w-]+',
        r'^https?://(www\.)?youtube\.com/embed/[\w-]+'
    ]
    return any(re.match(pattern, url) for pattern in patterns)

def sanitize_input(text):
    """Sanitize user input"""
    if not text:
        return ""
    # Remove potentially dangerous characters
    return re.sub(r'[<>"\'&;]', '', text.strip())

def get_video_folder(video_id):
    """Get the dedicated folder for a specific video"""
    video_folder = os.path.join(BASE_DOWNLOAD_FOLDER, f"video_{video_id}")
    os.makedirs(video_folder, exist_ok=True)
    return video_folder

# ----- YouTube Metadata Functions -----
def get_video_title_from_youtube(link):
    """Extract actual video title from YouTube"""
    try:
        cmd = ['yt-dlp', '--get-title', '--no-warnings', link]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            title = result.stdout.strip()
            # Remove invalid filename characters
            title = re.sub(r'[\\/*?:"<>|]', "", title)
            return title[:100]  # Limit length
    except Exception as e:
        print(f"Could not get title from YouTube: {e}")
    return None

def get_video_description_from_youtube(link):
    """Extract video description from YouTube"""
    try:
        cmd = ['yt-dlp', '--get-description', '--no-warnings', link]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            description = result.stdout.strip()
            if description and len(description) > 10:  # Only return if we got meaningful content
                return description[:500]  # Limit length
    except Exception as e:
        print(f"Could not get description from YouTube: {e}")
    return "Video description will be updated shortly..."

# ----- Database Helper Functions -----
def get_user_by_username(username):
    """Get user by username"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            return user
        except Error as e:
            print(f"Error getting user: {e}")
            return None
        finally:
            cursor.close()
            connection.close()
    return None

def add_video(youtube_link, youtube_id, title, description, thumbnail_url, added_by, user_type):
    """Add video to database"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO videos (youtube_link, youtube_id, title, description, thumbnail_url, added_by, user_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (youtube_link, youtube_id, title, description, thumbnail_url, added_by, user_type))
            video_id = cursor.lastrowid
            connection.commit()
            
            # Create dedicated folder for this video
            video_folder = get_video_folder(video_id)
            print(f"Created dedicated folder: {video_folder}")
            
            return video_id
        except Error as e:
            print(f"Error adding video: {e}")
            return None
        finally:
            cursor.close()
            connection.close()
    return None

def get_videos_by_user(user_id=None, user_type=None):
    """Get videos based on user criteria"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            
            if user_type == 'admin':
                cursor.execute("""
                    SELECT v.*, u.username 
                    FROM videos v 
                    JOIN users u ON v.added_by = u.id 
                    WHERE v.user_type = 'admin'
                    ORDER BY v.created_at DESC
                """)
            elif user_id:
                cursor.execute("""
                    SELECT v.*, u.username 
                    FROM videos v 
                    JOIN users u ON v.added_by = u.id 
                    WHERE v.added_by = %s 
                    ORDER BY v.created_at DESC
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT v.*, u.username 
                    FROM videos v 
                    JOIN users u ON v.added_by = u.id 
                    ORDER BY v.created_at DESC
                """)
            
            videos = cursor.fetchall()
            return videos
        except Error as e:
            print(f"Error getting videos: {e}")
            return []
        finally:
            cursor.close()
            connection.close()
    return []

def get_video_by_id(video_id):
    """Get video by ID"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT v.*, u.username 
                FROM videos v 
                JOIN users u ON v.added_by = u.id 
                WHERE v.id = %s
            """, (video_id,))
            video = cursor.fetchone()
            return video
        except Error as e:
            print(f"Error getting video: {e}")
            return None
        finally:
            cursor.close()
            connection.close()
    return None

def update_video_download_status(video_id, status, video_path=None, audio_path=None, transcript_path=None):
    """Update video download status and paths"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            
            # Fix path separators for web compatibility
            if video_path:
                video_path = video_path.replace('\\', '/')
            if audio_path:
                audio_path = audio_path.replace('\\', '/')
            if transcript_path:
                transcript_path = transcript_path.replace('\\', '/')
            
            if video_path and audio_path and transcript_path:
                cursor.execute("""
                    UPDATE videos 
                    SET download_status = %s, video_path = %s, audio_path = %s, transcript_path = %s
                    WHERE id = %s
                """, (status, video_path, audio_path, transcript_path, video_id))
            elif video_path and audio_path:
                cursor.execute("""
                    UPDATE videos 
                    SET download_status = %s, video_path = %s, audio_path = %s
                    WHERE id = %s
                """, (status, video_path, audio_path, video_id))
            elif video_path:
                cursor.execute("""
                    UPDATE videos SET download_status = %s, video_path = %s WHERE id = %s
                """, (status, video_path, video_id))
            else:
                cursor.execute("""
                    UPDATE videos SET download_status = %s WHERE id = %s
                """, (status, video_id))
                    
            connection.commit()
            return True
        except Error as e:
            print(f"Error updating video status: {e}")
            return False
        finally:
            cursor.close()
            connection.close()
    return False

def update_video_title(video_id, title):
    """Update video title with proper title"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("UPDATE videos SET title = %s WHERE id = %s", (title, video_id))
            connection.commit()
            return True
        except Error as e:
            print(f"Error updating title: {e}")
            return False
        finally:
            cursor.close()
            connection.close()
    return False

def update_video_description(video_id, description):
    """Update video description in database"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("UPDATE videos SET description = %s WHERE id = %s", (description, video_id))
            connection.commit()
            print(f"Description updated for video {video_id}")
            return True
        except Error as e:
            print(f"Error updating description: {e}")
            return False
        finally:
            cursor.close()
            connection.close()
    return False

# ----- Background Download Function -----
def download_video_background(video_id, youtube_link):
    """Download video in background thread with concurrency control - NO UNNECESSARY REPAIR"""
    with DOWNLOAD_SEMAPHORE:
        try:
            print(f"Starting background download for video {video_id}")
            print(f"URL: {youtube_link}")
            
            # Get the dedicated folder for this video
            video_folder = get_video_folder(video_id)
            print(f"Using dedicated folder: {video_folder}")
            
            # Update status to downloading
            update_video_download_status(video_id, 'downloading')
            
            # STEP 1: Get metadata BEFORE download
            print("Fetching video metadata...")
            actual_title = get_video_title_from_youtube(youtube_link)
            actual_description = get_video_description_from_youtube(youtube_link)
            
            # Update title and description in database
            if actual_title:
                update_video_title(video_id, actual_title)
                print(f"Updated title: {actual_title}")
            else:
                print("Could not fetch title")
            
            if actual_description and actual_description != "Video description will be updated shortly...":
                update_video_description(video_id, actual_description)
                print(f"Updated description: {actual_description[:100]}...")
            else:
                print("Could not fetch description")
            
            # STEP 2: Download video to dedicated folder - SINGLE ATTEMPT
            print("Starting video download (single attempt)...")
            success, result = download_youtube_video(youtube_link, video_folder)
            
            if success:
                print(f"Video download successful: {result}")
                
                # Validate the downloaded video
                print("Validating video file...")
                is_valid, validation_message = validate_video_file(result)
                
                if not is_valid:
                    print(f" Video validation failed: {validation_message}")
                    
                    # CHECK IF REPAIR IS WORTH ATTEMPTING
                    file_size = os.path.getsize(result)
                    if file_size < 1024000:  # Less than 1MB - definitely corrupted
                        print("File too small, skipping repair")
                        update_video_download_status(video_id, 'failed')
                        return
                    
                    # Check if it's a "no video streams" error specifically
                    if "No video streams" in validation_message:
                        print("No video streams detected - file may be corrupted, skipping repair")
                        update_video_download_status(video_id, 'failed')
                        return
                    
                    print("Attempting to repair video...")
                    repaired, repaired_path = repair_video_file(result, video_folder)
                    if repaired:
                        print("Video repaired successfully")
                        result = repaired_path
                        
                        # Validate the repaired file
                        is_valid_after_repair, repair_message = validate_video_file(result)
                        if not is_valid_after_repair:
                            print(f"Repair failed: {repair_message}")
                            update_video_download_status(video_id, 'failed')
                            return
                    else:
                        print("Video repair failed")
                        update_video_download_status(video_id, 'failed')
                        return
                
                # Only proceed with audio extraction if video is valid
                print("Starting audio extraction...")
                audio_path = extract_audio_from_video(result, video_folder)
                
                if audio_path:
                    print(f"Audio extraction successful: {audio_path}")
                    # STEP 4: Transcribe audio (only if audio exists)
                    print("Starting transcription...")
                    transcript_path = transcribe_audio(audio_path, video_folder)
                else:
                    print("Audio extraction FAILED - no audio track found in video")
                    transcript_path = None
                
                # Update final status
                update_video_download_status(
                    video_id, 
                    'completed', 
                    result, 
                    audio_path, 
                    transcript_path
                )
                print(f"Video {video_id} processing completed!")
                
            else:
                print(f"Download failed for video {video_id}: {result}")
                # Mark as failed and STOP - NO RETRY
                update_video_download_status(video_id, 'failed')
                # Clean up any partial files
                try:
                    video_folder = get_video_folder(video_id)
                    if os.path.exists(video_folder):
                        # Remove only partial download files, keep folder structure
                        for file in os.listdir(video_folder):
                            file_path = os.path.join(video_folder, file)
                            if os.path.isfile(file_path):
                                os.remove(file_path)
                        print(f"Cleaned up partial files in {video_folder}")
                except Exception as e:
                    print(f"Could not clean up partial files: {e}")
                
        except Exception as e:
            print(f"Background download error for video {video_id}: {e}")
            # Mark as failed and STOP - NO RETRY
            update_video_download_status(video_id, 'failed')

# ----- Debug Routes -----
@app.route('/debug_video/<int:video_id>')
def debug_video(video_id):
    """Debug route to check video file status"""
    if 'user' not in session:
        return redirect('/login')
    
    video = get_video_by_id(video_id)
    if not video:
        return "Video not found"
    
    debug_info = {
        'video_id': video_id,
        'video_path': video['video_path'],
        'file_exists': False,
        'file_size': 0,
        'download_status': video['download_status'],
        'video_folder': get_video_folder(video_id)
    }
    
    if video['video_path']:
        debug_info['file_exists'] = os.path.exists(video['video_path'])
        if debug_info['file_exists']:
            debug_info['file_size'] = os.path.getsize(video['video_path'])
            
            # Run ffprobe to get detailed info
            try:
                cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', video['video_path']]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    debug_info['ffprobe'] = json.loads(result.stdout)
            except Exception as e:
                debug_info['ffprobe_error'] = str(e)
            
            # Validate the file
            is_valid, message = validate_video_file(video['video_path'])
            debug_info['validation'] = {
                'is_valid': is_valid,
                'message': message
            }
    
    # Check folder contents
    try:
        video_folder = get_video_folder(video_id)
        debug_info['folder_contents'] = os.listdir(video_folder)
    except Exception as e:
        debug_info['folder_error'] = str(e)
    
    return render_template('debug_video.html', debug_info=debug_info, video=video)
            
# ----- Routes -----
@app.route('/')
def home():
    return redirect('/login')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = sanitize_input(request.form.get('username', ''))
        password = request.form.get('password', '')
        
        if not username or not password:
            flash("Username and password are required", "error")
            return redirect('/signup')
        
        if len(username) < 3 or len(password) < 6:
            flash("Username must be at least 3 characters and password at least 6 characters", "error")
            return redirect('/signup')
        
        existing_user = get_user_by_username(username)
        if existing_user:
            flash("User already exists!", "error")
            return redirect('/signup')
        
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()
                cursor.execute(
                    "INSERT INTO users (username, password, role) VALUES (%s, %s, 'user')",
                    (username, password)
                )
                connection.commit()
                flash("Account created successfully! Please log in.", "success")
                return redirect('/login')
            except Error as e:
                flash(f"Error creating user: {e}", "error")
            finally:
                cursor.close()
                connection.close()
        else:
            flash("Database connection error", "error")
    
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = sanitize_input(request.form.get('username', ''))
        password = request.form.get('password', '')
        
        if not username or not password:
            flash("Username and password are required", "error")
            return redirect('/login')
        
        user = get_user_by_username(username)
        if user and user['password'] == password:
            session['user'] = user['username']
            session['user_id'] = user['id']
            session['user_role'] = user['role']
            flash(f"Welcome back, {user['username']}!", "success")
            return redirect('/dashboard')
        else:
            flash("Invalid credentials", "error")
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/login')
    
    admin_videos = get_videos_by_user(user_type='admin')
    user_videos = get_videos_by_user(user_id=session['user_id'])
    
    # Check for recently failed downloads and show flash messages
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, title, download_status 
                FROM videos 
                WHERE added_by = %s AND download_status = 'failed'
                ORDER BY created_at DESC 
                LIMIT 5
            """, (session['user_id'],))
            failed_videos = cursor.fetchall()
            
            for video in failed_videos:
                flash(f"Download failed for: {video['title']}", "error")
                
        except Error as e:
            print(f"Error checking failed videos: {e}")
        finally:
            cursor.close()
            connection.close()
    
    return render_template('dashboard.html', 
                         admin_videos=admin_videos, 
                         user_videos=user_videos,
                         user_role=session['user_role'])

@app.route('/add_video', methods=['POST'])
def add_video_route():
    if 'user' not in session:
        return redirect('/login')
    
    youtube_link = request.form.get('youtube_link', '').strip()
    
    if not youtube_link:
        flash("YouTube link is required", "error")
        return redirect('/dashboard')
    
    # Validate YouTube URL
    if not is_valid_youtube_url(youtube_link):
        flash("Invalid YouTube URL format", "error")
        return redirect('/dashboard')
    
    # Extract video ID from YouTube link
    if 'v=' in youtube_link:
        video_id = youtube_link.split('v=')[-1].split('&')[0]
    elif 'youtu.be/' in youtube_link:
        video_id = youtube_link.split('youtu.be/')[-1].split('?')[0]
    else:
        flash("Invalid YouTube link", "error")
        return redirect('/dashboard')
    
    # Get initial metadata
    initial_title = get_video_title_from_youtube(youtube_link) or f"Video {video_id}"
    initial_description = get_video_description_from_youtube(youtube_link)
    
    thumbnail_url = f"https://img.youtube.com/vi/{video_id}/0.jpg"
    
    # Add video to database
    db_video_id = add_video(
        youtube_link=youtube_link,
        youtube_id=video_id,
        title=initial_title,
        description=initial_description,
        thumbnail_url=thumbnail_url,
        added_by=session['user_id'],
        user_type=session['user_role']
    )
    
    if db_video_id:
        # Start background download
        thread = threading.Thread(
            target=download_video_background,
            args=(db_video_id, youtube_link)
        )
        thread.daemon = True
        thread.start()
        
        flash("Video added successfully! Download started in background.", "success")
    else:
        flash("Error adding video to database", "error")
    
    return redirect('/dashboard')

@app.route('/download_video/<int:video_id>')
def download_video(video_id):
    if 'user' not in session:
        return redirect('/login')
    
    video = get_video_by_id(video_id)
    if not video:
        flash("Video not found", "error")
        return redirect('/dashboard')
    
    if video['video_path'] and os.path.exists(video['video_path']):
        # Validate the file before serving
        is_valid, message = validate_video_file(video['video_path'])
        
        if not is_valid:
            flash(f"Video file has issues: {message}. Attempting repair...", "warning")
            # Try to repair
            repaired, repaired_path = repair_video_file(video['video_path'], get_video_folder(video_id))
            if not repaired:
                flash("Video file could not be repaired", "error")
                return redirect(f'/video/{video_id}')
            # Update the path if repaired
            video_path = repaired_path.replace('\\', '/')
        else:
            video_path = video['video_path'].replace('\\', '/')
        
        filename = os.path.basename(video_path)
        
        # For video playback, don't force download, allow streaming
        if request.args.get('download') == 'true':
            # Force download
            return send_file(
                video_path, 
                as_attachment=True,
                download_name=filename,
                mimetype='video/mp4'
            )
        else:
            # Stream for video player with proper headers
            response = send_file(
                video_path,
                mimetype='video/mp4',
                as_attachment=False  # This allows the browser to play it
            )
            # Enable range requests for video streaming
            response.headers['Accept-Ranges'] = 'bytes'
            return response
    else:
        flash("Video file not available yet. Please wait for processing to complete.", "error")
        return redirect(f'/video/{video_id}')

@app.route('/video/<int:video_id>')
def video_detail(video_id):
    if 'user' not in session:
        return redirect('/login')
    
    video = get_video_by_id(video_id)
    if not video:
        flash("Video not found", "error")
        return redirect('/dashboard')
    
    # Check if video file exists and is valid
    if video['video_path'] and os.path.exists(video['video_path']):
        is_valid, message = validate_video_file(video['video_path'])
        if not is_valid:
            flash(f"Video file may have issues: {message}", "warning")
    
    return render_template('video_detail.html', video=video)

@app.route('/extract_audio/<int:video_id>')
def extract_audio_route(video_id):
    if 'user' not in session:
        return redirect('/login')
    
    video = get_video_by_id(video_id)
    if not video:
        flash("Video not found", "error")
        return redirect('/dashboard')
    
    if video['audio_path'] and os.path.exists(video['audio_path']):
        # Fix path separators for web
        audio_path = video['audio_path'].replace('\\', '/')
        return send_file(audio_path, as_attachment=True)
    else:
        flash("Audio file not available yet. Please wait for processing to complete.", "error")
        return redirect(f'/video/{video_id}')

@app.route('/extract_text/<int:video_id>')
def extract_text(video_id):
    if 'user' not in session:
        return redirect('/login')
    
    video = get_video_by_id(video_id)
    if not video:
        flash("Video not found", "error")
        return redirect('/dashboard')
    
    if video['transcript_path'] and os.path.exists(video['transcript_path']):
        return send_file(video['transcript_path'], as_attachment=True)
    else:
        flash("Transcript not available yet. Please wait for processing to complete.", "error")
        return redirect(f'/video/{video_id}')

@app.route('/view_text/<int:video_id>')
def view_text(video_id):
    if 'user' not in session:
        return redirect('/login')
    
    video = get_video_by_id(video_id)
    if not video:
        flash("Video not found", "error")
        return redirect('/dashboard')
    
    if video['transcript_path'] and os.path.exists(video['transcript_path']):
        with open(video['transcript_path'], 'r', encoding='utf-8') as f:
            transcript_content = f.read()
        return render_template('view_transcript.html', video=video, transcript=transcript_content)
    else:
        flash("Transcript not available yet. Please wait for processing to complete.", "error")
        return redirect(f'/video/{video_id}')

@app.route('/delete_video/<int:video_id>')
def delete_video(video_id):
    """Delete video and its dedicated folder"""
    if 'user' not in session:
        return redirect('/login')
    
    video = get_video_by_id(video_id)
    if not video:
        flash("Video not found", "error")
        return redirect('/dashboard')
    
    # Check if user owns the video or is admin
    if video['added_by'] != session['user_id'] and session['user_role'] != 'admin':
        flash("You don't have permission to delete this video", "error")
        return redirect('/dashboard')
    
    try:
        # Delete the dedicated folder
        video_folder = get_video_folder(video_id)
        if os.path.exists(video_folder):
            shutil.rmtree(video_folder)
            print(f"Deleted folder: {video_folder}")
        
        # Delete from database
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM videos WHERE id = %s", (video_id,))
            connection.commit()
            cursor.close()
            connection.close()
        
        flash("Video deleted successfully", "success")
    except Exception as e:
        flash(f"Error deleting video: {e}", "error")
    
    return redirect('/dashboard')

@app.route('/video/<int:video_id>/questions')
def get_video_questions_route(video_id):
    """Get all questions for a video - ENHANCED for polling"""
    if 'user' not in session:
        return jsonify({'error': 'Please login'}), 401
    
    try:
        # Add a small delay to ensure database consistency
        time.sleep(0.1)
        questions = get_video_questions(video_id)
        return jsonify(questions)
    except Exception as e:
        print(f"Error getting questions: {e}")
        return jsonify({'error': 'Failed to fetch questions'}), 500

import threading
import time

def generate_answer_background(question_id, video_id, question, video_title, video_description):
    """Background task to generate AI answer from transcript"""
    try:
        print(f"Starting background answer generation for question {question_id}")
        print(f" Question: {question}")
        print(f" Video ID: {video_id}")
        
        video = get_video_by_id(video_id)
        if not video:
            print(f"Video {video_id} not found")
            update_answer(question_id, "Error: Video not found")
            return
        
        # Check transcript availability
        transcript_path = video.get('transcript_path')
        if not transcript_path or not os.path.exists(transcript_path):
            print(f"Transcript not available for video {video_id}")
            update_answer(question_id, "Sorry, the transcript for this video is not available yet.")
            return

        # Read transcript
        with open(transcript_path, 'r', encoding='utf-8') as f:
            transcript = f.read()

        if len(transcript.strip()) < 50:
            update_answer(question_id, "Transcript too short or not available.")
            return

        print("Checking question relevance...")

        # -------------------------------
        # 🔍 Simple relevance check
        # -------------------------------
        transcript_lower = transcript.lower()
        question_lower = question.lower()
        title_lower = (video_title or "").lower()
        desc_lower = (video_description or "").lower()

        # Basic keyword overlap heuristic
        words_in_question = set(re.findall(r'\w+', question_lower))
        matched_keywords = [w for w in words_in_question if w in transcript_lower or w in title_lower or w in desc_lower]
        relevance_score = len(matched_keywords) / (len(words_in_question) + 1)

        print(f" Matched keywords: {matched_keywords} | Relevance score: {relevance_score:.2f}")

        if relevance_score < 0.15:  # Less than 15% overlap
            update_answer(question_id, "The content related to your question was not found in this video.")
            print("Question not relevant to video content.")
            return

        # -------------------------------
        # 🤖 Generate contextual answer
        # -------------------------------
        answer = qa_processor.generate_answer(
            video_id=video_id,
            question=question,
            transcript=transcript,
            video_title=video_title,
            video_description=video_description
        )

        # -------------------------------
        # 🧠 Validate AI answer content
        # -------------------------------
        if not answer or len(answer.strip()) < 10:
            print("Empty or meaningless answer detected.")
            answer = "The content related to your question was not found in this video."

        if re.search(r"i (don't|cannot|can’t) find", answer.lower()):
            answer = "The content related to your question was not found in this video."

        update_answer(question_id, answer)
        print(f"Final answer saved for question {question_id}")

    except Exception as e:
        print(f"Error generating answer for question {question_id}: {e}")
        update_answer(question_id, f"Error while generating answer: {str(e)}")

@app.route('/video/<int:video_id>/ask', methods=['POST'])
def ask_question(video_id):
    """Ask a question about a video - ASYNCHRONOUS VERSION"""
    if 'user' not in session:
        return jsonify({'error': 'Please login to ask questions'}), 401
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data received'}), 400
            
        question = data.get('question', '').strip()
        
        if not question:
            return jsonify({'error': 'Question is required'}), 400
        
        if len(question) < 5:
            return jsonify({'error': 'Question must be at least 5 characters'}), 400
        
        if len(question) > 500:
            return jsonify({'error': 'Question must be less than 500 characters'}), 400
        
        # Get video details
        video = get_video_by_id(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        # Add question to database immediately with NULL answer
        question_id = add_question(video_id, session['user_id'], question)
        if not question_id:
            return jsonify({'error': 'Failed to save question'}), 500
        
        print(f"Question saved to database with ID: {question_id}")
        
        # Start background task to generate answer
        thread = threading.Thread(
            target=generate_answer_background,
            args=(question_id, video_id, question, video['title'], video['description'])
        )
        thread.daemon = True
        thread.start()
        
        print(f"Started background answer generation for question {question_id}")
        
        return jsonify({
            'success': True,
            'question_id': question_id,
            'answer': None  # No answer yet - will be generated in background
        })
        
    except Exception as e:
        print(f"Error processing question: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/question/<int:question_id>/feedback', methods=['POST'])
def submit_feedback(question_id):
    """Submit feedback for an answer"""
    if 'user' not in session:
        return jsonify({'error': 'Please login to submit feedback'}), 401
    
    try:
        data = request.get_json()
        is_helpful = data.get('is_helpful')
        feedback_text = data.get('feedback_text', '').strip()
        
        if is_helpful is None:
            return jsonify({'error': 'Helpful status is required'}), 400
        
        success = add_feedback(question_id, session['user_id'], is_helpful, feedback_text)
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to save feedback'}), 500
            
    except Exception as e:
        print(f"Error saving feedback: {e}")
        return jsonify({'error': 'Internal server error'}), 500

from ddgs import DDGS
import re
import textwrap

@app.route('/question/<int:question_id>/regenerate', methods=['POST'])
def regenerate_answer(question_id):
    """
    Generate a new web-searched answer that is specific to the video's topic.
    Combines video metadata with web sources for contextual relevance.
    """
    if 'user' not in session:
        return jsonify({'error': 'Please login'}), 401

    try:
        data = request.get_json()
        question_text = data.get('question', '').strip()
        video_id = data.get('video_id')

        if not question_text:
            return jsonify({'error': 'Question text is required'}), 400

        # ---- Fetch video details ----
        video = get_video_by_id(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404

        video_title = video.get('title', 'Untitled Video')
        video_desc = video.get('description', '')
        transcript_path = video.get('transcript_path')

        print(f"Regenerating answer from web for: '{question_text}' | Video: '{video_title}'")

        # ---- Prepare video context ----
        transcript_excerpt = ""
        if transcript_path and os.path.exists(transcript_path):
            with open(transcript_path, 'r', encoding='utf-8') as f:
                transcript_excerpt = f.read(1000)  # only first 1000 chars
        else:
            print("Transcript not found; using title + description for context.")

        # ---- Build intelligent search query ----
        search_query = (
            f"{video_title} {question_text} {video_desc[:150]} "
            f"{transcript_excerpt[:150]} site:simplilearn.com OR site:geeksforgeeks.org "
            f"OR site:tutorialspoint.com OR site:medium.com OR site:stackoverflow.com OR site:w3schools.com"
        )

        print(f"Search Query: {search_query[:250]}...")

        # ---- Perform web search ----
        ddgs = DDGS()
        results = ddgs.text(search_query, max_results=10)

        snippets = []
        for res in results:
            snippet = res.get('body', '')
            title = res.get('title', '')
            url = res.get('href', '')
            if not snippet or len(snippet) < 40:
                continue
            if re.search(r'[\u4e00-\u9fff]', snippet):  # skip Chinese/junk
                continue
            snippets.append(f"{title}. {snippet} (Source: {url})")

        # ---- Generate final answer ----
        if not snippets:
            new_answer = (
                f" I couldn’t find specific online information directly linked to the video "
                f"**'{video_title}'**. Try rephrasing your question or checking similar tutorials."
            )
        else:
            combined = " ".join(snippets[:6])
            sentences = re.split(r'(?<=[.!?]) +', combined)
            summary = " ".join(sentences[:8]).strip()

            new_answer = textwrap.dedent(f"""
            **Based on the video '{video_title}' and trusted web sources:**

            {summary}

            _This web-sourced answer was generated using trusted educational sites related to the video's topic._
            """)

        # ---- Save to database ----
        update_answer(question_id, new_answer)
        print(f"Web-based answer generated and saved for question {question_id}")

        return jsonify({'success': True, 'new_answer': new_answer})

    except Exception as e:
        print(f"Error during web regeneration: {e}")
        return jsonify({'error': 'Failed to generate web-based answer'}), 5000



@app.route('/debug_video_titles')
def debug_video_titles():
    """Debug route to check video titles in database"""
    if 'user' not in session:
        return redirect('/login')
    
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, youtube_id, title, youtube_link 
                FROM videos 
                WHERE added_by = %s 
                ORDER BY created_at DESC
            """, (session['user_id'],))
            videos = cursor.fetchall()
            
            debug_info = []
            for video in videos:
                debug_info.append({
                    'id': video['id'],
                    'youtube_id': video['youtube_id'],
                    'title': video['title'],
                    'youtube_link': video['youtube_link'],
                    'title_length': len(video['title']) if video['title'] else 0
                })
            
            return render_template('debug_titles.html', videos=debug_info)
            
        except Error as e:
            return f"Error: {e}"
        finally:
            cursor.close()
            connection.close()
    return "Database connection failed"

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out successfully", "success")
    return redirect('/login')

if __name__ == '__main__':
    app.run(debug=True,use_reloader=False)