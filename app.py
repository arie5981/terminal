import re
from flask import Flask, request, jsonify
# ודא שספריית openai מיובאת אצלך בקוד (למשל: import openai או מתוך ה-Client החדש)

# פונקציית עזר לניקוי תגיות HTML מההיסטוריה
def clean_html(text):
    if not text:
        return ""
    if "<br><hr>" in text:
        text = text.split("<br><hr>")[0]
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).strip()

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "Missing JSON request body"}), 400
            
        user_question = data.get('question', '').strip()
        history = data.get('history', [])

        if not user_question:
            return jsonify({"error": "No question provided"}), 400

        # 1. ניקוי מנע של ההיסטוריה
        clean_history = []
        for msg in history:
            clean_history.append({
                "role": msg.get("role"),
                "content": clean_html(msg.get("content", ""))
            })

        # 2. 🧠 Query Rewriting (ניסוח מחדש של השאלה על בסיס ההיסטוריה)
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
                # לוקחים את 2 ההודעות האחרונות מההיסטוריה
                rewriter_messages.extend(clean_history[-2:])
                rewriter_messages.append({"role": "user", "content": f"שאלת המשך: {user_question}"})

                # קריאה ל-OpenAI (ודא שמשתנה ה-client או openai מוגדרים אצלך בקוד למעלה)
                rewrite_response = openai.chat.completions.create(
                    model="gpt-4o-mini", 
                    messages=rewriter_messages,
                    temperature=0.0
                )
                search_query = rewrite_response.choices[0].message.content.strip()
                print(f"🔍 שאילתה מקורית: '{user_question}' -> שודרגה ל: '{search_query}'")
            except Exception as e:
                print(f"Error during query rewriting: {e}")
                search_query = user_question 

        # 3. 📄 שליפת מידע מהנהלים (RAG)
        # שים לב: החלף את השורה הזו בשורת החיפוש האמיתית שיש לך בקוד המקורי!
        # (למשל הפונקציה שקוראת מתוך Terminal.txt או מחפשת ב-Vector DB)
        context = "" # <-- כאן צריך לבוא קוד החיפוש הקיים שלך, מבוסס על search_query
        
        # 4. 🤖 הבניית הפרומפט המהודק והסופי
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
            "2. חוק ה-2 עד 4: חלוק את התשובה למינימום 2 ומקסימום 4 חלקים מרכזיים בלבד. אם הטקסט קצר, הצג אותו בצורה ממוקדת מבלי לנפח אותו.\n"
            "3. תתי-סעיפים (בוליטים): מתחת לכל כותרת ראשית, פרט את המידע באמצעות נקודות (•).\n\n"
            
            "🎯 חוקי ניסוח, פתיח וסיום:\n"
            "1. גישה ישירה לעניין: אסור להשתמש במשפטי פתיחה שבלוניים. פתח מיד במשפט ענייני המחובר לשאלה.\n"
            "2. סיום נקי: אל תוסיף משפטי סיום רובוטיים קבועים.\n\n"
            
            "🔗 חוקי קישורים וסוגריים מרובעים:\n"
            "- ודא שכל שם של טופס, אתר, מערכת או מייל עטופים בדיוק בסוגריים מרובעים כפי שהם מופיעים בנהלים (לדוגמה: [אתר שירות אישי])."
        )

        final_messages = [{"role": "system", "content": system_prompt}]
        final_messages.extend(clean_history)
        final_messages.append({"role": "user", "content": f"הקשר מהנהלים עבור השאלה הזו:\n{context}\n\nשאלה: {user_question}"})

        # קריאה ל-OpenAI לקבלת התשובה הסופית
        # (שנה את השורות הבאות בהתאם לסינטקס המדויק שבו אתה משתמש בקוד המקור שלך)
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=final_messages,
            temperature=0.2
        )
        final_response_text = response.choices[0].message.content.strip()
        
        # כאן תחזיר את התשובה יחד עם קוד האקורדיון כפי שהיה לך קודם
        # למשל: return jsonify({"response": final_response_text + accordion_html})
        return jsonify({"response": final_response_text})

    except Exception as e:
        print(f"General error in chat route: {e}")
        return jsonify({"error": "Internal server error"}), 500
