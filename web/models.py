from .extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'user' or 'guardian'
    
    # For Guardian: ID of the user they are monitoring
    linked_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # For User: Reverse relationship to see who is monitoring them (optional, but good for data integrity)
    # linked_guardian = db.relationship('User', backref=db.backref('monitored_user', remote_side=[id]), uselist=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class LogRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # 'SOS', 'NAV', 'CONFIG', 'WARNING'
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # related user objects
    user = db.relationship('User', foreign_keys=[user_id])
    
    def to_dict(self):
        return {
            'id': self.id,
            'category': self.category,
            'message': self.message,
            'time': self.timestamp.strftime('%H:%M:%S'),
            'date': self.timestamp.strftime('%Y-%m-%d')
        }

class GuardianSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    guardian_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    sensitivity = db.Column(db.Float, default=0.3)
    dark_mode = db.Column(db.Boolean, default=False)
    
    # alarm thresholds
    battery_alarm_threshold = db.Column(db.Float, default=20.0)
    latency_alarm_threshold = db.Column(db.Float, default=200.0)
    
    guardian = db.relationship('User', foreign_keys=[guardian_id])
