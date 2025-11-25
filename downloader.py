import yt_dlp
import os
import re
from datetime import datetime
import speech_recognition as sr
from pydub import AudioSegment
import subprocess
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
        logging.error(f"⚠️ Could not get title from YouTube: {e}")
    return None

def download_youtube_video(link, output_folder):
    """Download YouTube video to dedicated folder - SMARTER REPAIR LOGIC"""
    os.makedirs(output_folder, exist_ok=True)
    
    try:
        timestamp = int(time.time())
        
        # Use more compatible format selection for web playback
        cmd = [
            'yt-dlp',
            '-f', 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best[ext=mp4]/best',
            '--merge-output-format', 'mp4',  # Force MP4 container
            '--no-write-thumbnail',
            '--no-write-info-json',
            '--no-write-subs',
            '--no-write-auto-subs',
            '--no-post-overwrites',
            '--no-overwrites',
            '--no-playlist',
            '--socket-timeout', '30',
            '--retries', '3',
            '-o', os.path.join(output_folder, f'video_{timestamp}.%(ext)s'),
            link
        ]
        
        logging.info(f"📥 Downloading to dedicated folder: {output_folder}")
        
        # Single attempt with timeout
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode != 0:
            logging.error(f"❌ yt-dlp failed: {result.stderr}")
            return False, f"Download failed: {result.stderr}"
        
        # Look for the downloaded video file
        video_file = None
        for file in os.listdir(output_folder):
            file_path = os.path.join(output_folder, file)
            if file.endswith(('.mp4', '.webm', '.mkv')):
                file_size = os.path.getsize(file_path)
                if file_size > 1024000:  # Increased to 1MB minimum
                    video_file = file_path
                    logging.info(f"✅ Video downloaded: {file_path} ({file_size} bytes)")
                    break
        
        if video_file:
            # Validate the video file
            is_valid, message = validate_video_file(video_file)
            if not is_valid:
                logging.warning(f"❌ Video validation failed: {message}")
                
                # DON'T attempt repair for "no video streams" errors
                if "No video streams" in message:
                    logging.error("❌ Skipping repair - no video streams detected")
                    return False, f"Downloaded file has no video streams: {message}"
                
                # Only attempt repair for other types of validation failures
                logging.info("🔄 Attempting video repair...")
                repaired, repaired_path = repair_video_file(video_file, output_folder)
                if repaired:
                    logging.info("✅ Video repaired successfully")
                    return True, repaired_path
                else:
                    return False, f"Video file invalid and repair failed: {message}"
            
            return True, video_file
        
        logging.warning("No valid video file found in dedicated folder")
        return False, "No valid video file found after download"
            
    except subprocess.TimeoutExpired:
        logging.error("❌ Download timed out after 10 minutes")
        return False, "Download timed out"
    except Exception as e:
        logging.error(f"❌ Download failed: {e}")
        return False, str(e)

def download_with_ytdlp_direct(link, output_folder):
    """Fallback download method with simpler format"""
    try:
        timestamp = int(time.time())
        
        cmd = [
            'yt-dlp',
            '-f', 'best[ext=mp4]/best',
            '--merge-output-format', 'mp4',
            '--no-write-thumbnail',
            '--no-write-info-json',
            '--no-write-subs',
            '--no-post-overwrites',
            '--ignore-errors',
            '-o', os.path.join(output_folder, f'video_{timestamp}.%(ext)s'),
            link
        ]
        
        logging.info("📥 Direct yt-dlp download to dedicated folder...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        # Find any MP4 file in the dedicated folder
        for file in os.listdir(output_folder):
            file_path = os.path.join(output_folder, file)
            if file.endswith('.mp4'):
                file_size = os.path.getsize(file_path)
                if file_size > 1024000:  # At least 1MB
                    logging.info(f"✅ Fallback download successful: {file_path}")
                    return True, file_path
        
        return False, "No valid MP4 file found in dedicated folder"
            
    except Exception as e:
        return False, str(e)

def validate_video_file(video_path):
    """Validate that the downloaded video file is playable with better diagnostics"""
    try:
        logging.info(f"🔍 Validating video file: {os.path.basename(video_path)}")
        
        # Check file exists and has reasonable size
        if not os.path.exists(video_path):
            logging.error("❌ Video file does not exist")
            return False, "File not found"
        
        file_size = os.path.getsize(video_path)
        if file_size < 1024000:  # Less than 1MB
            logging.error(f"❌ Video file too small: {file_size} bytes")
            return False, f"File too small: {file_size} bytes"
        
        logging.info(f"📊 File size OK: {file_size} bytes")
        
        # First, try a basic file type check
        try:
            import magic
            file_type = magic.from_file(video_path, mime=True)
            logging.info(f"📄 File type detected: {file_type}")
            
            # If it's not a video file, don't bother with ffprobe
            if not file_type.startswith('video/') and not file_type.startswith('application/octet-stream'):
                logging.error(f"❌ Not a video file: {file_type}")
                return False, f"Not a video file: {file_type}"
        except ImportError:
            logging.warning("⚠️ python-magic not installed, skipping file type detection")
        except Exception as e:
            logging.warning(f"⚠️ File type detection failed: {e}")
        
        # More comprehensive ffprobe check
        cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', 
               '-show_entries', 'stream=codec_name,width,height,pix_fmt,duration,bit_rate,codec_type', 
               '-show_entries', 'format=format_name,size,duration',
               '-of', 'json', video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            logging.error(f"❌ FFprobe validation failed: {result.stderr}")
            
            # Try a simpler probe to see what's actually in the file
            simple_cmd = ['ffprobe', '-v', 'quiet', '-show_streams', '-show_format', video_path]
            simple_result = subprocess.run(simple_cmd, capture_output=True, text=True, timeout=10)
            
            if simple_result.returncode == 0:
                # Analyze what streams are available
                if 'codec_type=video' not in simple_result.stdout:
                    logging.error("❌ CONFIRMED: No video streams in file")
                    return False, "No video streams detected - file may be corrupted or contain only audio"
                else:
                    logging.info("✅ Video streams found but detailed probe failed")
                    return True, "Video streams present but detailed validation failed"
            else:
                return False, f"FFprobe failed: {result.stderr}"
        
        import json
        probe_data = json.loads(result.stdout)
        
        # Check for video streams
        if not probe_data.get('streams'):
            logging.error("❌ No streams found in file")
            return False, "No streams found"
        
        # Check specifically for video streams
        video_streams = [s for s in probe_data['streams'] if s.get('codec_type') == 'video']
        if not video_streams:
            logging.error("❌ No video streams found")
            
            # Check what kind of streams ARE available
            stream_types = [s.get('codec_type', 'unknown') for s in probe_data['streams']]
            logging.info(f"📊 Available stream types: {stream_types}")
            
            return False, f"No video streams detected. Available streams: {stream_types}"
        
        video_info = video_streams[0]
        codec = video_info.get('codec_name', 'unknown')
        
        # Log video details
        logging.info(f"🎬 Video codec: {codec}")
        logging.info(f"📺 Resolution: {video_info.get('width', 'unknown')}x{video_info.get('height', 'unknown')}")
        logging.info(f"⏱️ Duration: {video_info.get('duration', 'unknown')}s")
        
        # Check if codec is web-compatible
        web_compatible_codecs = ['h264', 'mpeg4', 'vp8', 'vp9']
        if codec.lower() not in web_compatible_codecs:
            logging.warning(f"⚠️ Non-standard codec: {codec}. May not play in all browsers.")
        
        return True, f"Valid {codec} video, {file_size} bytes"
        
    except Exception as e:
        logging.error(f"❌ Video validation failed: {e}")
        return False, f"Validation error: {e}"

def repair_video_file(video_path, output_folder):
    """Try to repair and re-encode corrupted video file to standard format"""
    try:
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        repaired_path = os.path.join(output_folder, f"{base_name}_repaired.mp4")
        
        logging.info("🔧 Attempting to repair and re-encode video file...")
        
        # Re-encode to H.264/AAC in MP4 container (most compatible)
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-c:v', 'libx264',        # Standard video codec
            '-preset', 'medium',      # Balance between speed and quality
            '-crf', '23',             # Quality setting
            '-c:a', 'aac',           # Standard audio codec
            '-b:a', '128k',          # Audio bitrate
            '-movflags', '+faststart',  # Enable streaming (moov atom at front)
            '-y',                    # Overwrite output
            '-loglevel', 'error',    # Only show errors
            repaired_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)  # 10 minutes timeout
        
        if result.returncode == 0 and os.path.exists(repaired_path):
            repaired_size = os.path.getsize(repaired_path)
            if repaired_size > 1024000:  # At least 1MB
                logging.info(f"✅ Video repaired successfully: {repaired_size} bytes")
                # Replace original with repaired file
                try:
                    os.remove(video_path)
                    os.rename(repaired_path, video_path)
                    
                    # Validate the repaired file
                    is_valid, message = validate_video_file(video_path)
                    if is_valid:
                        logging.info("✅ Repaired video validation passed")
                        return True, video_path
                    else:
                        logging.warning(f"⚠️ Repaired video validation failed: {message}")
                        return False, video_path
                        
                except Exception as e:
                    logging.error(f"❌ Error replacing original file: {e}")
                    return True, repaired_path  # Return repaired path even if rename fails
            else:
                if os.path.exists(repaired_path):
                    os.remove(repaired_path)
        
        logging.warning("❌ Video repair failed")
        if os.path.exists(repaired_path):
            os.remove(repaired_path)
        return False, video_path
        
    except subprocess.TimeoutExpired:
        logging.error("❌ Video repair timed out")
        if os.path.exists(repaired_path):
            os.remove(repaired_path)
        return False, video_path
    except Exception as e:
        logging.error(f"❌ Video repair failed: {e}")
        if os.path.exists(repaired_path):
            os.remove(repaired_path)
        return False, video_path

def extract_audio_from_video(video_path, output_folder):
    """Extract audio from video file with comprehensive error handling and retries"""
    max_retries = 2
    retry_delay = 2  # seconds
    
    for attempt in range(max_retries + 1):
        try:
            if not os.path.exists(video_path):
                logging.error(f"❌ Video file not found: {video_path}")
                return None
            
            file_size = os.path.getsize(video_path)
            logging.info(f"📊 Video file: {os.path.basename(video_path)} ({file_size} bytes)")
            
            if file_size < 1024000:
                logging.error(f"❌ File too small: {file_size} bytes")
                return None
            
            logging.info(f"🎵 Starting audio extraction (attempt {attempt + 1})...")
            
            # Method 1: Try ffmpeg first (more reliable)
            logging.info("🔄 Method 1: Trying ffmpeg...")
            audio_path_ffmpeg = extract_audio_with_ffmpeg(video_path, output_folder)
            if audio_path_ffmpeg:
                return audio_path_ffmpeg
            
            # Method 2: Try pydub as fallback
            logging.info("🔄 Method 2: Trying pydub...")
            audio_path_pydub = extract_audio_with_pydub(video_path, output_folder)
            if audio_path_pydub:
                return audio_path_pydub
            
            if attempt < max_retries:
                logging.info(f"🔄 Attempt {attempt + 1} failed, retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logging.error("❌ All audio extraction methods failed after retries")
                return None
                
        except Exception as e:
            logging.error(f"❌ Audio extraction attempt {attempt + 1} failed: {e}")
            if attempt < max_retries:
                logging.info(f"🔄 Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logging.error("❌ All audio extraction attempts failed")
                return None
    
    return None

def extract_audio_with_ffmpeg(video_path, output_folder):
    """Extract audio using ffmpeg directly - most reliable method"""
    try:
        # Create audio filename based on video filename
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        audio_filename = f"{base_name}_audio.wav"
        audio_path_output = os.path.join(output_folder, audio_filename)
        
        # Remove existing audio file if it exists
        if os.path.exists(audio_path_output):
            os.remove(audio_path_output)
        
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vn',  # No video
            '-acodec', 'pcm_s16le',
            '-ac', '1',  # Mono
            '-ar', '16000',  # 16kHz
            '-y',  # Overwrite output file
            '-loglevel', 'error',  # Only show errors
            audio_path_output
        ]
        
        logging.info("🎧 Running ffmpeg...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # Increased timeout
        
        if result.returncode == 0:
            if os.path.exists(audio_path_output):
                audio_size = os.path.getsize(audio_path_output)
                if audio_size > 1024:  # At least 1KB
                    logging.info(f"✅ FFmpeg: Audio extracted successfully! ({audio_size} bytes)")
                    return audio_path_output
                else:
                    logging.error("❌ FFmpeg: Audio file too small, likely no audio track")
                    os.remove(audio_path_output)
                    return None
            else:
                logging.error("❌ FFmpeg: Audio file was not created")
                return None
        else:
            # Check if error is due to no audio stream
            error_output = result.stderr.lower()
            if 'no audio streams' in error_output or 'invalid data' in error_output:
                logging.error("❌ FFmpeg: No audio track found in video file")
                return None
            else:
                logging.error(f"❌ FFmpeg failed: {result.stderr}")
                return None
            
    except subprocess.TimeoutExpired:
        logging.error("❌ FFmpeg: Extraction timed out")
        return None
    except Exception as e:
        logging.error(f"❌ FFmpeg extraction failed: {e}")
        return None

def extract_audio_with_pydub(video_path, output_folder):
    """Extract audio using pydub as fallback"""
    try:
        logging.info("🔍 Loading video with pydub...")
        video = AudioSegment.from_file(video_path)
        
        if len(video) == 0:
            logging.error("❌ Pydub: No audio track detected")
            return None
        
        logging.info(f"✅ Pydub: Video loaded. Duration: {len(video)/1000}s")
        
        # Convert to mono 16kHz
        audio = video.set_channels(1).set_frame_rate(16000)
        
        # Create audio filename
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        audio_filename = f"{base_name}_audio.wav"
        audio_path_output = os.path.join(output_folder, audio_filename)
        
        # Remove existing file
        if os.path.exists(audio_path_output):
            os.remove(audio_path_output)
        
        # Export audio
        logging.info("💾 Exporting audio with pydub...")
        audio.export(audio_path_output, format="wav")
        
        if os.path.exists(audio_path_output):
            audio_size = os.path.getsize(audio_path_output)
            if audio_size > 1024:
                logging.info(f"✅ Pydub: Audio extracted successfully! ({audio_size} bytes)")
                return audio_path_output
            else:
                logging.error("❌ Pydub: Audio file too small")
                os.remove(audio_path_output)
                return None
        else:
            logging.error("❌ Pydub: Audio file was not created")
            return None
            
    except Exception as e:
        logging.error(f"❌ Pydub extraction failed: {e}")
        return None

def debug_audio_file(audio_path):
    """Debug audio file to see what's in it with more details"""
    try:
        if not os.path.exists(audio_path):
            logging.error(f"❌ Audio file doesn't exist: {audio_path}")
            return
        
        file_size = os.path.getsize(audio_path)
        logging.info(f"🔍 Audio file debug: {os.path.basename(audio_path)}")
        logging.info(f"📊 File size: {file_size} bytes")
        
        # Check if file has actual audio content
        audio = AudioSegment.from_file(audio_path)
        duration_ms = len(audio)
        duration_seconds = duration_ms / 1000
        
        logging.info(f"⏱️ Duration: {duration_ms} ms ({duration_seconds:.2f} seconds)")
        logging.info(f"📈 Channels: {audio.channels}")
        logging.info(f"🎚️ Sample rate: {audio.frame_rate} Hz")
        logging.info(f"🔊 Max volume: {audio.max} dB")
        logging.info(f"🔈 Average volume: {audio.dBFS} dB")
        
        # Check if audio is mostly silence
        silence_threshold = -40  # dB
        if audio.dBFS > silence_threshold:
            logging.info("✅ Audio contains non-silent content")
        else:
            logging.warning("🔇 Audio appears to be mostly silent")
            
        # Calculate audio characteristics
        if duration_seconds > 0:
            logging.info(f"📏 Audio characteristics:")
            logging.info(f"   - Frame count: {audio.frame_count()}")
            logging.info(f"   - Frame rate: {audio.frame_rate} Hz")
            logging.info(f"   - Sample width: {audio.sample_width} bytes")
            
        # Check for very short audio (might be corrupted)
        if duration_seconds < 1.0:
            logging.warning("⚠️ Audio is very short (<1 second), may be corrupted")
        elif duration_seconds < 5.0:
            logging.info("ℹ️ Audio is short, may contain limited speech")
            
    except Exception as e:
        logging.error(f"❌ Audio debug failed: {e}")

def transcribe_audio(audio_path, output_folder):
    """Transcribe audio to text with multiple methods"""
    try:
        if not os.path.exists(audio_path):
            logging.error(f"❌ Audio file not found: {audio_path}")
            return create_empty_transcript(audio_path, output_folder, "Audio file not found")
        
        logging.info(f"📝 Starting transcription for: {os.path.basename(audio_path)}")
        
        # DEBUG: Check the audio file first
        debug_audio_file(audio_path)
        
        # Try Whisper first if available (usually more accurate)
        whisper_result = transcribe_with_whisper(audio_path, output_folder)
        if whisper_result:
            return whisper_result
        
        # Fall back to Google Speech Recognition
        recognizer = sr.Recognizer()
        
        # Get audio duration to determine chunking strategy
        try:
            audio = AudioSegment.from_file(audio_path)
            duration_seconds = len(audio) / 1000
            logging.info(f"⏱️ Audio duration: {duration_seconds:.2f} seconds")
        except Exception as e:
            logging.warning(f"⚠️ Could not get audio duration: {e}")
            duration_seconds = 0
        
        # Use chunking for longer audio files
        if duration_seconds > 30:
            logging.info("🔊 Audio is long, using chunked transcription...")
            return transcribe_long_audio(audio_path, output_folder, recognizer, duration_seconds)
        else:
            logging.info("🔊 Audio is short, using single transcription...")
            return transcribe_short_audio(audio_path, output_folder, recognizer)
        
    except Exception as e:
        logging.error(f"❌ Transcription failed: {e}")
        return create_empty_transcript(audio_path, output_folder, f"Transcription error: {e}")

def transcribe_short_audio(audio_path, output_folder, recognizer):
    """Transcribe short audio files (under 30 seconds) in one go"""
    try:
        with sr.AudioFile(audio_path) as source:
            # Adjust for ambient noise
            logging.info("🔊 Adjusting for ambient noise...")
            recognizer.adjust_for_ambient_noise(source, duration=1.0)
            
            # Record the entire audio
            logging.info("👂 Listening to audio...")
            audio_data = recognizer.record(source)
            
            logging.info(f"🎧 Audio data length: {len(audio_data.get_raw_data())} bytes")
        
        # Try multiple recognition engines with better settings
        text = None
        
        # Method 1: Google Speech Recognition with better parameters
        try:
            logging.info("🔄 Trying Google Speech Recognition...")
            text = recognizer.recognize_google(
                audio_data, 
                language='en-US',  # Explicitly set language
                show_all=False
            )
            logging.info("✅ Google Speech Recognition successful")
        except sr.UnknownValueError:
            logging.warning("❌ Google couldn't understand audio")
        except sr.RequestError as e:
            logging.error(f"❌ Google API error: {e}")
        
        # Method 2: If Google fails, try with show_all for alternatives
        if not text:
            try:
                logging.info("🔄 Trying Google with alternatives...")
                result = recognizer.recognize_google(audio_data, show_all=True)
                if result and 'alternative' in result and len(result['alternative']) > 0:
                    text = result['alternative'][0]['transcript']
                    logging.info("✅ Google alternatives successful")
            except Exception as e:
                logging.warning(f"❌ Google alternatives failed: {e}")
        
        if text:
            return save_transcript(audio_path, output_folder, text, "short")
        else:
            logging.error("❌ All speech recognition attempts failed for short audio")
            return create_empty_transcript(audio_path, output_folder, "No speech content detected")
            
    except Exception as e:
        logging.error(f"❌ Short audio transcription failed: {e}")
        return create_empty_transcript(audio_path, output_folder, f"Short audio error: {e}")

def transcribe_long_audio(audio_path, output_folder, recognizer, duration_seconds):
    """Transcribe long audio files by splitting into chunks"""
    try:
        logging.info(f"✂️ Splitting {duration_seconds:.2f} second audio into chunks...")
        
        # Load the audio file
        audio = AudioSegment.from_file(audio_path)
        
        # Split into 15-second chunks with 1-second overlap
        chunk_length = 15000  # 15 seconds in milliseconds
        overlap = 1000       # 1 second overlap
        
        chunks = []
        start = 0
        
        while start < len(audio):
            end = start + chunk_length
            if end > len(audio):
                end = len(audio)
            
            chunk = audio[start:end]
            chunks.append(chunk)
            start += chunk_length - overlap
        
        logging.info(f"📦 Created {len(chunks)} chunks for processing")
        
        # Transcribe each chunk
        all_texts = []
        
        for i, chunk in enumerate(chunks):
            logging.info(f"🎯 Processing chunk {i+1}/{len(chunks)}...")
            
            # Export chunk to temporary file
            temp_chunk_path = os.path.join(output_folder, f"temp_chunk_{i}.wav")
            chunk.export(temp_chunk_path, format="wav")
            
            try:
                # Transcribe the chunk
                with sr.AudioFile(temp_chunk_path) as source:
                    recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    chunk_audio = recognizer.record(source)
                
                chunk_text = recognizer.recognize_google(chunk_audio, language='en-US')
                if chunk_text:
                    all_texts.append(chunk_text)
                    logging.info(f"✅ Chunk {i+1}: {chunk_text[:50]}...")
                else:
                    logging.warning(f"⚠️ Chunk {i+1}: No text detected")
                
            except sr.UnknownValueError:
                logging.warning(f"⚠️ Chunk {i+1}: Could not understand audio")
            except sr.RequestError as e:
                logging.error(f"❌ Chunk {i+1}: API error - {e}")
            except Exception as e:
                logging.error(f"❌ Chunk {i+1}: Error - {e}")
            finally:
                # Clean up temporary chunk file
                if os.path.exists(temp_chunk_path):
                    os.remove(temp_chunk_path)
        
        # Combine all chunks
        if all_texts:
            full_text = " ".join(all_texts)
            logging.info(f"✅ Successfully transcribed {len(all_texts)} chunks")
            return save_transcript(audio_path, output_folder, full_text, "chunked")
        else:
            logging.error("❌ No chunks were successfully transcribed")
            return create_empty_transcript(audio_path, output_folder, "No speech content detected in any chunks")
            
    except Exception as e:
        logging.error(f"❌ Long audio transcription failed: {e}")
        return create_empty_transcript(audio_path, output_folder, f"Long audio error: {e}")

def save_transcript(audio_path, output_folder, text, method):
    """Save the transcribed text to a file"""
    try:
        # Create transcript filename based on audio filename
        base_name = os.path.splitext(os.path.basename(audio_path))[0].replace('_audio', '')
        transcript_filename = f"{base_name}_transcript.txt"
        transcript_path = os.path.join(output_folder, transcript_filename)
        
        # Format transcript with metadata
        formatted_transcript = format_transcript(text, method)
        
        # Save transcript
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write(formatted_transcript)
        
        # Also save a clean version without metadata
        clean_transcript_path = os.path.join(output_folder, f"{base_name}_clean_transcript.txt")
        with open(clean_transcript_path, 'w', encoding='utf-8') as f:
            f.write(text)
        
        logging.info(f"✅ Transcript saved: {os.path.basename(transcript_path)}")
        logging.info(f"📝 Text length: {len(text)} characters, {len(text.split())} words")
        
        return transcript_path
        
    except Exception as e:
        logging.error(f"❌ Error saving transcript: {e}")
        return create_empty_transcript(audio_path, output_folder, f"Save error: {e}")

def format_transcript(text, method="standard"):
    """Format the transcript with detailed metadata"""
    words = text.split()
    word_count = len(words)
    char_count = len(text)
    
    # Calculate estimated speaking time (assuming 150 words per minute)
    estimated_minutes = word_count / 150
    
    formatted_text = f"""=== VIDEO TRANSCRIPT ===
Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Transcription Method: {method}
Word Count: {word_count}
Character Count: {char_count}
Estimated Speaking Time: {estimated_minutes:.1f} minutes
Average Word Length: {char_count/word_count:.1f} characters

--- TRANSCRIPT START ---
{text}
--- TRANSCRIPT END ---

STATISTICS:
- Total words: {word_count}
- Total characters: {char_count}
- Estimated duration: {estimated_minutes:.1f} minutes
- Transcription date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Note: This transcript was automatically generated and may contain errors.
Please verify important content manually.
"""
    return formatted_text

def create_empty_transcript(audio_path, output_folder, error_message):
    """Create a transcript file with error message in dedicated folder"""
    base_name = os.path.splitext(os.path.basename(audio_path))[0].replace('_audio', '')
    transcript_filename = f"{base_name}_transcript.txt"
    transcript_path = os.path.join(output_folder, transcript_filename)
    
    error_content = f"""=== VIDEO TRANSCRIPT ===
Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Status: FAILED

Error: {error_message}

Note: This could be due to:
- No speech content in the audio
- Poor audio quality
- Network connectivity issues
- Service temporarily unavailable
"""
    
    with open(transcript_path, 'w', encoding='utf-8') as f:
        f.write(error_content)
    
    logging.info(f"📄 Created error transcript in dedicated folder: {os.path.basename(transcript_path)}")
    return transcript_path

def transcribe_with_whisper(audio_path, output_folder):
    """Alternative transcription using OpenAI Whisper (if available)"""
    try:
        # Check if whisper is available
        try:
            import whisper
        except ImportError:
            logging.warning("⚠️ OpenAI Whisper not available, using Google Speech Recognition")
            return None
        
        logging.info("🔊 Using OpenAI Whisper for transcription...")
        
        # Load the model
        model = whisper.load_model("base")  # You can use "small", "medium", "large" for better accuracy
        
        # Transcribe the audio
        result = model.transcribe(audio_path)
        
        if result and 'text' in result:
            text = result['text'].strip()
            if text:
                logging.info(f"✅ Whisper transcription successful: {len(text)} characters")
                
                # Create transcript filename
                base_name = os.path.splitext(os.path.basename(audio_path))[0].replace('_audio', '')
                transcript_filename = f"{base_name}_whisper_transcript.txt"
                transcript_path = os.path.join(output_folder, transcript_filename)
                
                # Save transcript
                with open(transcript_path, 'w', encoding='utf-8') as f:
                    f.write(f"=== WHISPER TRANSCRIPT ===\n")
                    f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Model: base\n\n")
                    f.write(text)
                
                return transcript_path
        
        return None
        
    except Exception as e:
        logging.error(f"❌ Whisper transcription failed: {e}")
        return None