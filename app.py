from flask import Flask, render_template, request, redirect, url_for, session, send_file
from flask_sqlalchemy import SQLAlchemy
from io import BytesIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///application.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    self_declaration = db.Column(db.Text)
    courses = db.relationship('Course', backref='user', cascade='all, delete-orphan')
    quizzes = db.relationship('Quiz', backref='user', cascade='all, delete-orphan')
    resumes = db.relationship('Resume', backref='user', cascade='all, delete-orphan')

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_name = db.Column(db.String(150), nullable=False)
    year_completed = db.Column(db.Integer, nullable=False)

class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question = db.Column(db.String(255), nullable=False)
    answer = db.Column(db.String(255), nullable=False)

class Resume(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(255))
    data = db.Column(db.LargeBinary)
    mimetype = db.Column(db.String(50))

with app.app_context():
    db.create_all()

@app.route('/', methods=['GET', 'POST'])
def index():
    user_id = session.get('user_id')
    user = User.query.get(user_id) if user_id else None

    if request.method == 'POST':
        if user:
            # Update existing user
            user.full_name = request.form['full_name']
            user.email = request.form['email']
            user.self_declaration = request.form['self_declaration']
        else:
            # Create new user
            user = User(
                full_name=request.form['full_name'],
                email=request.form['email'],
                self_declaration=request.form['self_declaration']
            )
            db.session.add(user)
        
        try:
            db.session.commit()
            session['user_id'] = user.id
        except Exception as e:
            db.session.rollback()
            print(f"Error: {e}")
        
        return redirect(url_for('index'))
    
    courses = Course.query.filter_by(user_id=user_id).all() if user else []
    return render_template('index.html', user=user, courses=courses)

@app.route('/courses', methods=['POST'])
def add_course():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    course = Course(
        user_id=session['user_id'],
        course_name=request.form['course_name'],
        year_completed=request.form['year_completed']
    )
    db.session.add(course)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/quiz')
def submit_quiz():
    return render_template('quiz.html')
@app.route('/upload_resume', methods=['POST'])
def upload_resume():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    file = request.files['resume']
    if file:
        resume = Resume(
            user_id=session['user_id'],
            filename=file.filename,
            data=file.read(),
            mimetype=file.mimetype
        )
        db.session.add(resume)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/download_resume/<int:resume_id>')
def download_resume(resume_id):
    resume = Resume.query.get_or_404(resume_id)
    return send_file(
        BytesIO(resume.data),
        mimetype=resume.mimetype,
        as_attachment=True,
        download_name=resume.filename
    )
@app.route('/login', methods=['POST'])
def login():
    return render_template('loginpage.html')
if __name__ == '__main__':
    app.run(debug=True)