AI YouTube Video Downloader & QA System

This project is a Flask-based platform that allows users to download YouTube videos, extract audio, generate transcripts, and run AI-powered Q&A on the content. It supports multi-user login, admin management, background processing, and provides detailed debugging tools for video validation.


---

 Key Features

🔹 YouTube Video Processing

Add and manage YouTube video links

Automatic extraction of title, description, and thumbnail

Background downloading with concurrency control

Audio extraction from video

Transcription of audio into text

Automatic validation of downloaded files

Smart repair mechanism for corrupted videos


🔹 User Account System

Signup and Login

User roles: Normal User and Admin

Users can only see their own uploaded videos

Admin can view all videos in the system


🔹 AI-Powered Q&A

Automatically process transcripts using an AI QA processor

Store questions and answers

Allow users to add feedback on Q&A output


🔹 Video Debugging Tools

Includes a dedicated debug page showing:

Video file health

File size

ffprobe metadata

Download status

Folder contents



---
 Technologies Used

Flask (Python)

MySQL database

yt-dlp for downloading YouTube videos

ffmpeg / ffprobe for validation and processing

Background threading for concurrent downloads

MoviePy for media processing

Pluggable AI processor for Q&A



---

 Project Structure

The project follows a modular structure that separates:

Application routes

Downloading and media processing

Database logic

AI QA processor

Templates and static files



---

 How It Works

1. User submits a YouTube link


2. The system fetches metadata (title + description)


3. A background thread begins downloading the video


4. Once downloaded, validation checks ensure the file is healthy


5. Audio is extracted from the video


6. The audio is transcribed


7. Q&A is generated from the transcript


8. Results are stored and viewable through the dashboard




---

 User Workflow

Normal User:

Signup → Login

Add YouTube link

Wait for processing

View transcript and QA

Provide feedback


Admin:

View all users’ videos

Inspect debug information

Manage overall system



---
 Debugging Tools

The debug section allows you to:

Inspect the processed video

Verify whether video/audio/transcript exists

Inspect technical metadata

Validate ffprobe results


This helps identify broken streams or invalid downloads.


---

 app uses background threads, so downloads do not block user actions

Video folders are separated per video for clean organization

Repair attempts only happen when necessary to avoid corruption
