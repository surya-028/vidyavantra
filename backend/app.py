from flask import Flask, request, jsonify, session, render_template
import requests
from models import db, User, Course, UserCourse, Activity, UserSaved, SupportRequest, Resume, LearningSession, Schedule
from database import init_db
import json
from datetime import datetime, timedelta, timezone
from flask_cors import CORS
import random
import string
import smtplib
from email.mime.text import MIMEText
import os
import logging
from freecodecamp_learning_paths import fetch_freecodecamp_learning_paths
from flask_caching import Cache

#--- Flask App Setup ---
logging.basicConfig(level=logging.INFO)
app = Flask(__name__, instance_relative_config=True)
CORS(app, supports_credentials=True)

# Load instance config if present
app.config.from_pyfile('config.py', silent=True)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///vidyavantra.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a_very_secret_key_for_dev')
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False

init_db(app)
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 300})

FCCC_CHANNEL_ID = 'UC8butISFwT-Wl7EV0hUK0BQ'

def generate_otp(length=6):
    return ''.join(random.choices(string.digits, k=length))

def send_otp_email(to_email, otp):
    smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ.get('SMTP_USER')
    smtp_password = os.environ.get('SMTP_PASSWORD')
    from_email = smtp_user
    subject = 'Your OTP for Password Reset'
    body = f'Your OTP for password reset is: {otp}'
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = to_email
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, [to_email], msg.as_string())
        logging.info(f"OTP sent to {to_email}")
    except Exception as e:
        logging.error(f"Failed to send OTP: {e}")

def send_support_email_to_admin(name, user_email, message):
    """Send support request email to admin"""
    admin_email = "vidyavantra@gmail.com"
    smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ.get('SMTP_USER')
    smtp_password = os.environ.get('SMTP_PASSWORD')

    subject = f'New Support Request from {name}'
    body = f"""
New support request received on Vidyavantra Learning Platform:

Name: {name}
Email: {user_email}
Message: {message}

Please respond to the user at: {user_email}

Best regards,
Vidyavantra Support System
    """
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = smtp_user
    msg['To'] = admin_email
    msg['Reply-To'] = user_email
    
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, [admin_email], msg.as_string())
        logging.info(f"Support email sent to admin from {name} <{user_email}>")
    except Exception as e:
        logging.error(f"Failed to send support email to admin: {e}")

def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'message': 'Unauthorized: Login required'}), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def add_activity(user_id, activity_type, description):
    new_activity = Activity(user_id=user_id, activity_type=activity_type, description=description)
    db.session.add(new_activity)
    db.session.commit()

#---------- Pages ----------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register')
def register():
    return render_template('register.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/news')
def news():
    return render_template('news.html')

@app.route('/tutorial')
def tutorial():
    return render_template('tutorial.html')

@app.route('/chatbot')
def chatbot():
    return render_template('chatbot.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/reset', methods=['GET'])
def reset_page():
    return render_template('reset.html')

#---------- Auth / Profile ----------
@app.route('/api/register', methods=['POST'])
def register_api():
    if request.is_json:
        data = request.get_json()
        first_name = data.get('firstName'); last_name = data.get('lastName')
        email = data.get('email'); phone = data.get('phone')
        password = data.get('password')
        profession = data.get('profession'); experience = data.get('experience')
        skills = data.get('skills'); location = data.get('location')
    else:
        first_name = request.form.get('firstName'); last_name = request.form.get('lastName')
        email = request.form.get('email'); phone = request.form.get('phone')
        password = request.form.get('password')
        profession = request.form.get('profession'); experience = request.form.get('experience')
        skills = request.form.get('skills'); location = request.form.get('location')

    if not all([first_name, last_name, email, password]):
        return jsonify({'message': 'Missing required fields'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'message': 'Email already exists'}), 409

    new_user = User(
        first_name=first_name, last_name=last_name, email=email, phone=phone,
        profession=profession, experience=experience, skills=skills, location=location
    )
    new_user.set_password(password)
    try:
        db.session.add(new_user); db.session.commit(); db.session.refresh(new_user)
        add_activity(new_user.id, 'registered', 'Account created successfully.')
        return jsonify({'message': 'Registration successful', 'user': new_user.to_dict()}), 201
    except Exception as e:
        db.session.rollback(); logging.error(f"Registration error: {str(e)}")
        return jsonify({'message': 'Registration failed', 'error': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get('email'); password = data.get('password')
    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password):
        session['user_id'] = user.id
        session.permanent = True
        app.permanent_session_lifetime = timedelta(days=7)
        return jsonify({'message': 'Login successful', 'user': user.to_dict()}), 200
    return jsonify({'message': 'Invalid email or password'}), 401

@app.route('/api/logout', methods=['POST'])
@login_required
def logout():
    session.pop('user_id', None)
    return jsonify({'message': 'Logged out successfully'}), 200

@app.route('/api/user', methods=['GET'])
@login_required
def get_user_profile():
    user = User.query.get(session['user_id'])
    return (jsonify(user.to_dict()), 200) if user else (jsonify({'message': 'User not found'}), 404)

#---------- OTP / Reset ----------
@app.route('/api/send_otp', methods=['POST'])
def api_send_otp():
    data = request.get_json() or request.form
    email = data.get('email'); phone = data.get('phone')
    user = User.query.filter_by(email=email).first() if email else User.query.filter_by(phone=phone).first() if phone else None
    if not user:
        return jsonify({'message': 'User not found'}), 404
    try:
        otp = generate_otp()
        user.otp = otp
        user.otp_expiry = datetime.now(timezone.utc) + timedelta(minutes=10)
        db.session.commit()
        if email:
            send_otp_email(email, otp)
        return jsonify({'message': 'OTP sent'}), 200
    except Exception as e:
        logging.exception('Error sending OTP: %s', e)
        return jsonify({'message': f'Failed to send OTP: {str(e)}'}), 500

@app.route('/api/verify_otp', methods=['POST'])
def api_verify_otp():
    data = request.get_json() or request.form
    email = data.get('email'); phone = data.get('phone'); otp = data.get('otp')
    user = User.query.filter_by(email=email).first() if email else User.query.filter_by(phone=phone).first() if phone else None
    if not user or not otp:
        return jsonify({'message': 'Invalid request'}), 400
    # Fix timezone comparison: compare aware datetimes
    if user.otp == otp and user.otp_expiry and user.otp_expiry > datetime.now(timezone.utc):
        return jsonify({'message': 'OTP verified'}), 200
    return jsonify({'message': 'Invalid or expired OTP'}), 400

@app.route('/api/reset_password', methods=['POST'])
def api_reset_password():
    data = request.get_json() or request.form
    email = data.get('email'); phone = data.get('phone')
    otp = data.get('otp'); new_password = data.get('new_password')
    user = User.query.filter_by(email=email).first() if email else User.query.filter_by(phone=phone).first() if phone else None
    if not user or not otp or not new_password:
        return jsonify({'message': 'Invalid request'}), 400
    if user.otp == otp and user.otp_expiry and user.otp_expiry > datetime.now(timezone.utc):
        user.set_password(new_password); user.otp = None; user.otp_expiry = None; db.session.commit()
        return jsonify({'message': 'Password reset successful'}), 200
    return jsonify({'message': 'Invalid or expired OTP'}), 400

#---------- Dashboard / Stats ----------
@app.route('/api/dashboard/stats', methods=['GET'])
@login_required
def get_dashboard_stats():
    user_id = session['user_id']
    enrolled_courses_count = UserCourse.query.filter_by(user_id=user_id).count()
    user_courses = UserCourse.query.filter_by(user_id=user_id).all()
    total_progress_sum = sum(uc.progress_percentage for uc in user_courses)
    overall_progress = (total_progress_sum / len(user_courses)) if user_courses else 0
    certificates_earned = UserCourse.query.filter_by(user_id=user_id, completed=True).count()
    # Compute learning hours from LearningSession (last 30 days)
    now = datetime.utcnow(); since = now - timedelta(days=30)
    sessions = LearningSession.query.filter(
        LearningSession.user_id == user_id,
        LearningSession.started_at >= since
    ).all()
    total_seconds = sum(s.seconds for s in sessions)
    learning_hours = round(total_seconds / 3600, 1)
    try:
        saved_count = UserSaved.query.filter_by(user_id=user_id).count()
    except Exception:
        saved_count = 0
    return jsonify({
        'enrolled_courses': enrolled_courses_count,
        'overall_progress': round(overall_progress),
        'certificates_earned': certificates_earned,
        'saved_items': saved_count,
        'learning_hours': learning_hours
    }), 200

@app.route('/api/dashboard/continue_learning', methods=['GET'])
@login_required
def get_continue_learning_courses():
    user_id = session['user_id']
    try:
        limit = int(request.args.get('limit', 4))
    except ValueError:
        limit = 4
    user_courses = UserCourse.query.filter_by(user_id=user_id, completed=False)\
        .order_by(UserCourse.last_accessed.desc()).limit(limit).all()
    courses_data = []
    for uc in user_courses:
        course = Course.query.get(uc.course_id)
        if course:
            courses_data.append({
                'id': course.id,
                'title': course.title,
                'thumbnail': course.thumbnail,
                'current_module': uc.current_module,
                'user_course_id': uc.id,
                'total_modules': course.total_modules,
                'progress_percentage': uc.progress_percentage,
                'remaining_hours': round((course.total_hours / 60) * (1 - uc.progress_percentage / 100))
            })
    return jsonify(courses_data), 200

@app.route('/api/dashboard/activity_feed', methods=['GET'])
@login_required
def get_activity_feed():
    activities = Activity.query.filter_by(user_id=session['user_id']).order_by(Activity.timestamp.desc()).limit(5).all()
    return jsonify([a.to_dict() for a in activities]), 200

@app.route('/api/dashboard/activity', methods=['POST'])
@login_required
def post_activity():
    data = request.get_json() or {}
    activity_type = data.get('type') or data.get('activity_type') or 'note'
    description = data.get('description') or data.get('desc') or ''
    if not description:
        return jsonify({'message': 'Description is required'}), 400
    try:
        add_activity(session['user_id'], activity_type, description)
        return jsonify({'message': 'Activity recorded'}), 201
    except Exception as e:
        logging.exception('Failed to record activity: %s', e)
        return jsonify({'message': 'Failed to record activity', 'error': str(e)}), 500
#---------- Real-time News ----------
@app.route('/api/news', methods=['GET'])
def get_news():
    api_key = "9927cdd9c82ea677f699f5e33bf65cd1"
    url = f"http://api.mediastack.com/v1/news?access_key={api_key}&countries=in&languages=en&limit=10"
    try:
        resp = requests.get(url)
        data = resp.json()
        if 'data' in data:
            return jsonify({'articles': data['data']})
        else:
            return jsonify({'message': 'Failed to fetch news', 'error': data}), 500
    except Exception as e:
        return jsonify({'message': 'Error fetching news', 'error': str(e)}), 500

#---------- Jobs (Adzuna) ----------
@app.route('/api/jobs', methods=['GET'])
def get_jobs():
    app_id = "1b7a9173"
    app_key = "342bc28df2b60642e31cb079a0eeb2e7"
    what = request.args.get('what', 'developer')
    where = request.args.get('where', 'India')
    page = int(request.args.get('page', 1))
    results_per_page = int(request.args.get('results_per_page', 50))
    url = f"https://api.adzuna.com/v1/api/jobs/in/search/{page}?app_id={app_id}&app_key={app_key}&results_per_page={results_per_page}&what={what}&where={where}"
    try:
        resp = requests.get(url)
        data = resp.json()
        if 'results' in data:
            return jsonify({'jobs': data['results'], 'count': data.get('count', 0), 'page': page, 'results_per_page': results_per_page}), 200
        else:
            return jsonify({'message': 'Failed to fetch jobs', 'error': data}), 500
    except Exception as e:
        return jsonify({'message': 'Error fetching jobs', 'error': str(e)}), 500

#---------- Saves ----------
@app.route('/api/user/saves', methods=['GET'])
@login_required
def list_user_saves():
    user_id = session['user_id']
    resource_type = request.args.get('resource_type')
    q = UserSaved.query.filter_by(user_id=user_id)
    if resource_type:
        q = q.filter_by(resource_type=resource_type)
    saves = q.order_by(UserSaved.created_at.desc()).all()
    return jsonify([s.to_dict() for s in saves]), 200

@app.route('/api/user/saves/grouped', methods=['GET'])
@login_required
def saves_grouped():
    user_id = session['user_id']
    rows = UserSaved.query.filter_by(user_id=user_id).order_by(UserSaved.created_at.desc()).all()
    grouped = {}
    for r in rows:
        grouped.setdefault(r.resource_type, []).append(r.to_dict())
    return jsonify(grouped), 200

@app.route('/api/user/saves', methods=['POST'])
@login_required
def create_user_save():
    data = request.get_json() or {}
    resource_type = data.get('resource_type'); title = data.get('title')
    if not resource_type or not title:
        return jsonify({'message': 'resource_type and title are required'}), 400
    saved = UserSaved(
        user_id=session['user_id'],
        resource_type=resource_type,
        title=title,
        description=data.get('description'),
        thumbnail=data.get('thumbnail'),
        external_link=data.get('external_link'),
        metadata_json=(json.dumps(data.get('metadata')) if data.get('metadata') else None)
    )
    try:
        db.session.add(saved); db.session.commit()
        add_activity(session['user_id'], 'started', f'Saved {resource_type}: "{title}"')
        return jsonify({'message': 'Saved', 'saved': saved.to_dict()}), 201
    except Exception as e:
        db.session.rollback(); logging.exception('Failed to save user resource: %s', e)
        return jsonify({'message': 'Failed to save', 'error': str(e)}), 500

@app.route('/api/user/saves/<int:saved_id>', methods=['DELETE'])
@login_required
def delete_user_save(saved_id):
    s = UserSaved.query.filter_by(id=saved_id, user_id=session['user_id']).first()
    if not s:
        return jsonify({'message': 'Not found'}), 404
    try:
        db.session.delete(s); db.session.commit()
        add_activity(session['user_id'], 'note', f'Deleted saved item: "{s.title}"')
        return jsonify({'message': 'Deleted'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Failed to delete', 'error': str(e)}), 500

#---------- Courses ----------
@app.route('/api/add-sample-courses', methods=['POST'])
def add_sample_courses():
    samples = [
        Course(title='Python Data Science Masterclass', description='Master data analysis, visualization, and machine learning with Python. Work with pandas, matplotlib, and scikit-learn.', thumbnail='', total_modules=12, total_hours=375),
        Course(title='UI/UX Design Fundamentals', description='Learn design principles, user research, wireframing, and prototyping. Create stunning user interfaces with Figma.', thumbnail='', total_modules=8, total_hours=225),
        Course(title='Advanced JavaScript Concepts', description='Deep dive into closures, prototypes, async programming, and modern ES6+ features. Perfect for experienced developers.', thumbnail='', total_modules=10, total_hours=320),
        Course(title='Digital Marketing Strategy', description='Build comprehensive marketing campaigns across social media, email, and content marketing. Measure ROI and optimize performance.', thumbnail='', total_modules=7, total_hours=250),
        Course(title='Mobile App Development with Flutter', description='Create beautiful cross-platform mobile apps with Flutter and Dart. Deploy to both iOS and Android app stores.', thumbnail='', total_modules=9, total_hours=450),
    ]
    db.session.bulk_save_objects(samples)
    db.session.commit()
    return jsonify({'message': 'Sample courses added!', 'count': len(samples)}), 201

@app.route('/api/courses', methods=['GET'])
@login_required
def get_all_courses():
    courses = Course.query.all()
    return jsonify([course.to_dict() for course in courses]), 200

@app.route('/api/user/my_courses', methods=['GET'])
@login_required
def my_courses():
    ucs = UserCourse.query.filter_by(user_id=session['user_id']).order_by(UserCourse.last_accessed.desc()).all()
    return jsonify([uc.to_dict() for uc in ucs]), 200

@app.route('/api/courses/<int:course_id>/enroll', methods=['POST'])
@login_required
def enroll_course(course_id):
    user_id = session['user_id']
    course = Course.query.get(course_id)
    if not course:
        return jsonify({'message': 'Course not found'}), 404
    existing = UserCourse.query.filter_by(user_id=user_id, course_id=course_id).first()
    if existing:
        return jsonify({'message': 'Already enrolled in this course'}), 409
    new_uc = UserCourse(user_id=user_id, course_id=course_id, current_module=1, progress_percentage=0)
    db.session.add(new_uc); db.session.commit()
    add_activity(user_id, 'started', f'Started "{course.title}" course.')
    return jsonify({'message': 'Enrolled successfully', 'user_course': new_uc.to_dict()}), 201

@app.route('/api/user_courses/<int:user_course_id>/progress', methods=['PUT'])
@login_required
def update_course_progress(user_course_id):
    user_course = UserCourse.query.filter_by(id=user_course_id, user_id=session['user_id']).first()
    if not user_course:
        return jsonify({'message': 'User course not found or unauthorized'}), 404
    data = request.get_json() or {}
    if 'progress_percentage' in data:
        user_course.progress_percentage = data['progress_percentage']
    if 'current_module' in data:
        user_course.current_module = data['current_module']
    user_course.completed = bool(data.get('completed', False))
    user_course.last_accessed = datetime.utcnow()
    try:
        db.session.commit()
        if user_course.completed:
            add_activity(session['user_id'], 'completed', f'Completed "{user_course.course.title}" course.')
        return jsonify({'message': 'Progress updated successfully', 'user_course': user_course.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Failed to update progress', 'error': str(e)}), 500

@app.route('/api/save_course', methods=['POST'])
@login_required
def save_course():
    data = request.get_json() or {}
    title = data.get('title')
    if not title:
        return jsonify({'message': 'title is required'}), 400
    description = data.get('description', ''); thumbnail = data.get('thumbnail', '')
    course = Course.query.filter_by(title=title).first()
    if not course:
        course = Course(title=title, description=description, thumbnail=thumbnail, total_modules=1, total_hours=0)
        db.session.add(course); db.session.commit()
    existing = UserCourse.query.filter_by(user_id=session['user_id'], course_id=course.id).first()
    if existing:
        return jsonify({'message': 'Already saved', 'user_course': existing.to_dict()}), 200
    new_uc = UserCourse(user_id=session['user_id'], course_id=course.id, current_module=1, progress_percentage=0, last_accessed=datetime.utcnow())
    db.session.add(new_uc); db.session.commit()
    add_activity(session['user_id'], 'started', f'Saved "{course.title}" to My Courses')
    return jsonify({'message': 'Course saved', 'user_course': new_uc.to_dict()}), 201

#---------- Learning Time Tracking ----------
@app.route('/api/track/start', methods=['POST'])
@login_required
def track_start():
    data = request.get_json() or {}
    resource_type = data.get('resource_type')
    if not resource_type:
        return jsonify({'message': 'resource_type is required'}), 400
    sess = LearningSession(
        user_id=session['user_id'],
        resource_type=resource_type,
        resource_id=data.get('resource_id'),
        title=data.get('title'),
        started_at=datetime.utcnow()
    )
    db.session.add(sess); db.session.commit()
    return jsonify({'session_id': sess.id}), 201

@app.route('/api/track/stop', methods=['POST'])
@login_required
def track_stop():
    data = request.get_json() or {}
    sid = data.get('session_id')
    if not sid:
        return jsonify({'message': 'session_id is required'}), 400
    sess = LearningSession.query.filter_by(id=sid, user_id=session['user_id']).first()
    if not sess:
        return jsonify({'message': 'Session not found'}), 404
    if sess.ended_at:
        return jsonify({'message': 'Session already stopped', 'seconds': sess.seconds}), 200
    now = datetime.utcnow()
    sess.ended_at = now
    delta = (now - sess.started_at).total_seconds()
    if delta > 0:
        sess.seconds += int(delta)
    db.session.commit()
    add_activity(session['user_id'], 'note', f'Logged {sess.seconds} seconds on {sess.resource_type}: {sess.title or sess.resource_id or ""}'.strip())
    return jsonify({'message': 'Stopped', 'seconds': sess.seconds}), 200

@app.route('/api/progress/summary', methods=['GET'])
@login_required
def progress_summary():
    user_id = session['user_id']
    now = datetime.utcnow(); since = now - timedelta(days=7)
    sessions = LearningSession.query.filter(
        LearningSession.user_id == user_id,
        LearningSession.started_at >= since
    ).all()
    total_seconds = sum(s.seconds for s in sessions)
    by_type = {}
    for s in sessions:
        by_type[s.resource_type] = by_type.get(s.resource_type, 0) + s.seconds
    series = {}
    for s in sessions:
        day = s.started_at.date().isoformat()
        series[day] = series.get(day, 0) + s.seconds
    days = []
    for i in range(6, -1, -1):
        d = (now - timedelta(days=i)).date().isoformat()
        days.append({'day': d, 'seconds': series.get(d, 0)})
    return jsonify({'total_seconds_7d': total_seconds, 'by_type_7d': by_type, 'daily_7d': days}), 200

#---------- Schedules ----------
def parse_iso(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00'))

@app.route('/api/schedules', methods=['GET'])
@login_required
def list_schedules():
    rows = Schedule.query.filter_by(user_id=session['user_id']).order_by(Schedule.start_at.asc()).all()
    return jsonify([r.to_dict() for r in rows]), 200

@app.route('/api/schedules', methods=['POST'])
@login_required
def create_schedule():
    data = request.get_json() or {}
    title = data.get('title'); start_at = data.get('start_at'); end_at = data.get('end_at')
    if not title or not start_at or not end_at:
        return jsonify({'message': 'title, start_at, end_at required'}), 400
    row = Schedule(
        user_id=session['user_id'],
        title=title,
        notes=data.get('notes'),
        start_at=parse_iso(start_at),
        end_at=parse_iso(end_at),
        timezone=data.get('timezone')
    )
    db.session.add(row); db.session.commit()
    add_activity(session['user_id'], 'note', f'Created schedule: {title}')
    return jsonify({'message': 'Created', 'schedule': row.to_dict()}), 201

@app.route('/api/schedules/<int:schedule_id>', methods=['PUT'])
@login_required
def update_schedule(schedule_id):
    row = Schedule.query.filter_by(id=schedule_id, user_id=session['user_id']).first()
    if not row:
        return jsonify({'message': 'Not found'}), 404
    data = request.get_json() or {}
    if 'title' in data:
        row.title = data['title']
    if 'notes' in data:
        row.notes = data['notes']
    if 'timezone' in data:
        row.timezone = data['timezone']
    if 'start_at' in data:
        row.start_at = parse_iso(data['start_at'])
    if 'end_at' in data:
        row.end_at = parse_iso(data['end_at'])
    db.session.commit()
    return jsonify({'message': 'Updated', 'schedule': row.to_dict()}), 200

@app.route('/api/schedules/<int:schedule_id>', methods=['DELETE'])
@login_required
def delete_schedule(schedule_id):
    row = Schedule.query.filter_by(id=schedule_id, user_id=session['user_id']).first()
    if not row:
        return jsonify({'message': 'Not found'}), 404
    db.session.delete(row); db.session.commit()
    return jsonify({'message': 'Deleted'}), 200

#---------- Support ----------
@app.route('/api/support_request', methods=['POST'])
def support_request():
    data = request.get_json() or {}
    name = data.get('name'); email = data.get('email'); message = data.get('message')
    if not message or not email:
        return jsonify({'message': 'email and message are required'}), 400
    try:
        logging.info(f"Support request from {name or 'anonymous'} <{email}>: {message}")
        uid = session.get('user_id')
        sr = SupportRequest(user_id=uid, name=name, email=email, message=message)
        db.session.add(sr); db.session.commit()
        if uid:
            add_activity(uid, 'support', f'Submitted support request: {message[:120]}')
        
        # Send email to admin
        send_support_email_to_admin(name or 'Anonymous', email, message)
        
        return jsonify({'message': 'Support request received. Our team will contact you soon.'}), 201
    except Exception as e:
        logging.exception('Failed to accept support request: %s', e)
        return jsonify({'message': 'Failed to submit support request', 'error': str(e)}), 500

@app.route('/api/support_requests', methods=['GET'])
@login_required
def my_support_requests():
    rows = SupportRequest.query.filter_by(user_id=session['user_id']).order_by(SupportRequest.created_at.desc()).all()
    return jsonify([r.to_dict() for r in rows]), 200

#---------- Tutorials (YouTube) ----------
@app.route('/api/tutorials', methods=['GET'])
@cache.cached(timeout=300, query_string=True)
def get_youtube_tutorials():
    api_key = os.environ.get('YT_API_KEY') or app.config.get('YT_API_KEY')
    if not api_key:
        return jsonify({'message': 'YouTube API key missing. Set YT_API_KEY env var or add it to instance/config.py.'}), 500
    category = (request.args.get('category') or '').strip()
    try:
        max_results = int(request.args.get('limit', 24))
        max_results = max(1, min(max_results, 50))
    except ValueError:
        max_results = 24
    channel_id = request.args.get('channelId', FCCC_CHANNEL_ID)
    try:
        url = 'https://www.googleapis.com/youtube/v3/search'
        params = {
            'key': api_key,
            'channelId': channel_id,
            'part': 'snippet',
            'order': 'date',
            'maxResults': max_results,
            'type': 'video',
            'q': category
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        tutorials = []
        for item in data.get('items', []):
            sn = item.get('snippet', {}) or {}
            vid = (item.get('id', {}) or {}).get('videoId', '')
            tutorials.append({
                'id': vid,
                'title': sn['title'],
                'description': sn['description'],
                'category': category or 'YouTube',
                'level': 'all',
                'duration': '',
                'rating': '',
                'students': '',
                'instructor': sn.get('channelTitle', ''),
                'thumbnail': (sn.get('thumbnails', {}) or {}).get('high', {}).get('url', ''),
                'progress': 0,
                'tags': [],
                'isNew': False,
                'isFeatured': False,
                'videoId': vid
            })
        return jsonify({'tutorials': tutorials}), 200
    except Exception as e:
        logging.exception('Error fetching tutorials: %s', e)
        return jsonify({'message': 'Error fetching tutorials', 'error': str(e)}), 500
#---------- Learning Paths ----------
@app.route('/api/learning-paths', methods=['GET'])
@cache.cached(timeout=21600, query_string=True)
def get_learning_paths():
    category = (request.args.get('category') or '').strip()
    try:
        max_playlists = int(request.args.get('max_playlists', 4))
        items_per_playlist = int(request.args.get('items_per_playlist', 12))
    except ValueError:
        max_playlists, items_per_playlist = 4, 12
    try:
        rapidapi_key = os.environ.get('RAPIDAPI_KEY') or app.config.get('RAPIDAPI_KEY')
        rapidapi_host = os.environ.get('RAPIDAPI_HOST') or app.config.get('RAPIDAPI_HOST')
        paths = fetch_freecodecamp_learning_paths(
            category=category or None,
            max_playlists=max_playlists,
            items_per_playlist=items_per_playlist,
            rapidapi_key=rapidapi_key,
            rapidapi_host=rapidapi_host,
            yt_api_key=(os.environ.get('YT_API_KEY') or app.config.get('YT_API_KEY'))
        )
        return jsonify({'learning_paths': paths}), 200
    except Exception as e:
        logging.exception('Error fetching learning paths: %s', e)
        return jsonify({'message': 'Error fetching learning paths', 'error': str(e)}), 500

#---------- RapidAPI test, Categories, Resume, Populate, Debug, Health ----------
@app.route('/api/rapidapi-test', methods=['GET'])
def rapidapi_test():
    rapidapi_key = os.environ.get('RAPIDAPI_KEY') or app.config.get('RAPIDAPI_KEY')
    rapidapi_host = os.environ.get('RAPIDAPI_HOST') or app.config.get('RAPIDAPI_HOST')
    category = (request.args.get('category') or '').strip()
    if not rapidapi_key or not rapidapi_host:
        return jsonify({'message': 'RapidAPI credentials missing. Set RAPIDAPI_KEY and RAPIDAPI_HOST.'}), 400
    if not category:
        return jsonify({'message': 'Provide ?category=YourInstitution (course_institution) to test.'}), 400
    url = 'https://collection-for-coursera-courses.p.rapidapi.com/rapidapi/course/get_course.php'
    params = {'page_no': 1, 'course_institution': category}
    headers = {'x-rapidapi-key': rapidapi_key, 'x-rapidapi-host': rapidapi_host}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        return (resp.text, resp.status_code, {'Content-Type': 'application/json'})
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logging.exception('RapidAPI test call failed: %s', e)
        return jsonify({'message': 'RapidAPI test failed', 'error': str(e), 'traceback': tb}), 500

@app.route('/api/categories', methods=['GET'])
def get_categories():
    try:
        categories = [
            {
                "id": 1,
                "name": "Programming",
                "description": "Learn to code and build software."
            },
            {
                "id": 2,
                "name": "Design",
                "description": "Master the art of design and creativity."
            },
            {
                "id": 3,
                "name": "Data Science",
                "description": "Analyze and interpret complex data."
            },
            {
                "id": 4,
                "name": "Marketing",
                "description": "Learn marketing strategies and techniques."
            },
            {
                "id": 5,
                "name": "Business",
                "description": "Develop business skills and knowledge."
            },
            {
                "id": 6,
                "name": "Photography",
                "description": "Capture stunning photos and videos."
            }
        ]
        return jsonify({'categories': categories}), 200
    except Exception as e:
        return jsonify({'message': 'Error fetching categories', 'error': str(e)}), 500

@app.route('/resume', methods=['GET'])
@login_required
def resume_builder():
    return render_template('resume.html')

@app.route('/api/resume', methods=['GET', 'POST'])
@login_required
def resume_api():
    user_id = session['user_id']
    if request.method == 'GET':
        resume = Resume.query.filter_by(user_id=user_id).first()
        if not resume:
            return jsonify({'resume': None}), 200
        try:
            payload = json.loads(resume.data)
        except Exception:
            payload = {}
        return jsonify({'resume': {'template': resume.template, 'data': payload}}), 200
    payload = request.get_json() or {}
    template = payload.get('template', 'modern')
    data_obj = payload.get('payload', payload)
    try:
        resume = Resume.query.filter_by(user_id=user_id).first()
        if resume:
            resume.template = template
            resume.data = json.dumps(data_obj)
        else:
            resume = Resume(user_id=user_id, template=template, data=json.dumps(data_obj))
        db.session.add(resume)
        db.session.commit()
        return jsonify({'message': 'Resume saved'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Failed to save resume', 'error': str(e)}), 500

@app.route('/api/populate_data', methods=['POST'])
def populate_data():
    with app.app_context():
        db.drop_all()
        db.create_all()
        test_user = User(
            first_name='John',
            last_name='Doe',
            email='john.doe@example.com',
            phone='123-456-7890',
            profession='Working Professional',
            experience='3-5 years',
            skills='Python,React,SQL',
            location='Bangalore, India',
            is_premium=True
        )
        test_user.set_password('password123')
        db.session.add(test_user); db.session.commit()
        course1 = Course(title='Python for Data Science', description='Learn Python for data analysis.', thumbnail='', total_modules=8, total_hours=480)
        course2 = Course(title='React Development', description='Build modern web apps with React.', thumbnail='', total_modules=6, total_hours=360)
        course3 = Course(title='UI/UX Design Fundamentals', description='Master design principles.', thumbnail='', total_modules=10, total_hours=600)
        course4 = Course(title='Digital Marketing Analytics', description='Analyze marketing campaigns.', thumbnail='', total_modules=5, total_hours=300)
        db.session.add_all([course1, course2, course3, course4]); db.session.commit()
        uc1 = UserCourse(user_id=test_user.id, course_id=course1.id, current_module=4, progress_percentage=75, last_accessed=datetime.utcnow() - timedelta(days=1))
        uc2 = UserCourse(user_id=test_user.id, course_id=course2.id, current_module=2, progress_percentage=45, last_accessed=datetime.utcnow() - timedelta(days=2))
        uc3 = UserCourse(user_id=test_user.id, course_id=course3.id, current_module=6, progress_percentage=60, last_accessed=datetime.utcnow() - timedelta(days=3))
        uc4 = UserCourse(user_id=test_user.id, course_id=course4.id, current_module=1, progress_percentage=20, last_accessed=datetime.utcnow() - timedelta(days=4))
        uc_completed = UserCourse(user_id=test_user.id, course_id=course1.id, current_module=8, progress_percentage=100, completed=True, last_accessed=datetime.utcnow() - timedelta(days=5))
        db.session.add_all([uc1, uc2, uc3, uc4, uc_completed]); db.session.commit()
        add_activity(test_user.id, 'completed', 'Completed "Data Visualization" module')
        add_activity(test_user.id, 'achievement', 'Earned "Python Basics" certificate')
        add_activity(test_user.id, 'started', 'Started "React Development" course')
        add_activity(test_user.id, 'completed', 'Completed quiz with 95% score')
        add_activity(test_user.id, 'achievement', 'Reached 100 learning hours milestone')
        return jsonify({'message': 'Database populated with sample data!'}), 200

@app.route('/api/debug/test', methods=['GET'])
def debug_test():
    return jsonify({'message': 'Backend is working!', 'timestamp': datetime.utcnow().isoformat(), 'user_count': User.query.count()}), 200

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    app.run(debug=True)
