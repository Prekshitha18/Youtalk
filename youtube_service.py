import googleapiclient.discovery
import logging
from urllib.parse import urlparse, parse_qs
from config import YOUTUBE_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class YouTubeService:
    def __init__(self):
        self.api_key = YOUTUBE_API_KEY
        if self.api_key and self.api_key != 'YOUR_YOUTUBE_API_KEY_HERE':
            self.youtube = googleapiclient.discovery.build('youtube', 'v3', developerKey=self.api_key)
            self.api_available = True
        else:
            self.api_available = False
            logger.warning("YouTube API key not configured")
    
    def extract_video_id(self, youtube_url):
        """Extract video ID from YouTube URL"""
        try:
            if 'youtu.be' in youtube_url:
                return youtube_url.split('/')[-1].split('?')[0]
            elif 'youtube.com' in youtube_url:
                url_data = urlparse(youtube_url)
                query_params = parse_qs(url_data.query)
                return query_params.get('v', [None])[0]
        except Exception as e:
            logger.error(f"Error extracting video ID: {e}")
        return None
    
    def get_video_details(self, youtube_url):
        """Get video details using YouTube API"""
        if not self.api_available:
            return None
        
        try:
            video_id = self.extract_video_id(youtube_url)
            if not video_id:
                return None
            
            # Make API request
            request = self.youtube.videos().list(
                part="snippet,statistics,contentDetails",
                id=video_id
            )
            response = request.execute()
            
            if response['items']:
                return self._parse_video_data(response['items'][0])
            else:
                return None
                
        except Exception as e:
            logger.error(f"YouTube API error: {e}")
            return None
    
    def _parse_video_data(self, video_data):
        """Parse YouTube API response into usable format"""
        snippet = video_data['snippet']
        statistics = video_data.get('statistics', {})
        content_details = video_data.get('contentDetails', {})
        
        return {
            'video_id': video_data['id'],
            'title': snippet['title'],
            'description': snippet['description'],
            'channel_title': snippet['channelTitle'],
            'channel_id': snippet['channelId'],
            'published_at': snippet['publishedAt'],
            'view_count': statistics.get('viewCount', 0),
            'like_count': statistics.get('likeCount', 0),
            'comment_count': statistics.get('commentCount', 0),
            'duration': content_details.get('duration', 'PT0S'),
            'thumbnails': snippet.get('thumbnails', {}),
            'tags': snippet.get('tags', []),
            'category_id': snippet.get('categoryId')
        }
    
    def get_channel_details(self, channel_id):
        """Get channel details using YouTube API"""
        if not self.api_available:
            return None
        
        try:
            request = self.youtube.channels().list(
                part="snippet,statistics",
                id=channel_id
            )
            response = request.execute()
            
            if response['items']:
                return self._parse_channel_data(response['items'][0])
            else:
                return None
                
        except Exception as e:
            logger.error(f"YouTube API channel error: {e}")
            return None
    
    def _parse_channel_data(self, channel_data):
        """Parse channel API response"""
        snippet = channel_data['snippet']
        statistics = channel_data.get('statistics', {})
        
        return {
            'channel_id': channel_data['id'],
            'title': snippet['title'],
            'description': snippet['description'],
            'custom_url': snippet.get('customUrl'),
            'published_at': snippet['publishedAt'],
            'subscriber_count': statistics.get('subscriberCount', 0),
            'video_count': statistics.get('videoCount', 0),
            'view_count': statistics.get('viewCount', 0),
            'thumbnails': snippet.get('thumbnails', {})
        }

# Global instance
youtube_service = YouTubeService()