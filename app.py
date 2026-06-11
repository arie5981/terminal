from flask import Flask, render_template, request, jsonify
import os
from openai import OpenAI

app = Flask(__name__)

# שליפת המפתח הסודי
openai_api_key = os.environ.get("OPENAI_API_KEY")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    # בדיקה מקדימה אם המפתח בכלל קיים בשרת
    if not openai_api_key:
        return jsonify({
            "response": "❌ שגיאה: המשתנה OPENAI_API_KEY לא מוגדר בכלל בשרת של Fly.io! ודא שהגדרת אותו בלשונית Secrets בדשבורד."
        })

    try:
        # אתחול הקליינט עם המפתח
        client = OpenAI(api_key=openai_api_key)
        
        # פנייה קצרצרה לבדיקה
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "תענה במילה אחת בלבד: האם הכל עובד?"}
            ],
            temperature=0.2
        )
        
        answer_from_ai = response.choices[0].message.content
        return jsonify({
            "response": f"✅ החיבור ל-OpenAI הצליח! המפתח שלך עובד מצוין. תשובת המודל: {answer_from_ai}"
        })

    except Exception as e:
        # אם יש שגיאה (למשל מפתח שגוי או חסום), נציג אותה ישירות למסך
        return jsonify({
            "response": f"❌ החיבור נכשל. OpenAI החזירה את השגיאה הבאה: {str(e)}"
        })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
