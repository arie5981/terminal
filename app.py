import re
from flask import Flask, request, jsonify
# ודא שכל הספריות הרלוונטיות שלך (OpenAI, DB וכו') מיובאות כאן

app = Flask(__name__)

# פונקציית עזר לניקוי תגיות HTML מההיסטוריה (ליתר ביטחון)
def clean_html(text):
    if not text:
        return ""
    # מסיר את כל מה שמופיע אחרי המפריד של המטא-דאטה אם קיים
    if "<br><hr>" in text:
        text = text.split("<br><hr>")[0]
    # מסיר תגיות HTML
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).strip()

@app.route('/chat',默默={})  # שנה בהתאם לראוטינג שלך, למשל @app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_question = data.get('question', '').strip()
    history = data.get('history', [])

    if not user_question:
        return jsonify({"error": "No question provided"}), 400

    # 1. ניקוי מנע של ההיסטוריה כדי שהמודל לא יתבלבל מתגיות קוד
    clean_history = []
    for msg in history:
        clean_history.append({
            "role": msg.get("role"),
            "content": clean_html(msg.get("content", ""))
        })

    # 2. 🧠 שלב שלוש: Query Rewriting (ניסוח מחדש של השאלה על בסיס ההיסטוריה)
    # אם יש היסטוריה, נבקש מהמודל ליצור שאילתת חיפוש ממוקדת שמחברת את שאלת ההמשך להקשר המקורי
    search_query = user_question
    if clean_history:
        try:
            rewriter_messages = [
                {
                    "role": "system",
                    "content": (
                        "תפקידך לקחת שאלת המשך של משתמש ואת היסטוריית השיחה האחרונה, "
                        "ולנסח שאילתת חיפוש קצרה וממוקדת (עד 6 מילים) שתשמש לחיפוש בקובץ הנהלים.\n"
                        "עליך לשלב מילות מפתח מההיסטוריה כדי ששאלת ההמשך תהיה מובנת בפני עצמה.\n"
                        "החזר אך ורק את שאילתת החיפוש המעודכנת, ללא הקדמות או הסברים משום סוג!"
                    )
                }
            ]
            # מוסיפים את 2 ההודעות האחרונות מההיסטוריה לצורך הקשר קרוב
            rewriter_messages.extend(clean_history[-2:])
            rewriter_messages.append({"role": "user", "content": f"שאלת המשך: {user_question}"})

            # קריאה קצרה ומהירה ל-OpenAI (אפשר להשתמש במודל קטן וזול כמו gpt-4o-mini)
            rewrite_response = openai.chat.completions.create(
                model="gpt-4o-mini", 
                messages=rewriter_messages,
                temperature=0.0
            )
            search_query = rewrite_response.choices[0].message.content.strip()
            print(f"🔍 שאילתת החיפוש המקורית: '{user_question}' -> שודרגה ל: '{search_query}'")
        except Exception as e:
            print(f"Error during query rewriting: {e}")
            search_query = user_question # במקרה של שגיאה, נשארים עם המקור

    # 3. 📄 שלב החיפוש (RAG) - כעת משתמשים ב-search_query המשודרג ולא בשאלה המקורית!
    # כאן יבוא קוד החיפוש הקיים שלך (למשל חיפוש וקטורי או חיפוש טקסטואלי ב-Terminal.txt)
    # context = search_in_documents(search_query)  <-- דוגמה קיומית לקוד שלך
    
    # 4. 🤖 יצירת התשובה הסופית (הפרומפט המשודרג מהשלב הקודם)
    system_prompt = (
        "אתה עוזר דיגיטלי מקצועי, שירותי, ענייני ומדויק לחלוטין של אתר מייצגים בגביה של הביטוח הלאומי.\n"
        "תפקידך להנדס את המידע מהנהלים ולנסח תשובה נקייה, אסתטית, מרווחת, וללא מילים מיותרות או פרשנות עצמית.\n"
        "המידע מהנהלים (Context) מסופק לך כאשר הוא מחולק ל'קטע מידע 1', 'קטע מידע 2' וכו'.\n\n"
        
        "⛔ חוק איסור פרשנות והמצאת עובדות (קריטי ומעל הכל):\n"
        "1. אל תפרש, אל תסביר את הלוגיקה מאחורי הנהלים, ואל תוסיף משפטי הקדמה או שלבים שלא מופיעים בטקסט במפורש!\n"
        "2. אסור להמציא פעולות, כותרות או שלבי ביניים שאינם כתובים בטקסט המקור.\n\n"
        
        "🚫 חוק איסור שלבי כניסה והתחברות:\n"
        "1. חל איסור מוחלט לפתוח את התשובה או את השלב הראשון במשפטים כגון: 'היכנס לאתר מייצגים', 'התחבר למערכת' וכדומה. הנחת היסוד היא שהמשתמש כבר נמצא באתר!\n"
        "2. התחל את השלב הראשון ישירות מהפעולה המעשית הראשונה בתוך האתר (לדוגמה: 'באתר מייצגים, לחץ על...').\n\n"
        
        "🧱 חוקי מבנה וארכיטקטורה דינמית:\n"
        "1. השתמש במילה '**שלב**' אך ורק אם מדובר בתהליך כרונולוגי חובה שמופיע בטקסט.\n"
        "2. חוק ה-2 עד 4: חלוק את התשובה למינימום 2 ומקסימום 4 חלקים מרכזיים בלבד (אם יש מספיק מידע). אם הטקסט קצר, הצג אותו בצורה ממוקדת מבלי לנפח אותו.\n"
        "3. תתי-סעיפים (בוליטים): מתחת לכל כותרת ראשית, פרט את המידע באמצעות נקודות (•).\n\n"
        
        "🎯 חוקי ניסוח, פתיח וסיום:\n"
        "1. גישה ישירה לעניין: אסור להשתמש במשפטי פתיחה שבלוניים (כמו 'תודה על השאלה'). פתח מיד במשפט ענייני המחובר לשאלה.\n"
        "2. סיום נקי: אל תוסיף משפטי סיום רובוטיים קבועים.\n\n"
        
        "🔗 חוקי קישורים וסוגריים מרובעים:\n"
        "- ודא שכל שם של טופס, אתר, מערכת או מייל עטופים בדיוק בסוגריים מרובעים כפי שהם מופיעים בנהלים (לדוגמה: [אתר שירות אישי])."
    )

    final_messages = [{"role": "system", "content": system_prompt}]
    
    # מוסיפים את ההיסטוריה הנקייה כדי שהמודל הנוכחי ידע על מה דיברנו
    final_messages.extend(clean_history)
    
    # מוסיפים את שאלת המשתמש המקורית (כדי שיענה עליה, אבל הקונטקסט נשלף לפי השאלה המשודרגת!)
    final_messages.append({"role": "user", "content": f"הקשר מהנהלים עבור השאלה הזו:\n{context}\n\nשאלה: {user_question}"})

    # קריאה ל-OpenAI לקבלת התשובה הסופית
    # response = openai.chat.completions.create(model="gpt-4o", messages=final_messages, ...)
    
    # החזרת התשובה (והוספת המטא-דאטה באקורדיון כפי שביצעת קודם)
    # return jsonify({"response": final_response_text + accordion_html})
