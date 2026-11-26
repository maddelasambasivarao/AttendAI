"""
seed.py – Database initialization and realistic seeding script for AttendAI.
Usage:
    python seed.py

Creates all SQLite tables and seeds:
  - Local demo Admin account (admin / Admin@123)
  - Multiple Faculty members
  - Active Semester with 5 subjects
  - 15+ Students across departments, years, and sections
  - Multiple sessions of daily attendance records across multiple dates
  - Audit trail history entries (AttendanceEditHistory)
"""

import sys
import os
from datetime import date, datetime, timedelta

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from database.models import (
    db, User, Faculty, Semester, Student, Subject,
    StudentSubjectEnrolment, AttendanceRecord, AttendanceEditHistory,
    PredictionHistory, Intervention
)

app = create_app(os.environ.get("FLASK_ENV", "development"))


def seed_database(clean=True):
    with app.app_context():
        print("=" * 65)
        print("  AttendAI – Complete Database & Attendance Seeding")
        print("=" * 65)

        # 1. Create all SQLite tables
        if clean:
            print("\n[1/6] Recreating SQLite database tables cleanly...")
            db.drop_all()
            db.create_all()
            print("      All SQLite tables created freshly.")
        else:
            print("\n[1/6] Verifying SQLite database tables...")
            db.create_all()
            print("      All SQLite tables verified.")

        # 2. Local Demo Admin Account
        print("\n[2/6] Setting up local demo Admin account...")
        admin = User.query.filter_by(username="admin").first()
        if not admin:
            admin = User(
                username="admin",
                email="admin@attendai.edu",
                role="admin",
                is_active=True
            )
            admin.set_password("Admin@123")
            db.session.add(admin)
            db.session.flush()

            admin_profile = Faculty(
                user_id=admin.id,
                name="System Administrator",
                department="Administration",
                employee_id="ADM001",
                phone="+91 9999900001"
            )
            db.session.add(admin_profile)
            print("      Created demo admin: admin / Admin@123")
        else:
            admin.set_password("Admin@123")
            admin.is_active = True
            print("      Demo admin account verified.")

        # 3. Multiple Faculty Members
        print("\n[3/6] Setting up Faculty members...")
        fac_configs = [
            ("faculty1", "faculty1@attendai.edu", "Dr. Ananya Sharma", "Computer Science", "CSE001"),
            ("faculty2", "faculty2@attendai.edu", "Prof. Ravi Kumar", "Information Technology", "IT001"),
            ("faculty3", "faculty3@attendai.edu", "Dr. Priya Nair", "Electronics", "ECE001"),
        ]
        faculty_map = {}
        for uname, email, fname, dept, empid in fac_configs:
            f_user = User.query.filter_by(username=uname).first()
            if not f_user:
                f_user = User(username=uname, email=email, role="faculty", is_active=True)
                f_user.set_password("Faculty@123")
                db.session.add(f_user)
                db.session.flush()

                f_prof = Faculty(
                    user_id=f_user.id,
                    name=fname,
                    department=dept,
                    employee_id=empid,
                    phone="+91 9876543210"
                )
                db.session.add(f_prof)
                db.session.flush()
                faculty_map[uname] = f_prof
            else:
                f_user.set_password("Faculty@123")
                faculty_map[uname] = f_user.faculty_profile
        print(f"      Verified {len(faculty_map)} faculty accounts.")

        # 4. Semester & Multiple Subjects
        print("\n[4/6] Setting up Semester & Subjects...")
        sem = Semester.query.filter_by(name="Semester 3 – 2025-26").first()
        if not sem:
            sem = Semester(
                name="Semester 3 – 2025-26",
                year=2025,
                section="A",
                start_date=date(2025, 7, 1),
                end_date=date(2025, 12, 15),
                is_active=True
            )
            db.session.add(sem)
            db.session.flush()

        subjects_data = [
            ("Machine Learning", "CS601", faculty_map.get("faculty1").id, 45, "theory"),
            ("Data Structures & Algorithms", "CS602", faculty_map.get("faculty1").id, 45, "theory"),
            ("Database Management Systems", "CS603", faculty_map.get("faculty2").id, 40, "theory"),
            ("Applied Mathematics", "MA601", faculty_map.get("faculty2").id, 35, "theory"),
            ("ML & Data Science Lab", "CS691", faculty_map.get("faculty1").id, 30, "lab"),
        ]
        subject_objs = []
        for sname, scode, fid, classes, stype in subjects_data:
            subj = Subject.query.filter_by(code=scode, semester_id=sem.id).first()
            if not subj:
                subj = Subject(
                    name=sname, code=scode, semester_id=sem.id,
                    faculty_id=fid, total_classes_planned=classes, subject_type=stype
                )
                db.session.add(subj)
                db.session.flush()
            subject_objs.append(subj)
        print(f"      Verified {len(subject_objs)} subjects.")

        # 5. Multiple Students across Departments & Sections
        print("\n[5/6] Setting up Multiple Students across Departments...")
        student_records = [
            # High Attendance Students (>85%)
            ("STU2025001", "CS202501", "Aarav Sharma",   "Computer Science", 2, "A", "aarav@attendai.edu", 0.95),
            ("STU2025002", "CS202502", "Deepika Rao",    "Computer Science", 2, "A", "deepika@attendai.edu", 0.90),
            ("STU2025003", "CS202503", "Karan Singh",    "Computer Science", 2, "A", "karan@attendai.edu", 0.88),
            ("STU2025004", "CS202504", "Sneha Pillai",   "Computer Science", 2, "A", "sneha@attendai.edu", 0.92),
            ("STU2025005", "IT202501", "Rohit Verma",    "Information Technology", 2, "A", "rohit@attendai.edu", 0.85),

            # Regular Attendance Students (75% - 84%)
            ("STU2025006", "CS202505", "Priya Joshi",    "Computer Science", 2, "B", "priya@attendai.edu", 0.80),
            ("STU2025007", "EC202501", "Arjun Nair",     "Electronics", 2, "A", "arjun@attendai.edu", 0.78),
            ("STU2025008", "CS202506", "Kavya Reddy",    "Computer Science", 2, "B", "kavya@attendai.edu", 0.82),
            ("STU2025009", "IT202502", "Vikram Sharma",  "Information Technology", 2, "B", "vikram@attendai.edu", 0.76),
            ("STU2025010", "CS202507", "Ananya Das",     "Computer Science", 2, "A", "ananya@attendai.edu", 0.75),

            # Shortage Attendance Students (60% - 74%) - Medium Risk
            ("STU2025011", "CS202508", "Manish Kumar",   "Computer Science", 2, "B", "manish@attendai.edu", 0.68),
            ("STU2025012", "IT202503", "Ritu Sen",       "Information Technology", 2, "A", "ritu@attendai.edu", 0.64),
            ("STU2025013", "EC202502", "Gaurav Malhotra","Electronics", 2, "A", "gaurav@attendai.edu", 0.70),

            # Critical Attendance Students (< 60%) - High Risk
            ("STU2025014", "CS202509", "Tanvi Bhatia",   "Computer Science", 2, "B", "tanvi@attendai.edu", 0.50),
            ("STU2025015", "IT202504", "Aditya Kulkarni","Information Technology", 2, "B", "aditya@attendai.edu", 0.42),
            ("STU2025016", "CS202510", "Neha Chawla",    "Computer Science", 2, "A", "neha@attendai.edu", 0.35),
        ]

        created_students = []
        for sid, roll, sname, dept, yr, sec, semail, target_ratio in student_records:
            st = Student.query.filter((Student.student_id == sid) | (Student.roll_number == roll)).first()
            if not st:
                st = Student(
                    student_id=sid,
                    roll_number=roll,
                    name=sname,
                    department=dept,
                    year=yr,
                    section=sec,
                    email=semail,
                    semester_id=sem.id,
                    is_active=True
                )
                db.session.add(st)
                db.session.flush()
            else:
                st.student_id = sid
                st.roll_number = roll
                st.name = sname
                st.department = dept
                st.year = yr
                st.section = sec
                st.email = semail
                st.semester_id = sem.id
                db.session.flush()

            st.enroll_in_semester_subjects()
            created_students.append((st, target_ratio))

        db.session.commit()
        print(f"      Verified {len(created_students)} students across CSE, IT, and ECE.")

        # 6. Generate Multi-day Attendance Sessions & Audit History
        print("\n[6/6] Generating Multi-day Class Sessions & Audit Records...")
        # 12 class dates over September and October
        start_date = date(2025, 9, 1)
        class_dates = [start_date + timedelta(days=i * 3) for i in range(12)]

        admin_user = User.query.filter_by(username="admin").first()
        fac1_user  = User.query.filter_by(username="faculty1").first()

        total_sessions_marked = 0
        corrected_record = None

        for c_date in class_dates:
            # For each theory subject on this date
            for subj in subject_objs[:3]:
                for st, ratio in created_students:
                    # Check existing record
                    existing = AttendanceRecord.query.filter_by(
                        student_id=st.id,
                        subject_id=subj.id,
                        date=c_date,
                        session_slot=1
                    ).first()

                    if not existing:
                        # Deterministic present/absent based on target ratio & date index
                        day_idx = (c_date - start_date).days
                        hash_val = (hash(f"{st.roll_number}_{subj.code}_{day_idx}") % 100) / 100.0
                        status = "present" if hash_val < ratio else "absent"
                        remarks = "Medical leave" if status == "absent" and hash_val > 0.85 else None

                        rec = AttendanceRecord(
                            student_id=st.id,
                            subject_id=subj.id,
                            date=c_date,
                            session_slot=1,
                            status=status,
                            remarks=remarks,
                            marked_by=fac1_user.id if fac1_user else admin_user.id,
                            last_modified_by=fac1_user.id if fac1_user else admin_user.id
                        )
                        db.session.add(rec)
                        total_sessions_marked += 1

                        if not corrected_record and status == "absent":
                            corrected_record = rec

        db.session.commit()
        print(f"      Created {total_sessions_marked} daily session attendance records.")

        # Sample Audit Trail History Entry
        if corrected_record:
            corrected_record.status = "present"
            corrected_record.last_modified_by = fac1_user.id if fac1_user else admin_user.id
            audit = AttendanceEditHistory(
                attendance_record_id=corrected_record.id,
                old_status="absent",
                new_status="present",
                reason="Medical certificate submitted & verified by HOD",
                edited_by=fac1_user.id if fac1_user else admin_user.id,
                edited_at=datetime.utcnow()
            )
            db.session.add(audit)
            db.session.commit()
            print("      Created sample audit history log entry for attendance correction.")

        # 7. Seed ML Risk Predictions & Faculty Interventions
        print("\n[7/7] Generating ML Risk Predictions & Faculty Interventions...")
        from ml.predict import predict_risk
        intv_count = 0
        pred_count = 0
        fac1_prof = faculty_map.get("faculty1")

        for st, _ in created_students:
            try:
                res = predict_risk(st.id)
                pred = PredictionHistory(
                    student_id=st.id,
                    semester_id=sem.id,
                    attendance_percentage=res["current_attendance_pct"],
                    risk_probability=res["risk_probability"],
                    predicted_final_percentage=res["predicted_final_pct"],
                    risk_level=res["risk_category"],
                    recommendations="\n".join(res["recommendations"]),
                    model_version=res["model_version"],
                    predicted_at=datetime.utcnow() - timedelta(days=1)
                )
                db.session.add(pred)
                pred_count += 1

                # Seed sample faculty interventions for High Risk students
                if res["risk_category"] == "High" and fac1_prof:
                    intv = Intervention(
                        student_id=st.id,
                        faculty_id=fac1_prof.id,
                        intervention_type="counselling",
                        notes=f"Student attendance is critically low ({res['current_attendance_pct']}%, ML risk prob: {res['risk_probability']*100:.1f}%). Contacted student for urgent academic counselling.",
                        intervention_date=date.today() - timedelta(days=4),
                        status="in_progress",
                        student_contacted=True,
                        contact_date=date.today() - timedelta(days=4),
                        contact_method="In-Person Meeting",
                        explanation_received=True,
                        student_explanation="Student reported persistent viral fever and requested hospital medical certificate verification.",
                        attendance_improved="improved",
                        attendance_at_intervention=res["current_attendance_pct"],
                        post_intervention_attendance_pct=round(res["current_attendance_pct"] + 4.2, 1),
                        follow_up_date=date.today() + timedelta(days=7),
                        created_at=datetime.utcnow() - timedelta(days=4)
                    )
                    db.session.add(intv)
                    intv_count += 1
            except Exception as e:
                pass

        db.session.commit()
        print(f"      Logged {pred_count} initial ML predictions and {intv_count} faculty interventions.")

        print("\n" + "=" * 65)
        print("  Database Seeding Completed Successfully!")
        print("=" * 65)
        print("  DEMO LOGIN CREDENTIALS:")
        print("  - Admin:   username: admin     password: Admin@123")
        print("  - Faculty: username: faculty1  password: Faculty@123")
        print("  - Faculty: username: faculty2  password: Faculty@123")
        print("=" * 65 + "\n")


if __name__ == "__main__":
    clean_flag = "--no-clean" not in sys.argv
    seed_database(clean=clean_flag)
