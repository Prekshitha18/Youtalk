import logging
import re
from keybert import KeyBERT
from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
from sentence_transformers import SentenceTransformer
import torch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LocalAIService:
    def __init__(self):
        self.models = {}
        self.kw_model = None
        self._load_models()
    
    def _load_models(self):
        """Load enhanced local AI models"""
        try:
            logger.info("Loading enhanced local AI models...")
            
            # Load BART for summarization
            self.models['summarization'] = pipeline(
                "summarization",
                model="facebook/bart-large-cnn",
                tokenizer="facebook/bart-large-cnn",
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
            )
            
            # Load enhanced QA model
            self.models['qa'] = pipeline(
                "question-answering",
                model="deepset/roberta-base-squad2",
                tokenizer="deepset/roberta-base-squad2"
            )
            
            # Load semantic model for embeddings
            self.models['semantic'] = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
            
            # Load KeyBERT for topic extraction
            self.kw_model = KeyBERT()
            
            logger.info("Enhanced local AI models loaded successfully!")
            
        except Exception as e:
            logger.error(f"Error loading enhanced AI models: {e}")
            self.models = {}
            self.kw_model = None
    
    def generate_summary(self, title, description, max_length=150):
        """Generate AI summary using BART model"""
        if not self.models.get('summarization'):
            return self._fallback_summary(description)
        
        try:
            # Combine title and description for context
            context = f"Title: {title}. Description: {description}"
            
            # Limit context length
            if len(context) > 1024:
                context = context[:1024]
            
            # Generate summary
            summary = self.models['summarization'](
                context,
                max_length=max_length,
                min_length=30,
                do_sample=False
            )
            
            return summary[0]['summary_text']
            
        except Exception as e:
            logger.error(f"Summary generation error: {e}")
            return self._fallback_summary(description)
    
    def extract_topics(self, text, num_topics=5):
        """Extract key topics using KeyBERT"""
        if not self.kw_model or not text:
            return []
        
        try:
            # Extract keywords
            keywords = self.kw_model.extract_keywords(
                text,
                keyphrase_ngram_range=(1, 2),
                stop_words='english',
                top_n=num_topics
            )
            
            return [kw[0] for kw in keywords]
            
        except Exception as e:
            logger.error(f"Topic extraction error: {e}")
            return []
    
    def classify_content(self, title, description):
        """Classify video content type"""
        combined_text = f"{title} {description}".lower()
        
        # Simple rule-based classification
        categories = {
            'educational': any(word in combined_text for word in ['tutorial', 'how to', 'guide', 'learn', 'education', 'teaching', 'explain', 'lesson']),
            'entertainment': any(word in combined_text for word in ['funny', 'comedy', 'challenge', 'prank', 'entertainment', 'music', 'fun']),
            'gaming': any(word in combined_text for word in ['gameplay', 'walkthrough', 'review', 'gaming', 'lets play', 'video game']),
            'vlog': any(word in combined_text for word in ['vlog', 'day in life', 'personal', 'storytime', 'my life']),
            'review': any(word in combined_text for word in ['review', 'unboxing', 'test', 'comparison', 'vs']),
            'news': any(word in combined_text for word in ['news', 'update', 'current events', 'breaking', 'report'])
        }
        
        # Get primary category
        primary = None
        for category, matches in categories.items():
            if matches:
                primary = category
                break
        
        return primary or 'entertainment'  # Default to entertainment
    
    def analyze_question_intent(self, question):
        """Analyze question intent for better answering"""
        question_lower = question.lower()
        
        intent_map = {
            'content': ['what is this', 'what about', 'summary', 'describe', 'explain'],
            'creator': ['who made', 'who created', 'who started', 'who owns', 'whose channel'],
            'purpose': ['why', 'purpose', 'goal', 'objective', 'aim'],
            'audience': ['who is this for', 'target audience', 'suitable for'],
            'type': ['what type', 'kind of', 'category', 'genre'],
            'educational': ['educational', 'learn', 'teach', 'educational value'],
            'quality': ['good', 'bad', 'quality', 'worth watching', 'recommend']
        }
        
        for intent, keywords in intent_map.items():
            if any(keyword in question_lower for keyword in keywords):
                return intent
        
        return 'general'
    
    def answer_content_question(self, question, context):
        """Answer content-based questions using enhanced QA"""
        if not self.models.get('qa') or not context:
            return None
        
        try:
            result = self.models['qa'](
                question=question,
                context=context[:1000],  # Limit context
                max_answer_len=100,
                handle_impossible_answer=True
            )
            
            if result['score'] > 0.1:  # Confidence threshold
                return result['answer']
            
        except Exception as e:
            logger.error(f"QA error: {e}")
        
        return None
    
    def _fallback_summary(self, description):
        """Fallback summary when AI fails"""
        if not description:
            return "No description available."
        
        # Extract first meaningful sentence
        sentences = re.split(r'[.!?]+', description)
        for sentence in sentences:
            clean_sentence = sentence.strip()
            if len(clean_sentence) > 20 and len(clean_sentence) < 200:
                return clean_sentence
        
        # Fallback to first 150 characters
        return description[:150] + '...' if len(description) > 150 else description

# Global instance
local_ai_service = LocalAIService()