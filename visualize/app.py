import os
import sqlite3
import json
import google.generativeai as genai
from flask import Flask, render_template
from io import BytesIO
import base64
import matplotlib.pyplot as plt
from collections import defaultdict

app = Flask(__name__)
app.config['DATABASE'] = 'quizzes.db'

# Get Gemini API key from environment
api_key = os.environ.get('GEMINI_API_KEY')
if not api_key:
    raise ValueError("Missing GEMINI_API_KEY environment variable")
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.0-flash')

def init_db():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.execute('''
        CREATE TABLE IF NOT EXISTS quiz_result (
            id INTEGER PRIMARY KEY,
            topic TEXT CHECK(topic IN ('Data Science', 'Data Analysis', 'Data Engineering')),
            score INTEGER,
            total_questions INTEGER,
            results TEXT
        )
    ''')
    conn.commit()
    conn.close()

def analyze_with_gemini(data):
    prompt = f"""
    Analyze these quiz results and provide:
    - 2 key strengths
    - 3 weaknesses
    - 2 actionable recommendations
    Use concise bullet points
    
    Data: {json.dumps(data, default=str)}
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI analysis failed: {str(e)}"

def get_analysis():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    data = conn.execute('SELECT * FROM quiz_result').fetchall()
    conn.close()

    analysis = {
        'attempts': [],
        'domains': defaultdict(lambda: {'correct': 0, 'total': 0}),
        'weaknesses': defaultdict(int)
    }

    for idx, row in enumerate(data):
        try:
            # Track attempts
            analysis['attempts'].append({
                'number': idx + 1,
                'accuracy': row['score'] / row['total_questions']
            })
            
            # Track domain stats
            analysis['domains'][row['topic']]['correct'] += row['score']
            analysis['domains'][row['topic']]['total'] += row['total_questions']
            
            # Track weaknesses
            results = json.loads(row['results'])
            for res in results:
                if not res['correct']:
                    subtopic = res.get('subtopic', 'General').strip()
                    analysis['weaknesses'][subtopic] += 1
        except:
            continue

    return analysis

def create_progress_plot(attempts):
    plt.figure(figsize=(10, 4))
    plt.plot([a['number'] for a in attempts], 
             [a['accuracy']*100 for a in attempts], 
             marker='o', color='#1f77b4')
    plt.title('Performance Progress')
    plt.xlabel('Attempt Number')
    plt.ylabel('Accuracy (%)')
    plt.ylim(0, 105)
    plt.grid(True, alpha=0.3)
    
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    plt.close()
    return base64.b64encode(buf.getvalue()).decode()

@app.route('/')
def dashboard():
    analysis = get_analysis()
    
    # Process domain data
    domains = {}
    for domain, stats in analysis['domains'].items():
        if stats['total'] > 0:
            accuracy = stats['correct'] / stats['total']
            domains[domain] = {
                'accuracy': f"{accuracy:.1%}",
                'class': 'success' if accuracy >= 0.75 else 'warning' if accuracy >= 0.6 else 'danger'
            }
    
    # Generate visualizations
    plot_url = create_progress_plot(analysis['attempts']) if analysis['attempts'] else None
    
    # Get AI analysis
    gemini_analysis = analyze_with_gemini({
        'domains': domains,
        'weaknesses': dict(analysis['weaknesses'])
    })

    return render_template('dashboard.html',
                         plot_url=plot_url,
                         domains=domains,
                         analysis=gemini_analysis)

def generate_sample_data():
    """Helper to create test data"""
    conn = sqlite3.connect(app.config['DATABASE'])
    sample = {
        "topic": "Data Analysis",
        "score": 5,
        "total_questions": 10,
        "results": json.dumps([
            {"question": "Pandas merge", "correct": True, "subtopic": "Data Manipulation"},
            {"question": "SQL window functions", "correct": False, "subtopic": "Advanced SQL"}
        ])
    }
    conn.execute('INSERT INTO quiz_result (topic, score, total_questions, results) VALUES (?,?,?,?)',
                (sample['topic'], sample['score'], sample['total_questions'], sample['results']))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    # generate_sample_data()  # Uncomment to create sample data
    app.run(debug=True)