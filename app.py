# app.py
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import date, datetime
import os
import pandas as pd

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///attendance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key_here'

db = SQLAlchemy(app)

# Models
class Classroom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    students = db.relationship('Student', backref='classroom', lazy=True)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)
    attendances = db.relationship('Attendance', backref='student', lazy=True)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'))
    date = db.Column(db.Date, default=date.today)
    status = db.Column(db.String(10))

@app.before_request
def create_tables():
    db.create_all()

@app.route('/')
def index():
    classrooms = Classroom.query.all()
    classroom_id = request.args.get('classroom_id')
    if classroom_id:
        students = Student.query.filter_by(classroom_id=classroom_id).all()
    else:
        students = Student.query.all()
    return render_template('index.html', students=students, classrooms=classrooms, selected_classroom_id=classroom_id)

@app.route('/add', methods=['GET', 'POST'])
def add_student():
    classrooms = Classroom.query.all()
    if request.method == 'POST':
        name = request.form['name']
        classroom_id = request.form['classroom_id']
        student = Student(name=name, classroom_id=classroom_id)
        db.session.add(student)
        db.session.commit()
        flash('Student added successfully.')
        return redirect(url_for('index'))
    return render_template('add_student.html', classrooms=classrooms)

@app.route('/add_classroom', methods=['GET', 'POST'])
def add_classroom():
    if request.method == 'POST':
        name = request.form['name']
        new_classroom = Classroom(name=name)
        db.session.add(new_classroom)
        db.session.commit()
        flash(f'Classroom "{name}" added.', 'success')
        return redirect(url_for('add_classroom'))
    classrooms = Classroom.query.all()
    return render_template('add_classroom.html', classrooms=classrooms)

@app.route('/delete_classroom/<int:classroom_id>', methods=['POST'])
def delete_classroom(classroom_id):
    classroom = Classroom.query.get_or_404(classroom_id)
    students = Student.query.filter_by(classroom_id=classroom.id).first()
    if students:
        flash('Cannot delete: Classroom has assigned students.', 'error')
        return redirect(url_for('add_classroom'))

    db.session.delete(classroom)
    db.session.commit()
    flash('Classroom deleted.', 'success')
    return redirect(url_for('add_classroom'))


@app.route('/upload_students', methods=['GET', 'POST'])
def upload_students():
    classrooms = Classroom.query.all()
    if request.method == 'POST':
        file = request.files['file']
        classroom_id = request.form['classroom_id']
        df = pd.read_excel(file)
        for name in df['name']:
            student = Student(name=name, classroom_id=classroom_id)
            db.session.add(student)
        db.session.commit()
        flash('Students uploaded successfully.')
        return redirect(url_for('index'))
    return render_template('upload_students.html', classrooms=classrooms)

@app.route('/attendance', methods=['GET', 'POST'])
def attendance():
    classrooms = Classroom.query.all()
    selected_class_id = request.args.get('classroom_id') or request.form.get('classroom_id')
    students = Student.query.filter_by(classroom_id=selected_class_id).all() if selected_class_id else []

    if request.method == 'POST':
        present_ids = request.form.getlist('present')
        date_val = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        for student in students:
            status = 'Present' if str(student.id) in present_ids else 'Absent'
            db.session.add(Attendance(student_id=student.id, date=date_val, status=status))
        db.session.commit()
        flash('Attendance submitted.')
        return redirect(url_for('index'))

    return render_template('attendance.html', classrooms=classrooms, students=students, selected_class_id=selected_class_id, today=date.today())

@app.route('/records', methods=['GET', 'POST'])
def records():
    classrooms = Classroom.query.all()
    selected_date = None
    selected_classroom_id = None

    if request.method == 'POST':
        selected_date = request.form.get('date')
        selected_classroom_id = request.form.get('classroom_id')

    query = db.session.query(
        Student.name, Attendance.date, Attendance.status
    ).join(Attendance).join(Classroom)

    # Filter by date if selected
    if selected_date:
        date_obj = datetime.strptime(selected_date, '%Y-%m-%d').date()
        query = query.filter(Attendance.date == date_obj)

    # Filter by classroom if selected
    if selected_classroom_id:
        query = query.filter(Student.classroom_id == int(selected_classroom_id))

    records = query.order_by(Attendance.date.desc()).all()

    present_count = sum(1 for r in records if r[2] == 'Present')
    absent_count = sum(1 for r in records if r[2] == 'Absent')

    # Count attendance per student
    student_stats = {}
    for name, _, status in records:
        if name not in student_stats:
            student_stats[name] = {'Present': 0, 'Absent': 0}
        student_stats[name][status] += 1

    return render_template('records.html',
                           records=records,
                           selected_date=selected_date,
                           selected_classroom_id=selected_classroom_id,
                           classrooms=classrooms,
                           present_count=present_count,
                           absent_count=absent_count,
                           student_stats=student_stats)

@app.route('/student/<int:student_id>')
def student_records(student_id):
    student = Student.query.get_or_404(student_id)
    records = Attendance.query.filter_by(student_id=student.id).order_by(Attendance.date.desc()).all()
    present_count = Attendance.query.filter_by(student_id=student.id, status="Present").count()
    absent_count = Attendance.query.filter_by(student_id=student.id, status="Absent").count()
    return render_template('student_records.html', student=student, records=records, present_count=present_count, absent_count=absent_count)

@app.route('/delete_student/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    Attendance.query.filter_by(student_id=student.id).delete()
    db.session.delete(student)
    db.session.commit()
    flash('Student deleted.')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
