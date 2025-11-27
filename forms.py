from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, TextAreaField, DateTimeLocalField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length, Email

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=150)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Register')

# --- ฟอร์มใหม่สำหรับสร้างกลุ่ม ---
class WorkspaceForm(FlaskForm):
    name = StringField('Workspace Name', validators=[DataRequired(), Length(min=3, max=150)])
    submit = SubmitField('Create Workspace')

class TaskForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[DataRequired()])
    deadline = DateTimeLocalField('Deadline', format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    assigned_to = SelectField('Assign to', coerce=int)
    submit = SubmitField('Create/Update Task')

class SearchForm(FlaskForm):
    query = StringField('Search')
    status = SelectField('Status', choices=[('', 'All'), ('pending', 'Pending'), ('doing', 'Doing'), ('completed', 'Completed')])
    priority = SelectField('Priority', choices=[('', 'All'), ('high', 'High'), ('medium', 'Medium'), ('low', 'Low')])
    assigned_to = SelectField('Assigned to', coerce=int)
    submit = SubmitField('Filter')

class UserManageForm(FlaskForm):
    role = SelectField('Role', choices=[('member', 'Member'), ('admin', 'Admin')])
    is_active = SelectField('Active', choices=[(True, 'Yes'), (False, 'No')])
    submit = SubmitField('Update')