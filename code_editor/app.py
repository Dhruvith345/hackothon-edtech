# app.py
import os
import json
import google.generativeai as genai
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'default-secret-key')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB limit
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///kaggle_analyses.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}

# Initialize extensions
db = SQLAlchemy(app)
genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
model = genai.GenerativeModel('gemini-1.5-flash')

# Database Models
class Analysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    total_score = db.Column(db.Integer)
    raw_data = db.Column(db.Text)
    processed_data = db.Column(db.Text)

class CompetitionResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey('analysis.id'))
    title = db.Column(db.String(255))
    rank = db.Column(db.String(50))
    medal = db.Column(db.String(50))
    score = db.Column(db.Integer)

class ContributionResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey('analysis.id'))
    title = db.Column(db.String(255))
    type = db.Column(db.String(50))
    upvotes = db.Column(db.Integer)
    score = db.Column(db.Integer)

class CourseResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey('analysis.id'))
    title = db.Column(db.String(255))
    completed_at = db.Column(db.String(50))
    score = db.Column(db.Integer)

# Scoring Configuration
SCORING = {
    'medals': {'gold': 300, 'silver': 200, 'bronze': 100},
    'ranks': {'top 1%': 500, 'top 5%': 400, 'top 10%': 300},
    'upvote_multiplier': 0.5,
    'course_score': 150
}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def process_gemini_response(response_text):
    try:
        cleaned = response_text.strip().replace('```json', '').replace('```', '')
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None

def calculate_scores(data):
    total = 0
    processed = {'competitions': [], 'contributions': [], 'courses': []}

    # Process competitions
    for comp in data.get('competitions', []):
        medal_score = SCORING['medals'].get(comp.get('medal', '').lower(), 0)
        rank_score = SCORING['ranks'].get(comp.get('rank', '').lower(), 0)
        score = max(medal_score, rank_score)
        processed['competitions'].append({
            'title': comp.get('title', 'Unknown Competition'),
            'rank': comp.get('rank', 'N/A'),
            'medal': comp.get('medal'),
            'score': score
        })
        total += score

    # Process contributions
    for contrib in data.get('contributions', []):
        score = int(contrib.get('upvotes', 0) * SCORING['upvote_multiplier'])
        processed['contributions'].append({
            'title': contrib.get('title', 'Untitled Contribution'),
            'type': contrib.get('type', 'dataset'),
            'upvotes': contrib.get('upvotes', 0),
            'score': score
        })
        total += score

    # Process courses
    for course in data.get('courses', []):
        processed['courses'].append({
            'title': course.get('title', 'Unnamed Course'),
            'completed_at': course.get('completed_at', 'Unknown Date'),
            'score': SCORING['course_score']
        })
        total += SCORING['course_score']

    return total, processed

@app.route('/', methods=['GET'])
def index():
    analyses = Analysis.query.order_by(Analysis.upload_date.desc()).limit(10).all()
    return render_template('index.html', analyses=analyses)

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'file' not in request.files:
        flash('No file selected', 'danger')
        return redirect(url_for('index'))

    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('index'))

    if not allowed_file(file.filename):
        flash('Invalid file type (allowed: PNG, JPG, JPEG)', 'danger')
        return redirect(url_for('index'))

    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Get Gemini analysis
        prompt = """Analyze this Kaggle achievement image and return JSON with:
        {
            "competitions": [{"title": "...", "rank": "...", "medal": "..."}],
            "contributions": [{"title": "...", "type": "...", "upvotes": N}],
            "courses": [{"title": "...", "completed_at": "..."}]
        }"""
        response = model.generate_content([prompt, genai.upload_file(filepath)])
        
        if not response.text:
            raise ValueError("Empty response from Gemini API")

        # Process response
        raw_data = response.text
        parsed_data = process_gemini_response(raw_data)
        if not parsed_data:
            raise ValueError("Invalid response format from Gemini")

        # Calculate scores
        total_score, processed_data = calculate_scores(parsed_data)

        # Store analysis
        analysis = Analysis(
            filename=filename,
            total_score=total_score,
            raw_data=raw_data,
            processed_data=json.dumps(processed_data)
        )
        db.session.add(analysis)
        
        # Store detailed results
        for comp in processed_data['competitions']:
            db.session.add(CompetitionResult(
                analysis_id=analysis.id,
                **comp
            ))
        
        for contrib in processed_data['contributions']:
            db.session.add(ContributionResult(
                analysis_id=analysis.id,
                **contrib
            ))
        
        for course in processed_data['courses']:
            db.session.add(CourseResult(
                analysis_id=analysis.id,
                **course
            ))

        db.session.commit()
        return redirect(url_for('results', analysis_id=analysis.id))

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error: {str(e)}")
        flash(f'Analysis failed: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/results/<int:analysis_id>')
def results(analysis_id):
    analysis = Analysis.query.get_or_404(analysis_id)
    competitions = CompetitionResult.query.filter_by(analysis_id=analysis_id).all()
    contributions = ContributionResult.query.filter_by(analysis_id=analysis_id).all()
    courses = CourseResult.query.filter_by(analysis_id=analysis_id).all()
    
    return render_template('results.html',
        analysis=analysis,
        competitions=competitions,
        contributions=contributions,
        courses=courses
    )

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True)