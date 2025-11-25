import hashlib
import logging
import time
import re
import os
from database import get_cached_answer, cache_answer, get_video_by_id
from youtube_service import youtube_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CleanEnhancedQAProcessor:
    def __init__(self):
        logger.info("🚀 Initializing Clean Enhanced QA Processor")
        self.youtube_service = youtube_service
        self.ai_models = self._load_simple_ai()
    
    def _load_simple_ai(self):
        """Load simple AI models without complex dependencies"""
        try:
            from transformers import pipeline
            logger.info("🤖 Loading simple AI models...")
            
            return {
                'summarization': pipeline("summarization", model="facebook/bart-large-cnn"),
                'qa': pipeline("question-answering", model="deepset/roberta-base-squad2")
            }
        except Exception as e:
            logger.warning(f"AI models not available: {e}")
            return {}
    
    def generate_answer(self, video_id, question, transcript, video_title="", video_description=""):
        start_time = time.time()
        
        try:
            print(f"🎯 Processing: '{question}'")
            print(f"📊 Transcript available: {len(transcript) if transcript else 0} characters")
            
            # Check cache
            question_hash = hashlib.md5(question.lower().encode()).hexdigest()
            cached = get_cached_answer(video_id, question_hash)
            if cached:
                return cached['answer_text']
            
            # Get video info
            video = get_video_by_id(video_id)
            if not video:
                return "Video information not found."
            
            # PRIORITY 1: Use transcript if available and substantial
            if transcript and len(transcript.strip()) > 100:
                print("🎯 Using enhanced transcript-based answer generation")
                answer = self._generate_transcript_answer(question, transcript, video_title, video)
                elapsed = time.time() - start_time
                print(f"✅ Transcript answer in {elapsed:.2f} seconds")
                
                # Cache response
                cache_answer(video_id, question_hash, question, answer, "transcript")
                return answer
            
            # PRIORITY 2: Use YouTube API data if available
            elif youtube_url:
                print("🎯 Using YouTube API data (fallback)")
                video_details = self.youtube_service.get_video_details(youtube_url)
                if video_details:
                    answer = self._generate_clean_answer(question, video_details)
                else:
                    answer = self._generate_basic_answer(question, video.get('title', 'This video'))
                
                elapsed = time.time() - start_time
                print(f"✅ YouTube API answer in {elapsed:.2f} seconds")
                
                # Cache response
                cache_answer(video_id, question_hash, question, answer, "youtube_api")
                return answer
            
            # PRIORITY 3: Basic fallback
            else:
                answer = self._generate_basic_answer(question, video.get('title', 'This video'))
                cache_answer(video_id, question_hash, question, answer, "basic")
                return answer
            
        except Exception as e:
            logger.error(f"Error: {e}")
            return "I encountered an error while processing your question. Please try again."
    
    def _generate_transcript_answer(self, question, transcript, video_title, video):
        """Generate answer by analyzing the transcript"""
        try:
            question_lower = question.lower()
            
            # Use AI models if available for better transcript analysis
            if self.ai_models.get('qa'):
                return self._generate_ai_transcript_answer(question, transcript, video_title, video)
            else:
                return self._generate_simple_transcript_answer(question, transcript, video_title, video)
                
        except Exception as e:
            logger.error(f"Error in transcript analysis: {e}")
            return self._generate_simple_transcript_answer(question, transcript, video_title, video)
    
    def _generate_ai_transcript_answer(self, question, transcript, video_title, video):
        try:
            # For broad questions like "What is Python?", use more context
            question_lower = question.lower()
            
            # Use more context for broad/conceptual questions
            context_length = 2000 if any(word in question_lower for word in ['what is', 'what are', 'explain', 'define']) else 1000
            context = transcript[:context_length]
            
            qa_result = self.ai_models['qa'](
                question=question,
                context=context
            )
            
            # Lower confidence threshold for broad questions, higher for specific ones
            is_broad_question = any(word in question_lower for word in ['what is', 'what are', 'explain', 'define', 'overview'])
            confidence_threshold = 0.15 if is_broad_question else 0.25
            
            if qa_result['score'] > confidence_threshold:
                # Enhance the answer for better context
                enhanced_answer = self._enhance_ai_answer(qa_result['answer'], question, video_title)
                return enhanced_answer
            else:
                # For low-confidence AI answers, use enhanced simple matching
                print(f"🤖 AI confidence too low ({qa_result['score']:.2f}), using enhanced transcript analysis")
                return self._generate_enhanced_transcript_answer(question, transcript, video_title, video)
                
        except Exception as e:
            logger.warning(f"AI transcript analysis failed: {e}")
            return self._generate_enhanced_transcript_answer(question, transcript, video_title, video)

    def _enhance_ai_answer(self, ai_answer, question, video_title):
        """Enhance AI answers with better formatting and context"""
        question_lower = question.lower()
        
        # For "what is" questions, provide more structured answers
        if 'what is' in question_lower:
            return f"""🎬 **Based on the video "{video_title}":**

    **{question}**

    According to the video content: {ai_answer}*"""
        
        else:
            return f"""

    **Answer**: {ai_answer}

    **Video**: {video_title}"""

    def _generate_enhanced_transcript_answer(self, question, transcript, video_title, video):
        """Enhanced simple text-based transcript analysis"""
        question_lower = question.lower()
        question_words = set(re.findall(r'\b\w+\b', question_lower))
        
        # Remove common stop words
        stop_words = {'what', 'who', 'where', 'when', 'why', 'how', 'the', 'a', 'an', 'is', 'are', 'was', 'were', 'do', 'does', 'did', 'this', 'that', 'these', 'those'}
        meaningful_words = question_words - stop_words
        
        if not meaningful_words:
            meaningful_words = question_words
        
        # For "what is" questions, look for definition patterns
        if any(phrase in question_lower for phrase in ['what is', 'what are', 'define']):
            return self._find_definition_patterns(question, transcript, video_title, meaningful_words)
        
        # Split transcript into sentences with context
        sentences = re.split(r'[.!?]+', transcript)
        relevant_sentences = []
        
        for i, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if len(sentence) < 15:  # Skip very short sentences
                continue
                
            sentence_lower = sentence.lower()
            sentence_words = set(re.findall(r'\b\w+\b', sentence_lower))
            
            # Calculate relevance based on word overlap
            common_words = meaningful_words.intersection(sentence_words)
            if common_words:
                relevance_score = len(common_words) / len(meaningful_words) if meaningful_words else 0
                
                # Boost score if sentence contains definition keywords
                definition_boost = 1.5 if any(word in sentence_lower for word in ['is a', 'means', 'defined as', 'refers to', 'called']) else 1.0
                relevance_score *= definition_boost
                
                if relevance_score > 0.15:  # Lower threshold
                    # Get some context around the sentence
                    context_start = max(0, i-1)
                    context_end = min(len(sentences), i+2)
                    context_sentences = sentences[context_start:context_end]
                    context_text = ' '.join([s.strip() for s in context_sentences if s.strip()])
                    
                    relevant_sentences.append((context_text, relevance_score))
        
        # Sort by relevance and get top segments
        relevant_sentences.sort(key=lambda x: x[1], reverse=True)
        top_segments = [segment for segment, score in relevant_sentences[:2]]  # Limit to 2 best segments
        
        if top_segments:
            answer = f"""🎬 **Based on the video "{video_title}":**

    **{question}**

    """
            for i, segment in enumerate(top_segments, 1):
                answer += f"{segment}\n\n"
            
            answer += "💡 *This answer is generated from analyzing the actual video transcript.*"
        else:
            answer = self._generate_comprehensive_fallback(question, transcript, video_title)
        
        return answer

    def _find_definition_patterns(self, question, transcript, video_title, keywords):
        """Look for definition-like patterns in the transcript"""
        sentences = re.split(r'[.!?]+', transcript)
        
        # Look for sentences that seem to define or explain
        definition_patterns = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20:
                continue
                
            sentence_lower = sentence.lower()
            
            # Check for definition patterns
            is_definition = (
                any(keyword in sentence_lower for keyword in keywords) and
                any(pattern in sentence_lower for pattern in [
                    'is a', 'is an', 'are', 'means', 'defined as', 
                    'refers to', 'called', 'known as', 'essentially'
                ])
            )
            
            if is_definition:
                definition_patterns.append(sentence)
        
        if definition_patterns:
            answer = f"""🎬 **Based on the video "{video_title}":**

    **{question}**

    """
            for i, definition in enumerate(definition_patterns[:3], 1):
                answer += f"• {definition}\n"
            
            answer += "\n💡 *This explanation comes from the actual video content.*"
            return answer
        
        return None

    def _generate_comprehensive_fallback(self, question, transcript, video_title):
        """Generate a comprehensive fallback when no specific matches found"""
        # Get first few sentences as general context
        sentences = re.split(r'[.!?]+', transcript)
        first_meaningful = [s.strip() for s in sentences if len(s.strip()) > 30][:2]
        
        if first_meaningful:
            context_preview = ' '.join(first_meaningful)
            return f"""🔍 **Video Content Analysis for "{video_title}"**

    I've analyzed the transcript and here's what I can share about the video content:

    {context_preview[:300]}...

    **Regarding your question**: "{question}"

    The video appears to cover this topic, but I couldn't find a direct match in the transcript. 

    💡 **Suggestions**:
    • Watch the video for complete understanding
    • Try asking about specific aspects mentioned above
    • The video may use different terminology"""

        else:
            return f"""📺 **Video Analysis for "{video_title}"**

    I've reviewed the transcript but couldn't find specific information about "{question}".

    The video might cover this topic using different terminology or it may be part of broader discussions.

    💡 **Try**: Watching the video directly or asking about specific concepts you heard."""
    
    def _generate_simple_transcript_answer(self, question, transcript, video_title, video):
        """Simple text-based transcript analysis"""
        question_lower = question.lower()
        question_words = set(re.findall(r'\b\w+\b', question_lower))
        
        # Remove common stop words
        stop_words = {'what', 'who', 'where', 'when', 'why', 'how', 'the', 'a', 'an', 'is', 'are', 'was', 'were', 'do', 'does', 'did'}
        meaningful_words = question_words - stop_words
        
        if not meaningful_words:
            meaningful_words = question_words
        
        # Split transcript into sentences
        sentences = re.split(r'[.!?]+', transcript)
        relevant_sentences = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20:  # Skip very short sentences
                continue
                
            sentence_lower = sentence.lower()
            sentence_words = set(re.findall(r'\b\w+\b', sentence_lower))
            
            # Calculate relevance based on word overlap
            common_words = meaningful_words.intersection(sentence_words)
            if common_words:
                relevance_score = len(common_words) / len(meaningful_words) if meaningful_words else 0
                if relevance_score > 0.2:  # 20% match threshold
                    relevant_sentences.append((sentence, relevance_score))
        
        # Sort by relevance and get top sentences
        relevant_sentences.sort(key=lambda x: x[1], reverse=True)
        top_sentences = [sentence for sentence, score in relevant_sentences[:3]]
        
        if top_sentences:
            answer = f"""🎬 **Based on the video transcript for "{video_title}":**

"""
            for i, sentence in enumerate(top_sentences, 1):
                answer += f"• {sentence}\n"
            
            answer += f"""
**Source**: Actual video transcript analysis
**Relevance**: Found {len(top_sentences)} relevant segments"""
        else:
            answer = f"""🔍 **Transcript Analysis for "{video_title}"**

I reviewed the video transcript but didn't find specific mentions of "{question}". 

The video might not cover this topic in detail, or it may be discussed using different terminology.

**Alternative**: Try rephrasing your question or asking about broader topics covered in the video."""
        
        return answer
    
    def _generate_clean_answer(self, question, video_details):
        """Generate clean formatted answer (YouTube API fallback)"""
        question_lower = question.lower()
        title = video_details['title']
        channel = video_details['channel_title']
        description = video_details['description']
        views = f"{int(video_details['view_count']):,}" if video_details['view_count'] else "unknown"
        published = video_details['published_at'][:10]
        
        print(f"📊 Using YouTube API: '{title}', Channel: '{channel}'")
        
        # Generate AI summary if available
        ai_summary = self._generate_simple_summary(description) if description else "No description available"
        
        # Route questions
        if any(phrase in question_lower for phrase in ['what is this', 'what about', 'what this video']):
            return f"""🎬 **AI Summary**: {ai_summary}

**Channel**: {channel}
**Views**: {views} | **Uploaded**: {published}

💡 *Transcript not available - using video metadata*"""
        
        elif any(phrase in question_lower for phrase in ['who', 'channel', 'whose', 'creator']):
            return f"""🔍 **Channel**: {channel}

**Video**: {title}
**Stats**: {views} views | {published}

👤 *Transcript not available - using video metadata*"""
        
        elif any(phrase in question_lower for phrase in ['when', 'upload']):
            return f"📅 **Uploaded**: {published}\n\n**Video**: {title}\n**Channel**: {channel}\n\n*Transcript not available*"
        
        elif any(phrase in question_lower for phrase in ['views', 'how many views']):
            return f"👀 **Views**: {views}\n\n**Video**: {title}\n**Channel**: {channel}\n\n*Transcript not available*"
        
        else:
            return f"""🤔 **Answer**

**Video**: {title}
**Channel**: {channel}

**AI Insight**: {ai_summary}

📊 {views} views | 📅 {published}

*Transcript not available - using video metadata*"""
    
    def _generate_simple_summary(self, description):
        """Generate simple summary"""
        if not self.ai_models.get('summarization'):
            # Fallback: first meaningful sentence
            sentences = re.split(r'[.!?]+', description)
            for sentence in sentences:
                clean = sentence.strip()
                if len(clean) > 20:
                    return clean
            return description[:150] + '...' if len(description) > 150 else description
        
        try:
            # Use AI for summary
            context = description[:1000]
            summary = self.ai_models['summarization'](context, max_length=100, min_length=30, do_sample=False)
            return summary[0]['summary_text']
        except:
            return description[:150] + '...' if len(description) > 150 else description
    
    def _generate_basic_answer(self, question, title):
        """Basic fallback answer"""
        question_lower = question.lower()
        
        if any(phrase in question_lower for phrase in ['what is this', 'what about']):
            return f"🎬 **Video**: {title}\n\n*Transcript not available* - Watch the video above to learn about its content."
        
        elif any(phrase in question_lower for phrase in ['who', 'channel']):
            return f"🔍 *Transcript not available* - Visit the YouTube page to see the channel information.\n\n**Video**: {title}"
        
        else:
            return f"📺 **Video**: {title}\n\n*Transcript not available* - Please watch the video or visit YouTube for detailed information."

# Global instance
clean_qa_processor = CleanEnhancedQAProcessor()