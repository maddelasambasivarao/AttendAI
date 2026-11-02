from flask import Flask, render_template_string, request
import sqlite3

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('students.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS students 
                 (id INTEGER PRIMARY KEY, name TEXT, attendance REAL, internal REAL, cgpa REAL, risk TEXT)''')
    conn.commit()
    conn.close()

init_db()

HTML = """
<!DOCTYPE html>
<html>
<head>
<title>AttendAI - Pro Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body{font-family:Arial; background:#f5f7fb; padding:20px}
.box{background:white; padding:20px; border-radius:12px; max-width:850px; margin:auto; box-shadow:0 4px 20px rgba(0,0,0,0.1)}
input{padding:12px; margin:6px; width:92%; border-radius:8px; border:1px solid #ccc}
button{padding:12px 20px; background:#2563eb; color:white; border:none; border-radius:8px; cursor:pointer; width:100%; font-weight:bold; font-size:16px}
.risk-high{color:#ef4444} .risk-low{color:#22c55e} .risk-medium{color:#f59e0b}
table{width:100%; margin-top:20px; border-collapse:collapse} th,td{border:1px solid #ddd; padding:10px; text-align:center}
th{background:#2563eb; color:white}
.detail-box{background:#f0f9ff; padding:15px; border-radius:10px; margin-top:15px; border-left:5px solid #2563eb; text-align:left}
ul{line-height:1.9; list-style:none; padding:0}
</style>
</head>
<body>
<div class="box">
<h2>AttendAI - AI Risk Prediction System</h2>
<p>AI-powered Student Performance & Risk Analysis</p>

<form method="POST">
<input name="name" placeholder="Student Name (Ex: John Doe)" required>
<input name="attendance" type="number" step="0.1" placeholder="Attendance Out of 100 (Ex: 95)" required>
<input name="internal" type="number" step="0.1" placeholder="Internals Out of 30 (Ex: 28)" required>
<input name="cgpa" type="number" step="0.1" placeholder="CGPA Out of 10 (Ex: 9.2)" required>
<button type="submit">Predict & Save Record</button>
</form>

{% if result %}
<div class="detail-box">
<h3>Result: <span class="{% if 'HIGH' in result %}risk-high{% elif 'MEDIUM' in result %}risk-medium{% else %}risk-low{% endif %}">{{result}}</span></h3>
<p><b>Student Name:</b> {{last_name}}</p>
<p><b>Performance Breakdown:</b></p>
<ul>
<li>Attendance: <b>{{last_att}}/100</b> - {% if last_att >= 75 %}Good Standing{% else %}Needs Improvement{% endif %}</li>
<li>Internals: <b>{{last_internal}}/30</b> - {% if last_internal >= 20 %}Excellent{% elif last_internal >= 12 %}Average{% else %}Poor Performance{% endif %}</li>
<li>CGPA: <b>{{last_cgpa}}/10</b> - {% if last_cgpa >= 8 %}On Track{% elif last_cgpa >= 6 %}Needs Improvement{% else %}Critical{% endif %}</li>
</ul>
<p><b>Recommendation:</b> {{suggestion}}</p>
</div>
{% endif %}

<h3 style="margin-top:30px">Risk Analysis Chart</h3>
<canvas id="myChart" height="120"></canvas>

<h3 style="margin-top:30px">Saved Student Records</h3>
<table>
<tr><th>Name</th><th>Attendance</th><th>Internals</th><th>Risk Level</th></tr>
{% for s in students %}
<tr><td>{{s[1]}}</td><td>{{s[2]}}/100</td><td>{{s[3]}}/30</td><td>{{s[5]}}</td></tr>
{% endfor %}
</table>

{% if students|length == 0 %}
<p style="color:gray">No records found - Add students to view database</p>
{% endif %}

</div>

<script>
const ctx = document.getElementById('myChart').getContext('2d');
new Chart(ctx, {
  type: 'pie',
  data: {
    labels: ['Low Risk', 'Medium Risk', 'High Risk'],
    datasets: [{ data: [{{low_count}}, {{med_count}}, {{high_count}}], backgroundColor: ['#22c55e','#f59e0b','#ef4444'] }]
  }
});
</script>
</body>
</html>
"""

@app.route('/', methods=['GET','POST'])
def home():
    result = None
    last_name = last_att = last_internal = last_cgpa = suggestion = ""
    conn = sqlite3.connect('students.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        name = request.form['name']
        att = float(request.form['attendance'])
        internal = float(request.form['internal'])
        cgpa = float(request.form['cgpa'])
        
        if att < 60 or internal < 12 or cgpa < 6:
            risk = "HIGH RISK - Counselling Required"
        elif att < 75 or internal < 18:
            risk = "MEDIUM RISK - Improvement Needed"
        else:
            risk = "LOW RISK - SAFE - Student is on track"

        if 'HIGH' in risk:
            suggestion = f"Increase attendance by {75-att:.0f} marks and focus on internals. Requires immediate attention."
        elif 'MEDIUM' in risk:
            suggestion = "Improve attendance to reach 75/100 to achieve LOW RISK status. Keep working."
        else:
            suggestion = "Excellent performance! Maintain the same consistency and academic standards."
        
        result = risk
        last_name, last_att, last_internal, last_cgpa = name, att, internal, cgpa
        
        c.execute("INSERT INTO students (name, attendance, internal, cgpa, risk) VALUES (?,?,?,?,?)",
                  (name, att, internal, cgpa, risk))
        conn.commit()

    c.execute("SELECT * FROM students ORDER BY id DESC")
    students = c.fetchall()
    low_count = len([s for s in students if 'LOW' in s[5]])
    med_count = len([s for s in students if 'MEDIUM' in s[5]])
    high_count = len([s for s in students if 'HIGH' in s[5]])
    conn.close()
    
    return render_template_string(HTML, result=result, students=students, 
                                  low_count=low_count, med_count=med_count, high_count=high_count,
                                  last_name=last_name, last_att=last_att, 
                                  last_internal=last_internal, last_cgpa=last_cgpa, suggestion=suggestion)

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)