import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, render_template, render_template_string

app = Flask(__name__)

# --- משתנה הדיבאג הגלובלי ---
DEBUG_MODE = 1  # 0 = כבוי (מערכת רגילה), 1 = מצב דיבאג פעיל

# הגדרת נתיבים לתיקיית הדאטה ולקבצים
DATA_DIR = "data"
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.txt")
REMARKS_FILE = os.path.join(DATA_DIR, "remarks.txt")

# יצירת תיקיית data באופן אוטומטי בשרת אם אינה קיימת
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# 1. נתיב דף הבית (הצגת ממשק הצ'אט)
@app.route('/', methods=['GET'])
def home():
    return render_template('index.html')

# 2. נתיב ה-Chat המרכזי שיוצר קשר עם ג'מיני
@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_question = data.get('question', '').strip()
    history = data.get('history', [])

    # רישום השאלה בתוך data/questions.txt אם הדיבאג פעיל
    if DEBUG_MODE == 1 and user_question:
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(QUESTIONS_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {user_question}\n")
        except Exception as e:
            print(f"Error writing to questions.txt: {e}")

    # --- כאן מתבצעת הלוגיקה הקיימת שלך מול Gemini שמחזירה את התשובה ---
    # נניח שהמשתנה שמכיל את תשובת ה-HTML הסופית נקרא bot_response
    bot_response = "זוהי תשובת דוגמה מהנוהל.<br>1. שלב ראשון.<br>2. שלב שני." 
    # -----------------------------------------------------------------

    return jsonify({
        'response': bot_response,
        'debug': DEBUG_MODE,
        'original_question': user_question
    })

# 3. נתיב לקבלת הערת הדיבאג מהחלון הקופץ ושמירתה בפורמט JSONL
@app.route('/save_remark', methods=['POST'])
def save_remark():
    if DEBUG_MODE != 1:
        return jsonify({"status": "error", "message": "Debug mode is off"}), 403
        
    try:
        data = request.json
        remark_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "author": data.get("author", "").strip() or "אנונימי",
            "remark": data.get("remark", "").strip(),
            "question": data.get("question", "").strip(),
            "response": data.get("response", "").strip()
        }

        # שמירה בפורמט JSON Lines בתוך תיקיית data
        with open(REMARKS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(remark_entry, ensure_ascii=False) + "\n")

        return jsonify({"status": "success", "message": "ההערה נשמרה בהצלחה"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 4. נתיב דף ריכוז ההערות (הטבלה המעוצבת) באתר
@app.route('/remarks', methods=['GET'])
def show_remarks():
    remarks_list = []
    
    if os.path.exists(REMARKS_FILE):
        try:
            with open(REMARKS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        remarks_list.append(json.loads(line.strip()))
        except Exception as e:
            print(f"Error reading remarks file: {e}")
            
    # הצגת ההערות החדשות ביותר למעלה
    remarks_list.reverse()
    return render_template_string(REMARKS_HTML_TEMPLATE, remarks=remarks_list)

# --- תבנית ה-HTML הייעודית לעמוד ה-Remarks ---
REMARKS_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ניהול הערות דיבאג - מייצגים</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f6f9; margin: 0; padding: 20px; color: #333; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #1e3a8a; border-bottom: 3px solid #1e3a8a; padding-bottom: 10px; margin-bottom: 20px; font-size: 24px; }
        .summary-badge { background-color: #1e3a8a; color: white; padding: 4px 12px; border-radius: 12px; font-size: 14px; display: inline-block; margin-bottom: 15px; }
        .table-container { background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); overflow: hidden; }
        table { width: 100%; border-collapse: collapse; text-align: right; }
        th { background-color: #1e3a8a; color: white; padding: 12px 15px; font-weight: bold; font-size: 15px; }
        td { padding: 12px 15px; border-bottom: 1px solid #e4e6eb; font-size: 14px; vertical-align: top; line-height: 1.5; }
        tr:hover { background-color: #f8fafc; }
        .timestamp { color: #666; font-size: 12px; white-space: nowrap; }
        .author { font-weight: bold; color: #007bff; }
        .remark-text { background-color: #fff9db; padding: 6px 10px; border-right: 3px solid #fcc419; border-radius: 4px; font-weight: 500; }
        .box-content { max-height: 150px; overflow-y: auto; background-color: #f8f9fa; padding: 8px; border-radius: 4px; font-size: 13px; white-space: pre-line; }
        .no-remarks { text-align: center; padding: 40px; color: #666; font-size: 16px; }
        @media (max-width: 768px) {
            table, thead, tbody, th, td, tr { display: block; }
            thead { display: none; }
            tr { background: white; border: 1px solid #ccd0d5; border-radius: 8px; margin-bottom: 15px; padding: 10px; }
            td { border: none; padding: 6px 0; }
            td::before { content: attr(data-label); display: block; font-weight: bold; color: #1e3a8a; font-size: 12px; margin-bottom: 2px; }
        }
    </style>
</head>
<body>
<div class="container">
    <h1>📝 ריכוז הערות דיבאג ופידבק</h1>
    <div class="summary-badge">סה"כ הערות שנאספו: {{ remarks|length }}</div>
    <div class="table-container">
        {% if remarks %}
        <table>
            <thead>
                <tr>
                    <th style="width: 15%;">זמן ומעיר</th>
                    <th style="width: 25%;">ההערה שנכתבה</th>
                    <th style="width: 30%;">השאלה המקורית</th>
                    <th style="width: 30%;">תשובת הבוט</th>
                </tr>
            </thead>
            <tbody>
                {% for r in remarks %}
                <tr>
                    <td data-label="זמן ומעיר">
                        <div class="timestamp">{{ r.timestamp }}</div>
                        <div class="author">{{ r.author }}</div>
                    </td>
                    <td data-label="ההערה">
                        <div class="remark-text">{{ r.remark }}</div>
                    </td>
                    <td data-label="השאלה המקורית">
                        <div class="box-content">{{ r.question }}</div>
                    </td>
                    <td data-label="תשובת הבוט">
                        <div class="box-content">{{ r.response | striptags }}</div>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="no-remarks">טרם נרשמו הערות במערכת.</div>
        {% endif %}
    </div>
</div>
</body>
</html>
"""

if __name__ == '__main__':
    # התאמה מלאה לפורטים ולסביבה של Fly.io
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
