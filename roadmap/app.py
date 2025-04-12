import os
import json
import logging
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField, validators
import google.generativeai as genai
from dotenv import load_dotenv

# Configuration
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///roadmaps.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)

# Configure Gemini
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Database Model
class Roadmap(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    skills = db.Column(db.String(500), nullable=False)
    proficiency = db.Column(db.String(50), nullable=False)
    goal = db.Column(db.String(100), nullable=False)
    generated_content = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Form Class
class AssessmentForm(FlaskForm):
    name = StringField('Your Name', [validators.DataRequired()])
    email = StringField('Email', [validators.DataRequired(), validators.Email()])
    skills = StringField('Your Skills (comma separated)', [validators.DataRequired()])
    proficiency = SelectField('Proficiency Level', choices=[
        ('beginner', '🚀 Beginner'), 
        ('intermediate', '🎯 Intermediate'),
        ('advanced', '🔥 Advanced')
    ])
    goal = SelectField('Career Goal', choices=[
        ('data_analyst', '📊 Data Analyst'),
        ('data_scientist', '🔬 Data Scientist'),
        ('data_engineer', '⚙️ Data Engineer')
    ])
    submit = SubmitField('Generate Roadmap')

# Core Functionality
def generate_gemini_roadmap(skills, proficiency, goal):
    prompt = f"""
    Create a detailed 1-year learning roadmap for a {proficiency} level professional 
    aiming to become a {goal}. Current skills: {skills}.

    Provide output in this EXACT JSON format:
    {{
        "roadmap": {{
            "Month1": {{
                "focus": "Focus Area",
                "topics": ["Topic1", "Topic2"],
                "resources": [
                    {{"name": "Resource", "url": "https://valid.url"}}
                ],
                "projects": ["Project1"]
            }},
            "Month2": {{...}},
            "Month3": {{...}}
        }},
        "certifications": ["Cert1"],
        "skill_gaps": ["Gap1"]
    }}
    Requirements:
    1. Valid URLs only
    2. 3-5 items per list
    3. Real certifications
    4. Actionable projects
    """

    try:
        response = model.generate_content(prompt)
        response_text = response.text.strip().replace('```json', '').replace('```', '')
        roadmap_data = json.loads(response_text)
        
        # Validate structure
        required_keys = ['roadmap', 'certifications', 'skill_gaps']
        if not all(key in roadmap_data for key in required_keys):
            raise ValueError("Invalid roadmap structure")
            
        return roadmap_data
        
    except Exception as e:
        logger.error(f"Generation Error: {str(e)}")
        return None

# Routes
@app.route('/', methods=['GET', 'POST'])
def home():
    form = AssessmentForm()
    if form.validate_on_submit():
        try:
            roadmap_data = generate_gemini_roadmap(
                form.skills.data,
                form.proficiency.data,
                form.goal.data
            )

            if not roadmap_data:
                flash('Roadmap generation failed. Please try again.', 'danger')
                return redirect(url_for('home'))

            new_roadmap = Roadmap(
                name=form.name.data,
                email=form.email.data,
                skills=form.skills.data,
                proficiency=form.proficiency.data,
                goal=form.goal.data,
                generated_content=roadmap_data
            )
            
            db.session.add(new_roadmap)
            db.session.commit()
            session['roadmap_id'] = new_roadmap.id
            return redirect(url_for('roadmap'))

        except Exception as e:
            db.session.rollback()
            logger.error(f"Database Error: {str(e)}")
            flash('System error occurred. Please try again.', 'danger')

    return render_template('index.html', form=form)

@app.route('/roadmap')
def roadmap():
    roadmap_id = session.get('roadmap_id')
    if not roadmap_id:
        flash('Complete the assessment first', 'warning')
        return redirect(url_for('home'))
    
    roadmap = Roadmap.query.get(roadmap_id)
    return render_template('roadmap.html', 
                         roadmap=roadmap,
                         content=roadmap.generated_content)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)