import mysql.connector
from mysql.connector import Error

def create_database():
    """Create database if it doesn't exist"""
    try:
        connection = mysql.connector.connect(
            host='localhost',
            user='root',
            password='root'
        )
        
        if connection.is_connected():
            cursor = connection.cursor()
            
            # Create database if it doesn't exist
            cursor.execute("CREATE DATABASE IF NOT EXISTS youtalk_db")
            print("✅ Database 'youtalk_db' created or already exists!")
            
            cursor.close()
            connection.close()
            
    except Error as e:
        print(f"Error creating database: {e}")

def get_db_connection():
    """Create and return database connection"""
    try:
        connection = mysql.connector.connect(
            host='localhost',
            user='root',
            password='root',
            database='youtalk_db'
        )
        return connection
    except Error as e:
        print(f"Database connection error: {e}")
        return None

def init_db():
    """Initialize database tables"""
    # First create the database if it doesn't exist
    create_database()
    
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            
            # Create users table
            users_table = """
            CREATE TABLE IF NOT EXISTS users (
                id INT PRIMARY KEY AUTO_INCREMENT,
                username VARCHAR(50) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                role ENUM('admin', 'user') DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
            cursor.execute(users_table)
            print("✅ Users table created!")
            
            # Create videos table
            videos_table = """
            CREATE TABLE IF NOT EXISTS videos (
                id INT PRIMARY KEY AUTO_INCREMENT,
                youtube_link VARCHAR(255) NOT NULL,
                youtube_id VARCHAR(20) NOT NULL,
                title VARCHAR(255),
                description TEXT,
                thumbnail_url VARCHAR(255),
                video_path VARCHAR(500),
                audio_path VARCHAR(500),
                transcript_path VARCHAR(500),
                added_by INT,
                user_type ENUM('admin', 'user'),
                download_status ENUM('pending', 'downloading', 'completed', 'failed') DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (added_by) REFERENCES users(id) ON DELETE CASCADE
            )
            """
            cursor.execute(videos_table)
            print("✅ Videos table created!")
            
            # Create video_questions table for Q&A system
            video_questions_table = """
            CREATE TABLE IF NOT EXISTS video_questions (
                id INT PRIMARY KEY AUTO_INCREMENT,
                video_id INT NOT NULL,
                user_id INT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_video_id (video_id),
                INDEX idx_user_id (user_id),
                INDEX idx_created_at (created_at)
            )
            """
            cursor.execute(video_questions_table)
            print("✅ Video Questions table created!")
            
            # Create user feedback table
            user_feedback_table = """
            CREATE TABLE IF NOT EXISTS question_feedback (
                id INT PRIMARY KEY AUTO_INCREMENT,
                question_id INT NOT NULL,
                user_id INT NOT NULL,
                is_helpful BOOLEAN,
                feedback_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (question_id) REFERENCES video_questions(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
            cursor.execute(user_feedback_table)
            print("✅ User feedback table created!")
            
            # Create AI cache table
            ai_cache_table = """
            CREATE TABLE IF NOT EXISTS ai_response_cache (
                id INT PRIMARY KEY AUTO_INCREMENT,
                video_id INT NOT NULL,
                question_hash VARCHAR(64) UNIQUE,
                question_text TEXT,
                answer_text TEXT,
                context_used TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
            )
            """
            cursor.execute(ai_cache_table)
            print("✅ AI cache table created!")
            
            # Create default users if they don't exist
            cursor.execute("SELECT COUNT(*) FROM users WHERE username IN ('admin', 'user')")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin123', 'admin')")
                cursor.execute("INSERT INTO users (username, password, role) VALUES ('user', 'user123', 'user')")
                print("✅ Default users created!")
            else:
                print("✅ Default users already exist!")
            
            connection.commit()
            print("🎉 Database initialization completed successfully!")
            
        except Error as e:
            print(f"❌ Error initializing database: {e}")
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

def check_database_status():
    """Check if database and tables are properly set up"""
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            
            # Check if users table exists and has data
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            
            # Check if videos table exists
            cursor.execute("SELECT COUNT(*) FROM videos")
            video_count = cursor.fetchone()[0]
            
            # Check if video_questions table exists
            cursor.execute("SELECT COUNT(*) FROM video_questions")
            questions_count = cursor.fetchone()[0]
            
            print(f"📊 Database Status:")
            print(f"   - Users: {user_count}")
            print(f"   - Videos: {video_count}")
            print(f"   - Questions: {questions_count}")
            print(f"   - Connection: ✅ Working")
            
            cursor.close()
            connection.close()
            return True
            
    except Error as e:
        print(f"❌ Database status check failed: {e}")
        return False

# Q&A System Database Functions

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

def add_question(video_id, user_id, question):
    """Add a new question to the database"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO video_questions (video_id, user_id, question) VALUES (%s, %s, %s)",
                (video_id, user_id, question)
            )
            question_id = cursor.lastrowid
            connection.commit()
            return question_id
        except Error as e:
            print(f"Error adding question: {e}")
            return None
        finally:
            cursor.close()
            connection.close()
    return None

def update_answer(question_id, answer):
    """Update the answer for a question"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute(
                "UPDATE video_questions SET answer = %s WHERE id = %s",
                (answer, question_id)
            )
            connection.commit()
            return True
        except Error as e:
            print(f"Error updating answer: {e}")
            return False
        finally:
            cursor.close()
            connection.close()
    return False

def get_video_questions(video_id):
    """Get all questions and answers for a video"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT vq.*, u.username 
                FROM video_questions vq 
                JOIN users u ON vq.user_id = u.id 
                WHERE vq.video_id = %s 
                ORDER BY vq.created_at DESC
            """, (video_id,))
            questions = cursor.fetchall()
            result = []
            for q in questions:
                result.append({
                    'id': q['id'],
                    'video_id': q['video_id'],
                    'user_id': q['user_id'],
                    'username': q['username'],
                    'question': q['question'],
                    'answer': q['answer'] if q['answer'] else None,  # Keep as None if NULL
                    'created_at': q['created_at'].isoformat() if q['created_at'] else None
                })
            
            return result
        except Error as e:
            print(f"Error getting questions: {e}")
            return []
        finally:
            cursor.close()
            connection.close()
    return []

def get_question_with_user(question_id):
    """Get a specific question with user info"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT vq.*, u.username, v.title as video_title
                FROM video_questions vq 
                JOIN users u ON vq.user_id = u.id 
                JOIN videos v ON vq.video_id = v.id
                WHERE vq.id = %s
            """, (question_id,))
            question = cursor.fetchone()
            return question
        except Error as e:
            print(f"Error getting question: {e}")
            return None
        finally:
            cursor.close()
            connection.close()
    return None

def add_feedback(question_id, user_id, is_helpful, feedback_text=None):
    """Add user feedback for an answer"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO question_feedback (question_id, user_id, is_helpful, feedback_text) 
                VALUES (%s, %s, %s, %s)
            """, (question_id, user_id, is_helpful, feedback_text))
            connection.commit()
            return True
        except Error as e:
            print(f"Error adding feedback: {e}")
            return False
        finally:
            cursor.close()
            connection.close()
    return False

def get_cached_answer(video_id, question_hash):
    """Get cached answer if available"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT answer_text, context_used 
                FROM ai_response_cache 
                WHERE video_id = %s AND question_hash = %s
            """, (video_id, question_hash))
            cached = cursor.fetchone()
            return cached
        except Error as e:
            print(f"Error getting cached answer: {e}")
            return None
        finally:
            cursor.close()
            connection.close()
    return None

def cache_answer(video_id, question_hash, question_text, answer_text, context_used):
    """Cache an AI response for future use"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO ai_response_cache 
                (video_id, question_hash, question_text, answer_text, context_used) 
                VALUES (%s, %s, %s, %s, %s)
            """, (video_id, question_hash, question_text, answer_text, context_used))
            connection.commit()
            return True
        except Error as e:
            print(f"Error caching answer: {e}")
            return False
        finally:
            cursor.close()
            connection.close()
    return False

if __name__ == "__main__":
    print("🚀 Initializing YouTALK Database...")
    init_db()
    print("\n🔍 Checking database status...")
    check_database_status()
    print("\n✨ YouTALK Database is ready! You can now run app.py")