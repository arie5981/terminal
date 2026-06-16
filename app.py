from flask import Flask, render_template, request, jsonify
import os
from google import genai

app = Flask(__name__)

# שליפת המפתח
gemini_api_key = os.environ.get("GEMINI_API_KEY")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    # 1. בדיקה שהמפתח קיים
    if not gemini_api_key:
        return jsonify({"response": "❌ מפתח ה-API חסר בשרת."})

    # 2. אתחול הלקוח של גוגל בתוך הראוט עם המפתח המוכח
    try:
        client = genai.Client(api_key=gemini_api_key)
    except Exception as e:
        return jsonify({"response": f"❌ נכשל אתחול הלקוח של גוגל: {e}"})

    # 3. שליחת שאילתה פשוטה וישירה ל-Gemini
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="תגיד לי בבקשה 'שלום עולם, החיבור לג'מיני עובד!'"
        )
        
        # 4. החזרת התשובה שגוגל שלח לנו
        return jsonify({"response": f"✅ תקשורת הצליחה! הנה מה שגוגל ענה:<br><br> <b>{response.text}</b>"})

    except Exception as gemini_err:
        return jsonify({"response": f"❌ שגיאה בפנייה ל-Gemini API: {gemini_err}"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
