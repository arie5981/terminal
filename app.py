from flask import Flask, render_template, request, jsonify, render_template_string
import os
import re
import time
import json
import base64
import requests
import threading
from datetime import datetime
from google import genai
from google.genai import types
import markdown 

app = Flask(__name__)

# שליפת מפתחות API ומשתני סביבה
gemini_api_key = os.environ.get("GEMINI_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# הגדרה ישירה של ה-Repository שלך
GITHUB_REPO = "arie5981/terminal"

# משתנים גלובליים לנתונים
LINKS_DICTIONARY = {}   
TERMINAL_CONTENT = ""   
CACHE_NAME = None  # ישמור את המזהה הייחודי של ה-Cache בשרתי גוגל

# הגדרת נתיבים לתיקיית הדאטה ולקבצים (משמש לטעינה ראשונית בלבד)
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
CACHE_INFO_FILE = os.path.join(DATA_DIR, "cache_info.json")

# יצירת תיקיית data באופן אוטומטי בשרת אם אינה קיימת
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# הנחיות המערכת הקבועות
SYSTEM_INSTRUCTION = (
    "אתה עוזר דיגיטלי מקצועי, אדיב, ענייני וממוקד של אתר מייצגים בגביה של הביטוח הלאומי.\n"
    "תפקידך לענות בצורה ישירה וברורה על השאלה שנשאלת, מתוך הסתמכות מלאה על קובץ הנהלים המצורף למטה.\n\n"
    "🎯 חוק הניסוח הענייני, הממוקד והתפעולי:\n"
    "1. ענה בצורה עניינית וישירה. אם המשתמש שואל 'איך לבצע' פעולה מסוימת (נתיב או שלבי עבודה), התמקד אך ורק בשלבים התפעוליים המעשיים הנדרשים לביצועה.\n"
    "2. שמור על תמציות: אל תפרט תנאי סף, מגבלות חוקיות, אחוזי הפחתה, תיאור מסלולים חלופיים או הסברים תיאורטיים נלווים המופיעים בנוהל, אלא אם כן המשתמש שאל עליהם במפורש.\n"
    "3. 🔀 חוק מסלול ברירת מחדל (פיצול תהליכים): אם בנוהל מופיעים מספר מסלולים לביצוע אותה פעולה (כגון: 'עם כרטיס אשראי' / 'ללא כרטיס אשראי'):\n"
    "   - הצג אך ורק את המסלול הראשי והשכיח ביותר.\n"
    "   - בסוף התשובה הוסף שורה קצרה אחת בלבד: 'למקרים של [תיאור המקרה החריג, למשל: חוסר בכרטיס אשראי] - יש לפעול לפי [שם המסלול/הפתרון הקצר]'.\n"
    "4. שמור על טון מקצועי ואדיב. נסח את התשובה כמשפט זורם וברור ולא כמילה בודדת (לדוגמה: 'הטלפון למוקד מקצועי הוא...').\n"
    "5. ⚠️ חובה להכליל הערות קריטיות: אם בנוהל הרלוונטי מופיעה התייחסות המוגדרת כ-'חשוב!:' (או סייג מרכזי), חובה לכלול התייחסות זו בתשובה ולהדגישה (לדוגמה: '**שים לב:** אישור מרכז לא כולל אישור מילואים...').\n\n"
    "⛔ חוק איסור פרשנות והמצאת עובדות:\n"
    "1. הצמד אך ורק לעובדות הכתובות בדף הרלוונטי. אל תפרש, אל תסביר את הלוגיקה, ואל תוסיף מידע או שלבים שלא מופיעים בטקסט במפורש.\n"
    "2. ⚠️ קריטי: אל תעתיק תיאורי מיקום, הכוונות או סוגריים (כמו 'שמאל למעלה') מנוהל אחד למשנהו! הצג את נתיב הניווט (מיקום השירות) בדיוק כפי שהוא כתוב בנוהל הספציפי של השאלה הנוכחית, ללא שום תוספת פרשנית.\n"
    "3. אם המשתמש שואל אם משהו אפשרי, וקיימת דרך לבצע זאת, פתח מיד בהנחיות המעשיות לביצוע.\n\n"
    "🚫 חוק איסור שלבי כניסה והתחברות:\n"
    "1. חל איסור מוחלט לפתוח במשפטים כגון: 'היכנס לאתר', 'התחבר למערכת' וכדומה. הנחת היסוד היא שהמשתמש כבר בפנים.\n"
    "2. התחל את השלב הראשון ישירות מהפעולה המעשית הראשונה בתוך האתר.\n\n"
    "🎨 חוקי עיצוב, קריאות וריווח (Markdown):\n"
    "1. הפרדה בין סעיפים/מסלולים: חובה להפריד בין סעיפים ראשיים ברשימה באמצעות קו מפריד (---) או שורות ריקות כפולות.\n"
    "2. הזחת תבליטים (Indentation): הקפד על הזחה של 3 רווחים לפחות בתחילת שורת תבליט השייכת לסעיף ממוספר, כדי ליצור היררכיה חזותית ברורה.\n"
    "3. תמציתיות בשורת שלב: צרף את תיאור השלב באותה השורה של כותרת השלב (דוגמה: '* **שלב 1: גישה למסך** — עבור אל...').\n\n"
    "✨ חוק הדגשה והבלטה:\n"
    "1. חובה להדגיש באמצעות כוכביות כפולות (לדוגמה: **שלב 1: גישה לרשימה**) כותרות שלבים או מונחי מפתח תפעוליים חשובים (שמות כפתורים, סטטוסים, או אזהרות כמו **שים לב:**).\n\n"
    "🔗 חוקי קישורים, סוגריים מרובעים, סרטונים ומספרים:\n"
    "1. ודא שכל שם של טופס, אתר, מערכת, מוקד או כתובת מייל שמופיעים בטקסט, עטופים בדיוק בסוגריים מרובעים כפי שהם מופיעים בנהלים.\n"
    "2. 📞 מספרי טלפון/מוקד עם כוכבית: מספרי מוקד הכוללים כוכבית (כמו `6050*`) נתווסף סביבם קוד נקי בפורמט `6050*` כדי למנוע שיבושי תצוגה.\n"
    "3. 🎬 סרטוני הדרכה: אם בנוהל הרלוונטי מופיע אזכור לסרטון (כגון 'סרטון: ... [שם הסרטון]'), חובה להוסיף בסוף התשובה שורה נפרדת בדיוק בנוסח: 'סרטון הדרכה: [שם הסרטון]' תוך שמירה מדויקת על השם בתוך הסוגריים המרובעים."
)

def get_debug_mode():
    """קורא את מצב הדיבאג הנוכחי ישירות מתוך קובץ debug.txt ב-GitHub"""
    content = read_all_lines_from_github_file("data/debug.txt")
    if content and content.strip() in ["1", "0"]:
        return int(content.strip())
    return 0  # ברירת מחדל במקרה של שגיאה או קובץ ריק

def write_debug_mode_to_github(mode_value):
    """מעדכן את מצב הדיבאג בתוך קובץ debug.txt ב-GitHub על ידי דריסה מלאה"""
    return write_full_file_to_github("data/debug.txt", str(mode_value), f"🤖 מערכת דיבאג: עדכון סטטוס ל-{mode_value}")

def clean_html_for_history(text):
    """מנקה תגיות HTML מהיסטוריית השיחה בצורה בטוחה ומנועת קריסות"""
    if not text or not isinstance(text, str):
        return ""
    if "<br><hr>" in text:
        text = text.split("<br><hr>")[0]
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).strip()

def append_line_to_github_file(repo_filepath, new_line_content):
    """פונקציית עזר שמוסיפה שורה חדשה לקובץ ישירות בתוך ה-Repository ב-GitHub"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("🚨 חסרים פרטי הזדהות של GITHUB_TOKEN או GITHUB_REPO בשרת.")
        return False
        
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{repo_filepath}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        res = requests.get(url, headers=headers)
        current_content = ""
        sha = None
        
        if res.status_code == 200:
            file_data = res.json()
            sha = file_data.get("sha")
            current_content = base64.b64decode(file_data.get("content")).decode("utf-8")
        elif res.status_code == 404:
            print(f"⚠️ הקובץ {repo_filepath} לא נמצא ב-GitHub. ננסה ליצור אותו.")
        else:
            print(f"⚠️ שגיאה במשיכת קובץ מ-GitHub (סטטוס {res.status_code}): {res.text}")
            return False

        if current_content and not current_content.endswith("\n"):
            current_content += "\n"
        updated_content = current_content + new_line_content

        payload = {
            "message": f"🤖 מערכת דיבאג: עדכון אוטומטי של {repo_filepath}",
            "content": base64.b64encode(updated_content.encode("utf-8")).decode("utf-8")
        }
        if sha:
            payload["sha"] = sha
            
        put_res = requests.put(url, headers=headers, json=payload)
        return put_res.status_code in [200, 201]
            
    except Exception as e:
        print(f"🚨 שגיאה חריגה בתקשורת מול GitHub API: {e}")
        return False

def write_full_file_to_github(repo_filepath, full_content, commit_message):
    """כותבת/דורסת תוכן של קובץ מלא ב-GitHub"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return False
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{repo_filepath}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        res = requests.get(url, headers=headers)
        sha = None
        if res.status_code == 200:
            sha = res.json().get("sha")

        payload = {
            "message": commit_message,
            "content": base64.b64encode(full_content.encode("utf-8")).decode("utf-8")
        }
        if sha:
            payload["sha"] = sha

        put_res = requests.put(url, headers=headers, json=payload)
        return put_res.status_code in [200, 201]
    except Exception as e:
        print(f"🚨 שגיאה בעדכון קובץ {repo_filepath} ב-GitHub: {e}")
        return False

def read_all_lines_from_github_file(repo_filepath):
    """קורא את כל התוכן של קובץ מתוך GitHub"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return ""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{repo_filepath}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            file_data = res.json()
            return base64.b64decode(file_data.get("content")).decode("utf-8")
    except Exception as e:
        print(f"Error reading from GitHub: {e}")
    return ""

def load_terminal_data_directly():
    """טעינת הקישורים מתוך קובץ info.txt בנפרד, וטעינת הנהלים מתוך Terminal.txt"""
    global LINKS_DICTIONARY, TERMINAL_CONTENT
    
    info_path = os.path.join(DATA_DIR, 'info.txt')
    if os.path.exists(info_path):
        with open(info_path, 'r', encoding='utf-8') as f:
            info_content = f.read()
        link_matches = re.findall(r'>>([^:]+):\s*([^\s<<]+)<<', info_content)
        for name, url in link_matches:
            LINKS_DICTIONARY[name.strip()] = url.strip()

    terminal_path = os.path.join(DATA_DIR, 'Terminal.txt')
    if os.path.exists(terminal_path):
        with open(terminal_path, 'r', encoding='utf-8') as f:
            content = f.read()
        TERMINAL_CONTENT = content.replace('\r\n', '\n').replace('\r', '\n')

load_terminal_data_directly()

def get_or_create_context_cache(client):
    """מנהל את יצירת או שליפת ה-Context Cache לטווח של שעה"""
    global CACHE_NAME
    
    if not CACHE_NAME and os.path.exists(CACHE_INFO_FILE):
        try:
            with open(CACHE_INFO_FILE, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
                CACHE_NAME = saved_data.get("cache_name")
        except Exception:
            pass
    
    if CACHE_NAME:
        try:
            existing_cache = client.caches.get(name=CACHE_NAME)
            if hasattr(existing_cache, 'state') and str(existing_cache.state) not in ["STATE_ACTIVE", "ACTIVE"]:
                CACHE_NAME = None
            else:
                return existing_cache
        except Exception:
            CACHE_NAME = None

    full_cache_text = (
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"=== קובץ הנהלים הרשמי והמלא (CONTEXT) ===\n{TERMINAL_CONTENT}\n=========================================\n"
    )
    
    cache = client.caches.create(
        model='gemini-2.5-flash',
        config=types.CreateCachedContentConfig(
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=full_cache_text)])],
            ttl="1200s"
