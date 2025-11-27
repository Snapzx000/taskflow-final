from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime
import uuid

db = SQLAlchemy()

# ตารางกลางสำหรับเก็บว่า ใครอยู่กลุ่มไหน (Many-to-Many)
workspace_members = db.Table('workspace_members',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('workspace_id', db.Integer, db.ForeignKey('workspace.id'), primary_key=True),
    db.Column('role', db.String(50), default='member') # role ในกลุ่ม: admin, member
)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    
    # ความสัมพันธ์: User อยู่ได้หลาย Workspace
    workspaces = db.relationship('Workspace', secondary=workspace_members, backref=db.backref('members', lazy='dynamic'))

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

class Workspace(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    invite_code = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4())) # Code สำหรับสร้าง Link
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # งานทั้งหมดในกลุ่มนี้
    tasks = db.relationship('Task', backref='workspace', cascade="all, delete-orphan")

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    deadline = db.Column(db.DateTime, nullable=False)
    priority = db.Column(db.String(50), default='medium')
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    workspace_id = db.Column(db.Integer, db.ForeignKey('workspace.id'), nullable=False)
    reminder_sent = db.Column(db.Boolean, default=False)   # เตือนใกล้ถึงกำหนดไปรึยัง?
    overdue_notified = db.Column(db.Boolean, default=False) # เตือนเลยกำหนดไปรึยัง?