import os
import sqlite3
import json
import google.generativeai as genai
from flask import Flask, render_template, g
from io import BytesIO
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from collections import defaultdict

app = Flask(__name__)
app.config['DATABASE'] = 'quizzes.db'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-123')

# Configure Gemini
genai.configure(api_key=os.environ['GEMINI_API_KEY'])
model = genai.GenerativeModel('gemini-1.5-flash')

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        db.execute('''
            CREATE TABLE IF NOT EXISTS quiz_result (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT CHECK(topic IN ('Data Science', 'Data Analysis', 'Data Engineering')),
                score INTEGER NOT NULL,
                total_questions INTEGER NOT NULL,
                results TEXT NOT NULL
            )
        ''')
        db.commit()

def get_quiz_data():
    db = get_db()
    results = db.execute('''
        SELECT id, topic, score, total_questions, results 
        FROM quiz_result 
        ORDER BY id
    ''').fetchall()

    analysis = {
        'attempts': [],
        'domains': defaultdict(lambda: {'correct': 0, 'total': 0}),
        'weaknesses': defaultdict(int)
    }

    for row in results:
        try:
            analysis['attempts'].append({
                'id': row['id'],
                'topic': row['topic'],
                'score': row['score'],
                'total': row['total_questions'],
                'accuracy': row['score'] / row['total_questions']
            })
            
            analysis['domains'][row['topic']]['correct'] += row['score']
            analysis['domains'][row['topic']]['total'] += row['total_questions']
            
            for q in json.loads(row['results']):
                if not q['correct']:
                    subtopic = q.get('subtopic', 'General').strip()
                    analysis['weaknesses'][subtopic] += 1
        except Exception as e:
            continue

    return analysis

def create_progress_plot(attempts):
    plt.figure(figsize=(10, 5))
    if attempts:
        plt.plot(
            [a['id'] for a in attempts], 
            [a['accuracy']*100 for a in attempts], 
            marker='o', 
            color='#1f77b4'
        )
        plt.title('Accuracy Progress')
        plt.xlabel('Attempt Number')
        plt.ylabel('Accuracy (%)')
        plt.ylim(0, 105)
        plt.grid(True, alpha=0.3)
    
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    plt.close()
    return base64.b64encode(buf.getvalue()).decode()

def analyze_with_gemini(data):
    prompt = f"""
    Analyze these quiz results and provide:
    1. 2 key technical strengths
    2. 3 specific weaknesses
    3. 2 actionable recommendations
    Use markdown bullet points
    
    Data: {json.dumps(data, indent=2)}
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except:
        return "## AI Analysis Unavailable\nPlease try again later."

@app.route('/')
def dashboard():
    data = get_quiz_data()
    
    domains = {}
    for domain, stats in data['domains'].items():
        if stats['total'] > 0:
            accuracy = stats['correct'] / stats['total']
            total_attempts = sum(1 for a in data['attempts'] if a['topic'] == domain)
            domains[domain] = {
                'accuracy': f"{accuracy:.1%}",
                'class': 'success' if accuracy >= 0.75 else 'warning' if accuracy >= 0.5 else 'danger',
                'total_attempts': total_attempts
            }
    
    weaknesses = sorted(data['weaknesses'].items(), key=lambda x: x[1], reverse=True)[:3]
    
    return render_template('dashboard.html',
                         plot_url=create_progress_plot(data['attempts']),
                         domains=domains,
                         weaknesses=weaknesses,
                         analysis=analyze_with_gemini(data))

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)