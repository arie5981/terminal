from flask import Flask, render_template, request, jsonify
import os

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    # 1. שליפת המפתח מתוך השרת של Fly
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    
    # 2. בדיקה אם המפתח קיים בכלל
    if not gemini_api_key:
        return jsonify({
            "response": "❌ השרת לא מוצא שום משתנה סביבה בשם GEMINI_API_KEY. הוא ריק או לא קיים."
        })
    
    # 3. אם הוא קיים - נציג את האורך שלו ואת 4 התווים הראשונים והאחרונים כדי לוודא תקינות
    key_length = len(gemini_api_key)
    masked_key = f"{gemini_api_key[:4]}...{gemini_api_key[-4:]}" if key_length > 8 else "קצר מדי"
    
    return jsonify({
        "response": f"✅ המפתח נקרא בהצלחה! <br> אורך המפתח: {key_length} תווים. <br> תחילת וסוף המפתח: {masked_key}"
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
