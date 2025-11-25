import re
import requests
import logging
from urllib.parse import urlparse, parse_qs
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InstantYouTubeMetadata:
    def __init__(self):
        pass  # No web scraping, instant answers only
    
    def extract_video_id(self, youtube_url):
        """Extract video ID from YouTube URL"""
        try:
            if 'youtu.be' in youtube_url:
                return youtube_url.split('/')[-1].split('?')[0]
            elif 'youtube.com' in youtube_url:
                if 'v=' in youtube_url:
                    return youtube_url.split('v=')[1].split('&')[0]
                elif 'embed/' in youtube_url:
                    return youtube_url.split('embed/')[1].split('/')[0]
        except Exception as e:
            logger.error(f"Error extracting video ID: {e}")
        return None
    
    def generate_instant_answer(self, youtube_url, question, existing_title=""):
        """Generate instant answers without any web scraping"""
        try:
            start_time = time.time()
            
            # Extract video ID instantly
            video_id = self.extract_video_id(youtube_url)
            
            # Use the actual title from database, not video ID
            if existing_title and "YouTube Video" not in existing_title:
                title = existing_title
            else:
                title = "This YouTube Video"
            
            question_lower = question.lower()
            
            # Generate instant answers based on question patterns
            answer = self._get_smart_response(question_lower, title, video_id, youtube_url)
            
            elapsed = time.time() - start_time
            print(f"⚡ Instant answer generated in {elapsed:.3f} seconds")
            
            return answer
            
        except Exception as e:
            logger.error(f"Error in instant answer: {e}")
            return self._get_fallback_response()
    
    def _get_smart_response(self, question_lower, title, video_id, youtube_url):
        """Get smart responses based on question patterns"""
        
        # Channel-related questions
        if any(phrase in question_lower for phrase in ['youtube channel', 'what channel', 'which channel', 'channel name', 'name of channel']):
            return f"""**Channel Information**

I can see this video is titled: **"{title}"**

To find the exact channel name and creator information:

1. **Click the YouTube link** above the video player
2. **Visit the video page** on YouTube
3. **Look below the video** for the channel name and subscribe button

*The channel information is always visible on the actual YouTube video page.*"""

        # Person/Speaker questions
        elif any(phrase in question_lower for phrase in ['who is', 'who are', 'person', 'speaker', 'who the', 'who made']):
            return f"""**People in the Video**

**Video Title:** "{title}"

For information about specific people, presenters, or creators in this video:

• **Watch the video** - The speaker is usually introduced
• **Check the YouTube page** - Creator info is in the channel section
• **Look at the description** - Often mentions participants

*The best way to identify people is to watch the video content directly.*"""

        # Video content questions
        elif any(phrase in question_lower for phrase in ['what is this video', 'what this video about', 'what about', 'what is about', 'content']):
            return f"""**Video Content**

**Title:** "{title}"

Based on the title, this video appears to be about the topics mentioned. To get the full understanding:

**Watch the video** using the player above
**Check the transcript** if available in download options
**Visit YouTube** for the full description

The video title suggests it covers: **{self._extract_topics_from_title(title)}**"""

        # General questions
        elif any(phrase in question_lower for phrase in ['when', 'upload date', 'published', 'date']):
            return f"""**Video Details**

**Title:** "{title}"

For precise upload date and publishing information:

• Click the **YouTube link** above
• Check the **video description** on YouTube
• Look below the **video title** on YouTube

*Exact timing information is available on the YouTube video page.*"""

        # Duration questions
        elif any(phrase in question_lower for phrase in ['how long', 'duration', 'length', 'time']):
            return f"""**Video Duration**

**Title:** "{title}"

The video length is displayed in the player controls above. You can:

• **Hover over the timeline** to see total duration
• **Check the bottom-right** of the video player
• **Visit YouTube** for exact timing

*Duration is visible while watching the video.*"""

        # Summary questions
        elif any(phrase in question_lower for phrase in ['summary', 'summarize', 'main points']):
            return f"""**Video Summary**

**Title:** "{title}"

For a comprehensive summary:

1. **Watch the video** - Get the complete content
2. **Use the transcript** - Available in download options
3. **Read the description** - On the YouTube page

*The most accurate summary comes from watching the video directly.*"""

        # Default answer for other questions
        else:
            return f"""**About This Video**

**Title:** "{title}"

I can help you with information about this YouTube video. Here's what I can tell you:

• **Content** - Watch the video above for full details
• **Channel** - Visit the YouTube page for creator info  
• **Details** - Check the YouTube link for upload date
• **⏱Duration** - See the video player for length

**Try asking:**
• "What is this video about?"
• "How can I find the channel?"
• "Where can I watch this?"""

    def _extract_topics_from_title(self, title):
        """Extract potential topics from video title"""
        # Remove common non-topic words
        stop_words = ['the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'this', 'that', 'these', 'those', 'my', 'your', 'his', 'her', 'our', 'their']
        words = title.lower().split()
        topics = [word for word in words if word not in stop_words and len(word) > 2]
        
        if topics:
            return ", ".join(topics[:4])  # Return first 4 topics
        else:
            return "the content suggested by its title"

    def _get_fallback_response(self):
        """Fallback response for errors"""
        return """**Quick Assistance**

I can see this is a YouTube video in your collection. For specific information:

• **Watch the video** directly above
• **Visit the YouTube page** using the link provided
• **Check available downloads** for transcripts

The best information comes from experiencing the video content directly."""