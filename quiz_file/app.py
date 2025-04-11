from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import google.generativeai as genai
import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Load environment variables
load_dotenv()

# Configure Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quizzes.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.logger.setLevel(logging.INFO)

# Initialize extensions
db = SQLAlchemy(app)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Database Model
class QuizResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topic = db.Column(db.String(200), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    results = db.Column(db.JSON, nullable=False)

# Create database tables
with app.app_context():
    db.create_all()

# Configure Gemini AI
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("Missing GEMINI_API_KEY in .env file")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Generation configuration
generation_config = genai.types.GenerationConfig(
    temperature=0.7,
    top_p=0.95,
    top_k=40,
    max_output_tokens=8192
)

def generate_quiz_prompt(topic, count=10):
    return f"""Generate {count} quiz questions about {topic} with:
- 3 question types: fill-in-blank, code-output, true/false
- Include correct answers
- Format as JSON with this structure:
{{
  "questions": [
    {{
      "type": "fill/code/tf",
      "question": "question text",
      "answer": "correct answer"
    }}
  ]
}}
Ensure valid JSON formatting and escape special characters."""

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
@limiter.limit("10 per minute")
def generate_quiz():
    try:
        topic = request.form.get('topic', '').strip()
        count = min(int(request.form.get('count', 10)), 50)
        
        if not topic:
            return jsonify({"error": "Topic is required"}), 400

        app.logger.info(f"Generating {count} questions about: {topic}")
        prompt = generate_quiz_prompt(topic, count)
        response = model.generate_content(
            prompt,
            generation_config=generation_config
        )
        
        raw_response = response.text.strip()
        cleaned_response = raw_response.replace("```json", "").replace("```", "")
        quiz_data = json.loads(cleaned_response)
        
        return jsonify(quiz_data.get('questions', []))
    
    except json.JSONDecodeError:
        app.logger.error(f"JSON parse error. Response: {raw_response}")
        return jsonify({"error": "Failed to generate valid quiz format"}), 500
    except Exception as e:
        app.logger.error(f"Error: {str(e)}", exc_info=True)
        return jsonify({"error": f"Quiz generation failed: {str(e)}"}), 500

@app.route('/save_result', methods=['POST'])
def save_result():
    try:
        data = request.json
        new_result = QuizResult(
            topic=data['topic'],
            score=data['score'],
            total_questions=data['total_questions'],
            results=data['results']
        )
        db.session.add(new_result)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/history')
def quiz_history():
    results = QuizResult.query.order_by(QuizResult.timestamp.desc()).all()
    return render_template('history.html', results=results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)