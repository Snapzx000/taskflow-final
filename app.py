from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from flask_paginate import Pagination, get_page_args
from config import Config
from models import db, User, Task, Workspace, workspace_members
from forms import LoginForm, RegisterForm, TaskForm, SearchForm, UserManageForm, WorkspaceForm
from priority_engine import calculate_priority
from notifications import send_notification
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging
import threading

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)
mail = Mail(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ใช้ memory สำหรับ dev
limiter = Limiter(get_remote_address, app=app, storage_uri="memory://")

logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# สร้าง DB ใหม่ถ้ายังไม่มี
with app.app_context():
    db.create_all()

# --- ระบบแจ้งเตือน Real-time (กัน Spam) ---
def daily_notifications():
    with app.app_context():
        now = datetime.now()
          
        # 1. เช็คงานที่ "เลยกำหนด" (Overdue)
        # เงื่อนไข: เลยกำหนด + ยังไม่เสร็จ + ยังไม่เคยเตือนว่าเลยกำหนด (overdue_notified is False)
        overdue_tasks = Task.query.filter(
            Task.deadline < now,
            Task.status.notin_(['completed', 'trash', 'Past due']),
            Task.overdue_notified == False  # ✅ เช็คว่ายังไม่เคยเตือน
        ).all()

        for task in overdue_tasks:
            # อัปเดตสถานะ
            task.status = 'Past due'
            task.overdue_notified = True  # ✅ มาร์คว่าเตือนแล้ว (กันส่งซ้ำ)
            db.session.commit()
            
            # เตรียมส่งเมล
            ws = db.session.get(Workspace, task.workspace_id)
            subject = "URGENT: Task Past Due!"
            msg = f"Alert: Task '{task.title}' in '{ws.name}' is now PAST DUE!"
            
            # ส่งหา Assignee
            if task.assigned_to:
                user = db.session.get(User, task.assigned_to)
                if user and user.is_active: send_notification(user.email, msg, subject=subject)
            
            # ส่งหา Creator
            creator = db.session.get(User, task.created_by)
            if creator and creator.is_active and creator.id != task.assigned_to:
                 send_notification(creator.email, msg, subject=subject)

            # ส่งหาทั้งกลุ่ม (ถ้าไม่มีคนรับ)
            if not task.assigned_to:
                for member in ws.members:
                    if member.is_active: send_notification(member.email, msg, subject=subject)

        # 2. เช็คงาน "ใกล้ถึงกำหนด" (Upcoming 24 ชม.)
        # เงื่อนไข: ยังไม่ถึงเวลา + เหลือไม่ถึง 1 วัน + ยังไม่เคยเตือน (reminder_sent is False)
        upcoming_tasks = Task.query.filter(
            Task.deadline > now,
            Task.deadline <= now + timedelta(days=1),
            Task.status.in_(['pending', 'doing']),
            Task.reminder_sent == False  # ✅ เช็คว่ายังไม่เคยเตือน
        ).all()
        
        for task in upcoming_tasks:
            task.reminder_sent = True  # ✅ มาร์คว่าเตือนแล้ว (กันส่งซ้ำ)
            db.session.commit()
            
            ws = db.session.get(Workspace, task.workspace_id)
            subject = "Reminder: Task Due Soon"
            msg = f"Reminder: Task '{task.title}' is due in less than 24 hours."
            
            if task.assigned_to:
                user = db.session.get(User, task.assigned_to)
                if user and user.is_active: send_notification(user.email, msg, subject=subject)
                
                # เตือนคนสั่งงานด้วย (Optional)
                creator = db.session.get(User, task.created_by)
                if creator and creator.is_active and creator.id != task.assigned_to:
                    send_notification(creator.email, msg, subject=subject)
            else:
                for member in ws.members:
                    if member.is_active: send_notification(member.email, msg, subject=subject)

# ตั้งเวลาเช็คทุก 1 นาที
scheduler = BackgroundScheduler()
scheduler.add_job(daily_notifications, trigger=IntervalTrigger(minutes=1)) 
scheduler.start()

# --- Authentication Routes ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('workspaces'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first() or User.query.filter_by(email=form.email.data).first():
            flash('Username or email already exists')
            return redirect(url_for('register'))
        user = User(username=form.username.data, email=form.email.data, is_active=True)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Registered successfully')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('workspaces'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data) and user.is_active:
            login_user(user)
            return redirect(url_for('workspaces'))
        flash('Invalid credentials')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- Workspace System ---

@app.route('/workspaces', methods=['GET', 'POST'])
@login_required
def workspaces():
    form = WorkspaceForm()
    if form.validate_on_submit():
        ws = Workspace(name=form.name.data)
        ws.members.append(current_user)
        db.session.add(ws)
        db.session.commit()
        flash(f'Workspace "{ws.name}" created!')
        return redirect(url_for('workspaces'))
    
    user_workspaces = current_user.workspaces
    return render_template('workspaces.html', workspaces=user_workspaces, form=form)

@app.route('/join/<token>')
@login_required
def join_workspace(token):
    ws = Workspace.query.filter_by(invite_code=token).first_or_404()
    if current_user in ws.members:
        flash('You are already in this workspace.')
    else:
        ws.members.append(current_user)
        db.session.commit()
        flash(f'Joined workspace "{ws.name}" successfully!')
    return redirect(url_for('workspace_tasks', workspace_id=ws.id))

# --- Main Task Logic ---

@app.route('/workspace/<int:workspace_id>/tasks', methods=['GET', 'POST'])
@login_required
def workspace_tasks(workspace_id):
    ws = Workspace.query.get_or_404(workspace_id)
    if current_user not in ws.members:
        abort(403)
        
    form = TaskForm()
    search_form = SearchForm()
    
    # Assign options
    search_form.assigned_to.choices = [(0, 'All')] + [(u.id, u.username) for u in ws.members]
    form.assigned_to.choices = [(0, 'None')] + [(u.id, u.username) for u in ws.members]

    # Query เฉพาะงานที่ไม่ใช่ trash
    query = Task.query.filter_by(workspace_id=ws.id).filter(Task.status != 'trash')

    # Filter Logic
    if request.method == 'GET' and 'query' in request.args:
        s_query = request.args.get('query')
        s_status = request.args.get('status')
        s_priority = request.args.get('priority')
        s_assigned = request.args.get('assigned_to')
        
        if s_query:
            query = query.filter((Task.title.ilike(f'%{s_query}%')) | (Task.description.ilike(f'%{s_query}%')))
        if s_status:
            query = query.filter(Task.status == s_status)
        if s_priority:
            query = query.filter(Task.priority == s_priority)
        if s_assigned and s_assigned != '0':
            query = query.filter(Task.assigned_to == int(s_assigned))

    # Pagination
    page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
    per_page = 10
    tasks_list = query.order_by(Task.deadline.asc()).offset(offset).limit(per_page).all()
    total = query.count()
    pagination = Pagination(page=page, total=total, per_page=per_page, css_framework='bootstrap4')
    
    invite_link = url_for('join_workspace', token=ws.invite_code, _external=True)    

   # Create Task Logic (ฉบับกันตาย 100%)
    if form.validate_on_submit():
        try:
            # --- ด่านที่ 1: บันทึกเข้า Database ---
            task = Task(
                title=form.title.data,
                description=form.description.data,
                deadline=form.deadline.data,
                created_by=current_user.id,
                workspace_id=ws.id,
                assigned_to=form.assigned_to.data if form.assigned_to.data != 0 else None
            )
            # ถ้ามีฟังก์ชัน calculate_priority ให้ใช้บรรทัดนี้ ถ้าไม่มีให้ลบทิ้ง
            task.priority = calculate_priority(task.description, task.deadline) 
            
            db.session.add(task)
            db.session.commit() # ถ้าพังตรงนี้ จะเด้งไป except ตัวล่างทันที
            
            # --- ด่านที่ 2: ส่งเมล (แยก try ออกมาต่างหาก) ---
            try:
                msg = f"New task in '{ws.name}': {task.title}"
                if task.assigned_to:
                    # ใช้ db.session.get เพื่อลด warning
                    assigned_user = db.session.get(User, task.assigned_to) 
                    if assigned_user: send_notification(assigned_user.email, msg)
                    
                    if current_user.email: 
                        send_notification(current_user.email, f"Task created: {task.title} (Assigned to {assigned_user.username})")
                else:
                    for member in ws.members:
                        send_notification(member.email, msg)
            except Exception as e:
                print(f"❌ Email Failed (But Task Saved): {e}")

            flash('Task created successfully!')
            return redirect(url_for('workspace_tasks', workspace_id=ws.id))

        except Exception as e:
            # ถ้าด่าน 1 พัง (Database Error) ให้มาตรงนี้
            db.session.rollback() # ยกเลิกการบันทึก
            print(f"❌ Database Error: {e}")
            flash(f'Error creating task: {str(e)}') 
            # ไม่ต้อง redirect แต่ปล่อยให้ไหลลงไป render_template ด้านล่างเพื่อโชว์ error

    return render_template('tasks.html', form=form, search_form=search_form, tasks=tasks_list, pagination=pagination, workspace=ws, invite_link=invite_link)

# --- Actions (Edit, Status, Delete, Restore, Trash, Dashboard, Members) ---

@app.route('/task/edit/<int:task_id>', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    ws = Workspace.query.get(task.workspace_id)
    if current_user not in ws.members: abort(403)

    form = TaskForm(obj=task)
    form.assigned_to.choices = [(0, 'None')] + [(u.id, u.username) for u in ws.members]
    
    if form.validate_on_submit():
        form.populate_obj(task)
        task.assigned_to = form.assigned_to.data if form.assigned_to.data != 0 else None
        task.priority = calculate_priority(task.description, task.deadline)
        db.session.commit()
        flash('Task updated')
        return redirect(url_for('workspace_tasks', workspace_id=ws.id))
        
    return render_template('edit_task.html', form=form, task=task, workspace=ws)

@app.route('/task/status/<int:task_id>/<string:new_status>')
@login_required
def change_status(task_id, new_status):
    task = Task.query.get_or_404(task_id)
    ws = Workspace.query.get(task.workspace_id)
    if current_user not in ws.members: abort(403)
    
    task.status = new_status
    db.session.commit()
    flash(f'Task moved to {new_status}')
    return redirect(url_for('workspace_tasks', workspace_id=ws.id))

# Soft Delete (ย้ายเข้าถังขยะ)
@app.route('/task/delete/<int:task_id>')
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    ws = Workspace.query.get(task.workspace_id)
    if current_user not in ws.members: abort(403)
    
    task.status = 'trash'
    db.session.commit()
    flash('Task moved to trash')
    return redirect(url_for('workspace_tasks', workspace_id=ws.id))

# หน้าถังขยะ
@app.route('/workspace/<int:workspace_id>/trash')
@login_required
def workspace_trash(workspace_id):
    ws = Workspace.query.get_or_404(workspace_id)
    if current_user not in ws.members: abort(403)
    
    trash_tasks = Task.query.filter_by(workspace_id=ws.id, status='trash').all()
    return render_template('trash.html', workspace=ws, tasks=trash_tasks)

# กู้คืนงาน
@app.route('/task/restore/<int:task_id>')
@login_required
def restore_task(task_id):
    task = Task.query.get_or_404(task_id)
    ws = Workspace.query.get(task.workspace_id)
    if current_user not in ws.members: abort(403)
    
    task.status = 'pending'
    db.session.commit()
    flash('Task restored successfully')
    return redirect(url_for('workspace_tasks', workspace_id=ws.id))

# หน้าสมาชิก
@app.route('/workspace/<int:workspace_id>/members', methods=['GET', 'POST'])
@login_required
def workspace_members_manage(workspace_id):
    ws = Workspace.query.get_or_404(workspace_id)
    if current_user not in ws.members: abort(403)
    return render_template('members.html', workspace=ws)

# หน้า Dashboard (เฉพาะกลุ่ม)
@app.route('/workspace/<int:workspace_id>/dashboard')
@login_required
def workspace_dashboard(workspace_id):
    ws = Workspace.query.get_or_404(workspace_id)
    if current_user not in ws.members: abort(403)
    
    total_tasks = Task.query.filter_by(workspace_id=ws.id).filter(Task.status != 'trash').count()
    completed = Task.query.filter_by(workspace_id=ws.id, status='completed').count()
    pending = Task.query.filter_by(workspace_id=ws.id, status='pending').count()
    past_due = Task.query.filter_by(workspace_id=ws.id, status='Past due').count()
    doing = Task.query.filter_by(workspace_id=ws.id, status='doing').count()
    
    stats = {
        'total': total_tasks, 
        'completed': completed, 
        'pending': pending + doing, 
        'past_due': past_due
    }
    return render_template('dashboard.html', stats=stats, workspace=ws)

# Error Handlers
@app.errorhandler(403)
def forbidden(error): return render_template('403.html'), 403
@app.errorhandler(404)
def not_found(error): return render_template('404.html'), 404
@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=True)