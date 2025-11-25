import os

# YouTube API Configuration
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY', 'AIzaSyCxUNzgdICowqfQkBiHDOJ6KLSHwMQW6Fo')

# Enhanced Local AI Model Configuration
AI_MODELS = {
    'summarization': 'facebook/bart-large-cnn',
    'qa_model': 'deepset/roberta-base-squad2',
    'semantic_model': 'sentence-transformers/all-MiniLM-L6-v2',
    'topic_model': 'sentence-transformers/all-MiniLM-L6-v2'
}

# Content Classification
CONTENT_CATEGORIES = {
    'educational': ['tutorial', 'how to', 'guide', 'learn', 'education', 'teaching', 'explain'],
    'entertainment': ['funny', 'comedy', 'challenge', 'prank', 'entertainment', 'music'],
    'gaming': ['gameplay', 'walkthrough', 'review', 'gaming', 'lets play'],
    'vlog': ['vlog', 'day in life', 'personal', 'storytime'],
    'review': ['review', 'unboxing', 'test', 'comparison'],
    'news': ['news', 'update', 'current events', 'breaking']
}

# Cache Configuration
CACHE_ENABLED = True
CACHE_DURATION = 3600  # 1 hour