from flask import Flask, render_template, request, jsonify
import os
import re
import numpy as np
from google import genai
from rapidfuzz import fuzz

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json or {}
    user_question = data.get('question', '').strip()

    # === שלב 1: קריאת ה-API KEY והדפסתו ===
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if gemini_api_key:
        api_key_status = f"✅ נמצא (מתחיל ב-{gemini_api_key[:4]} ומסתיים ב-{gemini_api_key[-4:]})"
    else:
        api_key_status = "❌ לא נמצא! מפתח ה-API ריק."

    # === שלב 2: פנייה ל-gemini-2.5-flash לקבלת תשובת "שלום עולם" ===
    gemini_response_status = ""
    if gemini_api_key:
        try:
            client = genai.Client(api_key=gemini_api_key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents="תגיד בדיוק את המילים הבאות: שלום עולם! הקישור לג'ימיני עובד.",
            )
            gemini_response_status = f"✅ תגובת המודל: \"{response.text.strip()}\""
        except Exception as api_error:
            gemini_response_status = f"❌ שגיאה בפנייה ל-Gemini: {api_error}"
    else:
        gemini_response_status = "❌ לא בוצעה פנייה כי המפתח חסר."

    # === שלב 3: קריאת המסמך וניתוח הנתונים ===
    file_path = os.path.join(os.path.dirname(__file__), 'data', 'Terminal.txt')
    
    if not os.path.exists(file_path):
        return jsonify({
            "response": f"🚧 <b>בדיקת שלבים טורית:</b><br>"
                        f"1️⃣ מפתח API: {api_key_status}<br>"
                        f"2️⃣ פנייה למודל: {gemini_response_status}<br>"
                        f"3️⃣ קובץ נהלים: ❌ קובץ הנהלים Terminal.txt לא נמצא בשרת."
        })

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        parts = re.split(r'===(פרק \d+)===', content)
        
        chapter_2_text = ""
        chapter_3_text = ""
        
        for i in range(1, len(parts), 2):
            header = parts[i]
            body = parts[i+1] if i+1 < len(parts) else ""
            if "פרק 2" in header:
                chapter_2_text = body
            elif "פרק 3" in header:
                chapter_3_text = body

        # חילוץ פרק 2
        qna_blocks = re.split(r'\n(?=שאלה:)', chapter_2_text)
        chunks_chapter_2 = []
        for block in qna_blocks:
            block_clean = block.strip()
            if block_clean and "תשובה:" in block_clean:
                chunks_chapter_2 = [] if not chunks_chapter_2 and not block_clean.startswith("שאלה:") else chunks_chapter_2
                chunks_chapter_2.append(block_clean)
        
        if chapter_2_text.strip().startswith("שאלה:") and not any("מהו אתר מייצגים" in c for c in chunks_chapter_2):
            first_block = chapter_2_text.split("שאלה:")[1].split("\nשאלה:")[0]
            chunks_chapter_2.insert(0, f"שאלה:{first_block.strip()}")

        # חילוץ פרק 3
        page_blocks = re.split(r'\n(?=דף מייצגים - \d+)', chapter_3_text)
        chunks_chapter_3 = []
        for block in page_blocks:
            block_clean = block.strip()
            if block_clean and ("נושא:" in block_clean or "הסבר והנחיות:" in block_clean):
                chunks_chapter_3.append(block_clean)

        all_chunks = chunks_chapter_2 + chunks_chapter_3
        total_chunks = len(all_chunks)

        # === שלב 5 המתוקן: סינון פאזי מוקדם ל-30 המובילים ושליפה סמנטית חסינה ===
        retrieval_status = ""
        retrieved_results_html = ""
        
        if user_question and gemini_api_key:
            # 1. שלב סינון מקומי מהיר - חישוב ציון פאזי לכל 136 הצ'אנקים
            fuzzy_scored_chunks = []
            for idx, chunk in enumerate(all_chunks):
                f_score = fuzz.partial_ratio(user_question, chunk) / 100.0
                fuzzy_scored_chunks.append((f_score, idx, chunk))
            
            # מיון לפי הציון הפאזי ושליפת 30 הצ'אנקים הכי מתאימים טקסטואלית
            fuzzy_scored_chunks.sort(key=lambda x: x[0], reverse=True)
            candidate_chunks_info = fuzzy_scored_chunks[:30] # מגבילים ל-30 המועמדים הכי טובים
            
            candidate_texts = [item[2] for item in candidate_chunks_info]
            candidate_fuzzy_scores = [item[0] for item in candidate_chunks_info]
            candidate_original_indices = [item[1] for item in candidate_chunks_info]

            # 2. שליפת הציון הסמנטי רק עבור 30 המועמדים (בטוח לחלוטין ממגבלת ה-100!)
            try:
                emb_response = client.models.embed_content(
                    model="text-embedding-004",
                    contents=[user_question] + candidate_texts
                )
                
                embeddings = [item.values for item in emb_response.embeddings]
                user_vector = np.array(embeddings[0])
                chunks_vectors = np.array(embeddings[1:])
                
                semantic_scores = np.dot(chunks_vectors, user_vector)
                retrieval_status = "✅ החיפוש המשולב (סמנטי + פאזי) פועל בהצלחה ועבר את מגבלת ה-Batch!"
            except Exception as emb_err:
                semantic_scores = np.zeros(len(candidate_texts))
                retrieval_status = f"⚠️ החלק הסמנטי הושבת זמנית עקב: {emb_err}"

            # 3. שילוב הציון הסופי עבור המועמדים (70% סמנטי + 30% פאזי)
            combined_candidate_scores = (semantic_scores * 0.7) + (np.array(candidate_fuzzy_scores) * 0.3)
            
            # מיון ושליפת 3 המקומות הראשונים מתוך המועמדים
            top_candidate_indices = np.argsort(combined_candidate_scores)[-3:][::-1]
            
            for idx, pos in enumerate(top_candidate_indices, 1):
                chunk_text = candidate_texts[pos]
                short_text = chunk_text[:150] + "..." if len(chunk_text) > 150 else chunk_text
                short_text_escaped = short_text.replace('\n', '<br>')
                
                retrieved_results_html += (
                    f"📌 <b>תוצאה {idx}:</b><br>"
                    f"• ציון סמנטי: {semantic_scores[pos]:.2f} | ציון פאזי: {candidate_fuzzy_scores[pos]:.2f}<br>"
                    f"• ציון משולב סופי: {combined_candidate_scores[pos]:.2f}<br>"
                    f"<code>{short_text_escaped}</code><br><br>"
                )
        else:
            retrieval_status = "💡 שלח שאלה כדי לראות את האלגוריתם המשולב והחסין בפעולה."

        # החזרת כל חמשת השלבים בטור
        return jsonify({
            "response": f"🚧 <b>בדיקת שלבים טורית - שלב 5 המתוקן והחסין באוויר!</b><br><br>"
                        f"🔑 <b>1. בדיקת מפתח סביבה:</b><br>• {api_key_status}<br><br>"
                        f"🤖 <b>2. בדיקת קריאה לג'ימיני (Flash):</b><br>• {gemini_response_status}<br><br>"
                        f"📋 <b>3. ניתוח מסמך הנהלים (Terminal.txt):</b><br>"
                        f"• חולצו בהצלחה מפרק 2: <b>{len(chunks_chapter_2)}</b> שאלות ותשובות.<br>"
                        f"• חולצו בהצלחה מפרק 3: <b>{len(chunks_chapter_3)}</b> דפי מערכת.<br>"
                        f"📊 <b>סך הכל יחידות מידע מוכנות בזיכרון:</b> {total_chunks} יחידות.<br><br>"
                        f"🧠 <b>5. מנוע RAG משולב וחסין (סינון פאזי מוקדם ל-30 מועמדים + סמנטי):</b><br>"
                        f"• סטטוס: {retrieval_status}<br><br>"
                        f"{retrieved_results_html}"
        })

    except Exception as e:
        return jsonify({"response": f"❌ שגיאה כללית במהלך הרצת השלבים: {e}"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
