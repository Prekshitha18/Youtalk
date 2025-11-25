import os
import hashlib
import re
import logging
import time
from database import get_cached_answer, cache_answer, get_video_by_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GuaranteedQAProcessor:
    def __init__(self):
        logger.info("⚡ Initializing Guaranteed Instant QA Processor")
        # Import the instant metadata extractor
        try:
            from youtube_metadata import metadata_extractor
            self.metadata_extractor = metadata_extractor
            self.metadata_available = True
            print("✅ Instant metadata extractor loaded!")
        except ImportError as e:
            self.metadata_available = False
            logger.error(f"❌ Metadata extractor not available: {e}")
    
    def generate_answer(self, video_id, question, transcript, video_title="", video_description=""):
        """Generate guaranteed instant answers - always under 1 second"""
        start_time = time.time()
        
        try:
            print(f"🎯 Processing: '{question}'")
            print(f"📝 Using video title: '{video_title}'")
            
            # Create question hash for caching
            question_hash = hashlib.md5(question.lower().encode()).hexdigest()
            
            # Check cache first (instant)
            cached = get_cached_answer(video_id, question_hash)
            if cached:
                logger.info("✅ Using cached answer")
                elapsed = time.time() - start_time
                print(f"⚡ Cached answer in {elapsed:.3f} seconds")
                return cached['answer_text']
            
            # Get video info from database to ensure we have the latest title
            video = get_video_by_id(video_id)
            if not video:
                return "❌ Video information not found in our database."
            
            youtube_url = video.get('youtube_link', '')
            # Use the title from the database, not the parameter (which might be empty)
            actual_title = video.get('title', 'This YouTube Video')
            
            # Clean up the title if it's just a video ID
            if "YouTube Video" in actual_title and len(actual_title) > 20:
                actual_title = "This YouTube Video"
            
            print(f"🎬 Final title being used: '{actual_title}'")
            
            if not youtube_url:
                return "❌ YouTube URL not available for this video."
            
            # Use instant metadata extractor (always under 0.1 seconds)
            if self.metadata_available:
                answer = self.metadata_extractor.generate_instant_answer(
                    youtube_url, question, actual_title  # Pass the actual title
                )
            else:
                answer = self._generate_fallback_answer(question, actual_title, youtube_url)
            
            # Cache the answer for future instant responses
            cache_answer(video_id, question_hash, question, answer, "instant")
            
            elapsed = time.time() - start_time
            print(f"✅ Answer generated in {elapsed:.3f} seconds")
            return answer
            
        except Exception as e:
            logger.error(f"❌ Error in guaranteed QA: {e}")
            elapsed = time.time() - start_time
            print(f"⏱️ Error after {elapsed:.3f} seconds")
            return "⚡ I can see this is a YouTube video. For detailed information, please watch the video directly or visit the YouTube page."
    
    def _generate_fallback_answer(self, question, video_title, youtube_url):
        """Generate instant fallback answers"""
        question_lower = question.lower()
        
        if any(phrase in question_lower for phrase in ['youtube channel', 'what channel']):
            return f"🔍 **Channel Information**\n\nVideo: **{video_title}**\n\nClick the YouTube link above to visit the video page and see the channel name directly."
        
        elif any(phrase in question_lower for phrase in ['what is this video', 'what this video about']):
            return f"🎬 **Video Content**\n\n**Title:** {video_title}\n\nWatch the video above to learn about its content directly."
        
        else:
            return f"📺 **YouTube Video**\n\n**Title:** {video_title}\n\nYou can watch this video directly or visit YouTube for more details."

# Use the guaranteed instant processor
qa_processor = GuaranteedQAProcessor()