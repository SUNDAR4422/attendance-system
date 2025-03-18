from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import random
import string
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'  # Change this in production
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///attendance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)

class Class(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))

class Student(db.Model):
    register_number = db.Column(db.String(10), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=True)
    class_ = db.relationship('Class', backref='students')

class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(6), unique=True, nullable=False)
    remark = db.Column(db.String(200), nullable=True)
    attendance_active = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    register_number = db.Column(db.String(10), db.ForeignKey('student.register_number'))
    session_code = db.Column(db.String(6), db.ForeignKey('session.code'))
    date = db.Column(db.DateTime, default=datetime.utcnow)

class Absence(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    register_number = db.Column(db.String(10), db.ForeignKey('student.register_number'))
    session_code = db.Column(db.String(6), db.ForeignKey('session.code'))
    reason = db.Column(db.String(200), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)

# Create database tables and default users
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(username='admin', password=generate_password_hash('admin123'), role='admin'))
        db.session.add(User(username='professor', password=generate_password_hash('prof123'), role='professor'))
        db.session.commit()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user)
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user.role == 'professor':
                return redirect(url_for('professor_dashboard'))
        flash('Invalid credentials', 'warning')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/create_class', methods=['GET', 'POST'])
@login_required
def create_class():
    if current_user.role != 'admin':
        flash('Access denied', 'warning')
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        if Class.query.filter_by(name=name).first():
            flash('Class already exists!', 'warning')
        else:
            new_class = Class(name=name, description=description)
            db.session.add(new_class)
            db.session.commit()
            flash('Class created successfully!', 'success')
            return redirect(url_for('manage_classes'))
    return render_template('create_class.html')

@app.route('/manage_classes', methods=['GET', 'POST'])
@login_required
def manage_classes():
    if current_user.role != 'admin':
        flash('Access denied', 'warning')
        return redirect(url_for('login'))
    if request.method == 'POST' and 'delete' in request.form:
        class_id = request.form.get('class_id')
        class_ = Class.query.get(class_id)
        if class_:
            db.session.delete(class_)
            db.session.commit()
            flash('Class deleted successfully!', 'success')
        else:
            flash('Class not found!', 'warning')
    classes = Class.query.all()
    return render_template('manage_classes.html', classes=classes)

@app.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    if current_user.role != 'admin':
        flash('Access denied', 'warning')
        return redirect(url_for('login'))
    classes = Class.query.all()
    if request.method == 'POST':
        if 'file' in request.files:  # Bulk upload
            file = request.files['file']
            if file and file.filename.endswith('.csv'):
                csv_data = pd.read_csv(file)
                for _, row in csv_data.iterrows():
                    register_number = str(row['register_number'])
                    name = row['name']
                    class_name = row.get('class_name', None)
                    class_ = Class.query.filter_by(name=class_name).first() if class_name else None
                    if not Student.query.get(register_number):
                        student = Student(register_number=register_number, name=name, class_id=class_.id if class_ else None)
                        db.session.add(student)
                db.session.commit()
                flash('Students uploaded successfully!', 'success')
                return redirect(url_for('register'))
            else:
                flash('Please upload a valid CSV file!', 'warning')
        else:  # Single student registration
            register_number = request.form.get('register_number')
            name = request.form.get('name')
            class_id = request.form.get('class_id')
            if not register_number or not name:
                flash('Please provide both register number and name!', 'warning')
            elif Student.query.get(register_number):
                flash('Register number already exists!', 'warning')
            else:
                student = Student(register_number=register_number, name=name, class_id=class_id if class_id else None)
                db.session.add(student)
                db.session.commit()
                flash('Student registered successfully!', 'success')
                return redirect(url_for('register'))
    return render_template('register.html', classes=classes)

@app.route('/manage_students', methods=['GET', 'POST'])
@login_required
def manage_students():
    if current_user.role != 'admin':
        flash('Access denied', 'warning')
        return redirect(url_for('login'))
    if request.method == 'POST' and 'delete' in request.form:
        register_number = request.form.get('register_number')
        student = Student.query.get(register_number)
        if student:
            Attendance.query.filter_by(register_number=register_number).delete()
            Absence.query.filter_by(register_number=register_number).delete()
            db.session.delete(student)
            db.session.commit()
            flash('Student deleted successfully!', 'success')
        else:
            flash('Student not found!', 'warning')
    students = Student.query.all()
    return render_template('manage_students.html', students=students)

@app.route('/create_session', methods=['GET', 'POST'])
@login_required
def create_session():
    if current_user.role != 'admin':
        flash('Access denied', 'warning')
        return redirect(url_for('login'))
    if request.method == 'POST':
        remark = request.form.get('remark')
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        session = Session(code=code, remark=remark)
        db.session.add(session)
        db.session.commit()
        flash('Session created successfully!', 'success')
        return redirect(url_for('manage_sessions'))
    return render_template('create_session.html')

@app.route('/manage_sessions', methods=['GET', 'POST'])
@login_required
def manage_sessions():
    if current_user.role != 'admin':
        flash('Access denied', 'warning')
        return redirect(url_for('login'))
    if request.method == 'POST':
        if 'start_session' in request.form:
            session_id = request.form.get('session_id')
            session = Session.query.get_or_404(session_id)
            session.attendance_active = True
            db.session.commit()
            flash(f'Attendance started for session {session.code}', 'success')
        elif 'stop_session' in request.form:
            session_id = request.form.get('session_id')
            session = Session.query.get_or_404(session_id)
            session.attendance_active = False
            db.session.commit()
            flash(f'Attendance stopped for session {session.code}', 'success')
        elif 'delete_session' in request.form:
            session_id = request.form.get('session_id')
            session = Session.query.get_or_404(session_id)
            Attendance.query.filter_by(session_code=session.code).delete()
            Absence.query.filter_by(session_code=session.code).delete()
            db.session.delete(session)
            db.session.commit()
            flash(f'Session {session.code} deleted successfully!', 'success')
    sessions = Session.query.all()
    return render_template('manage_sessions.html', sessions=sessions)

@app.route('/start_attendance/<int:session_id>', methods=['POST'])
@login_required
def start_attendance(session_id):
    if current_user.role != 'admin':
        flash('Access denied', 'warning')
        return redirect(url_for('login'))
    session = Session.query.get_or_404(session_id)
    session.attendance_active = True
    db.session.commit()
    flash(f'Attendance started for session {session.code}', 'success')
    return redirect(url_for('manage_sessions'))

@app.route('/stop_attendance/<int:session_id>', methods=['POST'])
@login_required
def stop_attendance(session_id):
    if current_user.role != 'admin':
        flash('Access denied', 'warning')
        return redirect(url_for('login'))
    session = Session.query.get_or_404(session_id)
    session.attendance_active = False
    db.session.commit()
    flash(f'Attendance stopped for session {session.code}', 'success')
    return redirect(url_for('manage_sessions'))

@app.route('/attendance', methods=['GET', 'POST'])
def attendance():
    if request.method == 'POST':
        register_number = request.form.get('register_number')
        session_code = request.form.get('session_code')
        if not register_number or not session_code:
            flash('Please provide both register number and session code!', 'warning')
            return redirect(url_for('attendance'))
        session = Session.query.filter_by(code=session_code).first()
        if not session:
            flash('Invalid session code!', 'warning')
        elif not session.attendance_active:
            flash('Attendance is not active for this session!', 'warning')
        elif not Student.query.get(register_number):
            flash('Student not found!', 'warning')
        else:
            if Attendance.query.filter_by(register_number=register_number, session_code=session_code).first():
                flash('Attendance already marked for this session!', 'warning')
            else:
                attendance = Attendance(register_number=register_number, session_code=session_code)
                db.session.add(attendance)
                db.session.commit()
                flash('Attendance marked successfully!', 'success')
        return redirect(url_for('attendance'))
    active_sessions = Session.query.filter_by(attendance_active=True).all()
    return render_template('attendance.html', active_sessions=active_sessions)

@app.route('/student_dashboard')
def student_dashboard():
    register_number = request.args.get('register_number')
    if not register_number or not Student.query.get(register_number):
        flash('Please provide a valid register number', 'warning')
        return redirect(url_for('attendance'))
    student = Student.query.get(register_number)
    attendance = Attendance.query.filter_by(register_number=register_number).all()
    return render_template('student_dashboard.html', student=student, attendance=attendance)

@app.route('/student_profile/<register_number>')
@login_required
def student_profile(register_number):
    if current_user.role not in ['admin', 'professor']:
        flash('Access denied', 'warning')
        return redirect(url_for('login'))
    student = Student.query.get_or_404(register_number)
    attendance = Attendance.query.filter_by(register_number=register_number).all()
    absences = Absence.query.filter_by(register_number=register_number).all()
    total_sessions = Session.query.count()
    present_count = len(attendance)
    absent_count = len(absences)
    other_count = total_sessions - (present_count + absent_count) if total_sessions > 0 else 0
    chart_data = {'present': present_count, 'absent': absent_count, 'other': other_count}
    return render_template('student_profile.html', student=student, attendance=attendance, absences=absences, chart_data=chart_data)

@app.route('/add_absence', methods=['POST'])
@login_required
def add_absence():
    if current_user.role != 'admin':
        flash('Access denied', 'warning')
        return redirect(url_for('login'))
    register_number = request.form.get('register_number')
    session_code = request.form.get('session_code')
    reason = request.form.get('reason')
    if not Student.query.get(register_number) or not Session.query.filter_by(code=session_code).first():
        flash('Invalid student or session!', 'warning')
    else:
        absence = Absence(register_number=register_number, session_code=session_code, reason=reason)
        db.session.add(absence)
        db.session.commit()
        flash('Absence reason added!', 'success')
    return redirect(url_for('student_profile', register_number=register_number))

@app.route('/admin_dashboard', methods=['GET', 'POST'])
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Access denied', 'warning')
        return redirect(url_for('login'))
    return dashboard_logic('admin_dashboard.html')

@app.route('/professor_dashboard')
@login_required
def professor_dashboard():
    if current_user.role != 'professor':
        flash('Access denied', 'warning')
        return redirect(url_for('login'))
    return dashboard_logic('professor_dashboard.html')

@app.route('/export_excel')
@login_required
def export_excel():
    date_str = request.args.get('date', datetime.utcnow().strftime('%Y-%m-%d'))
    selected_date = datetime.strptime(date_str, '%Y-%m-%d')
    start_of_day = datetime(selected_date.year, selected_date.month, selected_date.day)
    attendance = Attendance.query.filter(Attendance.date >= start_of_day, Attendance.date < start_of_day + timedelta(days=1)).all()
    data = {
        'Register Number': [a.register_number for a in attendance],
        'Name': [Student.query.get(a.register_number).name for a in attendance],
        'Date': [a.date.strftime('%Y-%m-%d %H:%M:%S') for a in attendance],
        'Session Code': [a.session_code for a in attendance]
    }
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Attendance')
    output.seek(0)
    return send_file(output, download_name=f'attendance_{date_str}.xlsx', as_attachment=True)

def dashboard_logic(template_name):
    date_str = request.args.get('date', datetime.utcnow().strftime('%Y-%m-%d'))
    selected_date = datetime.strptime(date_str, '%Y-%m-%d')
    start_of_day = datetime(selected_date.year, selected_date.month, selected_date.day)
    end_of_day = start_of_day + timedelta(days=1)
    sessions = Session.query.filter(Session.created_at >= start_of_day, Session.created_at < end_of_day).all()
    attendance = Attendance.query.filter(Attendance.date >= start_of_day, Attendance.date < end_of_day).all()
    students = Student.query.all()
    
    # Calculate total present and absent
    attendance_dict = {(a.register_number, a.session_code): True for a in attendance}
    total_present = len(set(a.register_number for a in attendance))
    total_absent = len(students) - total_present
    
    student_status = []
    for student in students:
        status = 'Absent'
        for session in sessions:
            if (student.register_number, session.code) in attendance_dict:
                status = 'Present'
                break
        student_status.append({
            'register_number': student.register_number,
            'name': student.name,
            'status': status
        })
    
    # Calculate absentees (students who didn't attend any session on the selected date)
    present_students = set(a.register_number for a in attendance)
    absentees = [
        {'register_number': student.register_number, 'name': student.name}
        for student in students if student.register_number not in present_students
    ]
    
    return render_template(
        template_name,
        sessions=sessions,
        student_status=student_status,
        total_present=total_present,
        total_absent=total_absent,
        selected_date=date_str,
        datetime=datetime,
        last_login=current_user.last_login if current_user.is_authenticated else None,
        absentees=absentees
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
