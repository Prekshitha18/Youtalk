import hashlib
import logging
import time
import re
from database import get_cached_answer, cache_answer, get_video_by_id
from youtube_service import youtube_service
from local_ai_service import local_ai_service
from config import AI_MODELS, CONTENT_CATEGORIES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EnhancedYouTubeQAProcessor:
    def __init__(self):
        logger.info("Initializing Enhanced YouTube API + Local AI Processor")
        self.youtube_service = youtube_service
        self.ai_service = local_ai_service
    
    def generate_answer(self, video_id, question, transcript, video_title="", video_description=""):
        """Generate enhanced answer using YouTube API + Local AI"""
        start_time = time.time()
        
        try:
            # Clean the question
            cleaned_question = self._clean_question(question)
            print(f"Processing: '{cleaned_question}'")
            
            # Create question hash for caching
            question_hash = hashlib.md5(cleaned_question.lower().encode()).hexdigest()
            
            # Check cache first
            cached = get_cached_answer(video_id, question_hash)
            if cached:
                logger.info("Using cached answer")
                elapsed = time.time() - start_time
                print(f"Cached answer in {elapsed:.3f} seconds")
                return cached['answer_text']
            
            # Get video from database
            video = get_video_by_id(video_id)
            if not video:
                return "Video information not found."
            
            youtube_url = video.get('youtube_link', '')
            if not youtube_url:
                return "YouTube URL not available."
            
            # Get video details from YouTube API
            video_details = self.youtube_service.get_video_details(youtube_url)
            
            if video_details:
                answer = self._generate_enhanced_answer(cleaned_question, video_details, youtube_url)
            else:
                # Fallback to basic info
                answer = self._generate_fallback_answer(cleaned_question, video.get('title', 'This video'), youtube_url)
            
            # Cache the answer
            cache_answer(video_id, question_hash, question, answer, "enhanced_youtube")
            
            elapsed = time.time() - start_time
            print(f"Enhanced answer generated in {elapsed:.2f} seconds")
            return answer
            
        except Exception as e:
            logger.error(f"Error in enhanced YouTube QA: {e}")
            return self._get_error_response()
    
    def _clean_question(self, question):
        """Clean and correct spelling in the question"""
        corrections = {
            'whos': 'whose', 'whos ': 'whose ', 'rhis': 'this', 'wat': 'what',
            'wats': 'what\'s', 'wher': 'where', 'wen': 'when', 'hoe': 'how'
        }
        
        cleaned = question.strip()
        for wrong, correct in corrections.items():
            cleaned = re.sub(r'\b' + wrong + r'\b', correct, cleaned, flags=re.IGNORECASE)
        
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]
        
        return cleaned
    
    def _generate_enhanced_answer(self, question, video_details, youtube_url):
        """Generate enhanced answer using YouTube API + Local AI"""
        question_lower = question.lower()
        title = video_details['title']
        channel = video_details['channel_title']
        description = video_details['description']
        views = f"{int(video_details['view_count']):,}" if video_details['view_count'] else "unknown"
        published = video_details['published_at'][:10]
        duration = self._parse_duration(video_details['duration'])
        
        print(f"YouTube API Data - Title: '{title}', Channel: '{channel}'")
        
        # Analyze question intent
        intent = self.ai_service.analyze_question_intent(question)
        
        # Generate AI-enhanced content
        ai_summary = self.ai_service.generate_summary(title, description)
        topics = self.ai_service.extract_topics(description, 4)
        content_type = self.ai_service.classify_content(title, description)
        
        # Route to appropriate answer generator
        if intent == 'content' or any(phrase in question_lower for phrase in ['what is this', 'what about', 'summary']):
            return self._generate_content_answer(title, channel, ai_summary, topics, content_type, views, published)
        
        elif intent == 'creator' or any(phrase in question_lower for phrase in ['who made', 'who created', 'who started', 'whose channel']):
            return self._generate_creator_answer(title, channel, description, views, published)
        
        elif any(phrase in question_lower for phrase in ['youtube channel', 'what channel', 'channel name']):
            return self._generate_channel_answer(channel, views, published)
        
        elif any(phrase in question_lower for phrase in ['when', 'upload date', 'published']):
            return f"**Upload Date**: {published}\n\n**Video**: {title}\n**Channel**: {channel}\n\nPublished on YouTube."
        
        elif any(phrase in question_lower for phrase in ['how many views', 'view count']):
            return f"**Views**: {views}\n\n**Video**: {title}\n**Channel**: {channel}\n\nTotal YouTube views."
        
        elif any(phrase in question_lower for phrase in ['how long', 'duration']):
            return f"**Duration**: {duration}\n\n**Video**: {title}\n**Channel**: {channel}"
        
        elif intent == 'educational' or any(phrase in question_lower for phrase in ['educational', 'learn', 'teach']):
            return self._generate_educational_answer(title, channel, content_type, ai_summary)
        
        elif intent == 'type' or any(phrase in question_lower for phrase in ['what type', 'kind of']):
            return self._generate_type_answer(title, channel, content_type, topics)
        
        else:
            return self._generate_smart_answer(question, title, channel, ai_summary, content_type, views, published)
    
    def _generate_content_answer(self, title, channel, ai_summary, topics, content_type, views, published):
        """Generate content-focused answer"""
        topics_text = ", ".join(topics) if topics else "Various topics"
        
        answer = f"""**Video**: {title}
**Channel**: {channel}

**AI Analysis**: {ai_summary}

**Key Topics**: {topics_text}
**Content Type**: {content_type.title()}

**Stats**: {views} views | {published}"""

        return answer
    
    def _generate_creator_answer(self, title, channel, description, views, published):
        """Generate creator-focused answer"""
        # Try to extract creator info from description
        creator_clues = self._extract_creator_clues(description)
        
        answer = f"""**Channel**: {channel}

 **Video**: {title}

{creator_clues}

 **Channel Stats**: {views} views on this video
 **Active Since**: {published}"""

        return answer
    
    def _generate_channel_answer(self, channel, views, published):
        """Generate channel-focused answer"""
        return f"""**Channel**: {channel}

**Popularity**: {views} views on this video
**Content Since**: {published}

This channel creates YouTube content across various topics."""

    def _generate_educational_answer(self, title, channel, content_type, ai_summary):
        """Generate educational value assessment"""
        educational_value = "primarily educational" if content_type == 'educational' else "more entertainment-focused"
        
        return f"""**Educational Assessment**

**Video**: {title}
**Channel**: {channel}

**Content Type**: {content_type.title()}
**Learning Value**: {educational_value}

**AI Analysis**: {ai_summary}

{"Good for learning" if content_type == 'educational' else "🎯 Focused on entertainment"}"""

    def _generate_type_answer(self, title, channel, content_type, topics):
        """Generate content type analysis"""
        return f"""**Content Analysis**

**Video**: {title}
**Channel**: {channel}

**Category**: {content_type.title()}
**Primary Focus**: {', '.join(topics[:3]) if topics else 'Various content'}

{"Educational content" if content_type == 'educational' else "Entertainment content" if content_type == 'entertainment' else "General content"}"""

    def _generate_smart_answer(self, question, title, channel, ai_summary, content_type, views, published):
        """Generate smart answer for general questions"""
        return f""" **Answer**: {question}

**Video**: {title}
**Channel**: {channel}

**AI Insight**: {ai_summary}

**Content Type**: {content_type.title()}
**Popularity**: {views} views

Based on the video content and description."""

    def _extract_creator_clues(self, description):
        """Extract potential creator information from description"""
        if not description:
            return "Creator information available on YouTube channel page."
        
        # Look for common creator patterns
        patterns = [
            r'follow me on (\w+)',
            r'check out my (\w+)',
            r'my (?:website|blog)',
            r'contact:? (\S+@\S+)',
            r'(\w+) social media'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, description.lower())
            if match:
                return f"Creator engagement mentioned in video description."
        
        return "Check YouTube channel for creator details and social links."

    def _parse_duration(self, duration_str):
        """Parse ISO 8601 duration to readable format"""
        if duration_str.startswith('PT'):
            time_str = duration_str[2:]
            if 'H' in time_str and 'M' in time_str:
                hours = time_str.split('H')[0]
                minutes = time_str.split('H')[1].split('M')[0]
                return f"{hours}h {minutes}m"
            elif 'H' in time_str:
                hours = time_str.split('H')[0]
                return f"{hours} hours"
            elif 'M' in time_str:
                minutes = time_str.split('M')[0]
                return f"{minutes} minutes"
            elif 'S' in time_str:
                seconds = time_str.split('S')[0]
                return f"{seconds} seconds"
        return "unknown duration"

    def _generate_fallback_answer(self, question, title, youtube_url):
        """Fallback when YouTube API fails"""
        return f"""**Video Information**

**Title**: {title}

For detailed information about "{question}", please visit the YouTube page or watch the video directly.

The video player above provides the complete content experience."""

    def _get_error_response(self):
        """Error response when everything fails"""
        return """ **Temporary Issue**

I'm having trouble accessing video information right now. Please try:

• Watching the video directly above
• Visiting the YouTube page
• Asking again in a moment

The system should be back to normal shortly."""

# Global instance
youtube_qa_processor = EnhancedYouTubeQAProcessor()