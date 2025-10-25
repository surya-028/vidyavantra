from datetime import datetime
from database import db
from werkzeug.security import generate_password_hash, check_password_hash


class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    password_hash = db.Column(db.String(128), nullable=False)
    profession = db.Column(db.String(50), nullable=True)
    experience = db.Column(db.String(50), nullable=True)
    skills = db.Column(db.String(255), nullable=True)
    location = db.Column(db.String(100), nullable=True)
    is_premium = db.Column(db.Boolean, default=False)
    otp = db.Column(db.String(10), nullable=True)
    otp_expiry = db.Column(db.DateTime, nullable=True)

    enrolled_courses = db.relationship('UserCourse', backref='user', lazy=True)
    activities = db.relationship('Activity', backref='user', lazy=True)
    resume = db.relationship('Resume', backref='user', lazy=True, uselist=False)
    sessions = db.relationship('LearningSession', backref='user', lazy=True)
    schedules = db.relationship('Schedule', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'email': self.email,
            'phone': self.phone,
            'profession': self.profession,
            'experience': self.experience,
            'skills': self.skills.split(',') if self.skills else [],
            'location': self.location,
            'is_premium': self.is_premium
        }


class Course(db.Model):
    __tablename__ = 'course'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    thumbnail = db.Column(db.String(255), nullable=True)  # store url or emoji
    total_modules = db.Column(db.Integer, default=0)
    total_hours = db.Column(db.Integer, default=0)  # in minutes

    users_enrolled = db.relationship('UserCourse', backref='course', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'thumbnail': self.thumbnail,
            'total_modules': self.total_modules,
            'total_hours': self.total_hours
        }


class UserCourse(db.Model):
    __tablename__ = 'user_course'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    current_module = db.Column(db.Integer, default=0)
    progress_percentage = db.Column(db.Integer, default=0)
    last_accessed = db.Column(db.DateTime, default=datetime.utcnow)
    completed = db.Column(db.Boolean, default=False)

    def to_dict(self):
        course = Course.query.get(self.course_id)
        return {
            'id': self.id,
            'user_id': self.user_id,
            'course_id': self.course_id,
            'course_title': course.title if course else 'Unknown Course',
            'course_thumbnail': course.thumbnail if course else '',
            'total_modules': course.total_modules if course else 0,
            'current_module': self.current_module,
            'progress_percentage': self.progress_percentage,
            'last_accessed': self.last_accessed.isoformat(),
            'completed': self.completed
        }


class Activity(db.Model):
    __tablename__ = 'activity'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    activity_type = db.Column(db.String(50), nullable=False)  # e.g., 'completed', 'started', 'achievement'
    description = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'activity_type': self.activity_type,
            'description': self.description,
            'timestamp': self.timestamp.isoformat()
        }


class Resume(db.Model):
    __tablename__ = 'resume'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    template = db.Column(db.String(50), default='modern', nullable=False)
    data = db.Column(db.Text, nullable=False)  # JSON string
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserSaved(db.Model):
    __tablename__ = 'user_saved'
    """Generic saved resource for users (tutorials, learning paths, news, jobs, resume exports etc.)"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    resource_type = db.Column(db.String(50), nullable=False)  # e.g., tutorial, learning_path, news, job, resume
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    thumbnail = db.Column(db.String(255), nullable=True)
    external_link = db.Column(db.String(1024), nullable=True)
    metadata_json = db.Column(db.Text, nullable=True)  # JSON string for provider-specific data
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'resource_type': self.resource_type,
            'title': self.title,
            'description': self.description,
            'thumbnail': self.thumbnail,
            'external_link': self.external_link,
            'metadata': self.metadata_json,
            'created_at': self.created_at.isoformat()
        }


class SupportRequest(db.Model):
    __tablename__ = 'support_request'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    name = db.Column(db.String(120), nullable=True)
    email = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'email': self.email,
            'message': self.message,
            'created_at': self.created_at.isoformat()
        }


class LearningSession(db.Model):
    __tablename__ = 'learning_session'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    resource_type = db.Column(db.String(50), nullable=False)  # 'course' | 'tutorial' | 'learning_path' | 'news' | 'job' | ...
    resource_id = db.Column(db.String(255), nullable=True)  # course_id or external id
    title = db.Column(db.String(255), nullable=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=True)
    seconds = db.Column(db.Integer, default=0, nullable=False)
    metadata_json = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'title': self.title,
            'started_at': self.started_at.isoformat(),
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'seconds': self.seconds
        }


class Schedule(db.Model):
    __tablename__ = 'schedule'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    start_at = db.Column(db.DateTime, nullable=False)
    end_at = db.Column(db.DateTime, nullable=False)
    timezone = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'notes': self.notes,
            'start_at': self.start_at.isoformat(),
            'end_at': self.end_at.isoformat(),
            'timezone': self.timezone,
            'created_at': self.created_at.isoformat()
        }