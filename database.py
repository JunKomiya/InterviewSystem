import sqlite3
import os
from datetime import datetime

DB_NAME = "interview_system.db"

def get_connection():
    return sqlite3.connect(DB_NAME)

def init_db():
    """データベースの初期化と必要なテーブルの作成を行います。"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 質問データ用テーブル (既存と互換)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        industry TEXT,
        question_text TEXT
    )
    ''')
    
    # 簡易面接ログテーブル (既存と互換)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS interview_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_name TEXT,
        interview_count INTEGER,
        feedback TEXT
    )
    ''')
    
    # 詳細な面接結果保存用テーブル (新規)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS interview_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_name TEXT,
        job_type TEXT,
        overall_score INTEGER,
        rank TEXT,
        consistency_score INTEGER,
        content_quality_score INTEGER,
        eye_contact_score INTEGER,
        eval_text TEXT,
        user_answer_1 TEXT,
        user_answer_2 TEXT,
        created_at TEXT
    )
    ''')
    
    # サンプルデータの追加（questionsが空の場合のみ）
    cursor.execute("SELECT COUNT(*) FROM questions")
    if cursor.fetchone()[0] == 0:
        sample_questions = [
            ("IT", "学生時代に最も力を入れたプログラミング開発について教えてください。"),
            ("IT", "チーム開発で意見が衝突したとき、どのように解決しましたか？"),
            ("製造", "当社のものづくりに対する姿勢のどこに魅力を感じましたか？"),
            ("共通", "あなたの最大の強みと、それを表す具体的なエピソードを教えてください。")
        ]
        cursor.executemany("INSERT INTO questions (industry, question_text) VALUES (?, ?)", sample_questions)
        
    conn.commit()
    conn.close()

def save_interview_result(user_name: str, job_type: str, overall_score: int, rank: str, 
                          consistency_score: int, content_quality_score: int, eye_contact_score: int, 
                          eval_text: str, user_answer_1: str, user_answer_2: str) -> bool:
    """面接練習結果をDBに保存します。"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute('''
        INSERT INTO interview_results (
            user_name, job_type, overall_score, rank, 
            consistency_score, content_quality_score, eye_contact_score, 
            eval_text, user_answer_1, user_answer_2, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_name, job_type, overall_score, rank,
            consistency_score, content_quality_score, eye_contact_score,
            eval_text, user_answer_1, user_answer_2, created_at
        ))
        
        # 互換性テーブル(interview_logs)にも記録
        cursor.execute("SELECT COUNT(*) FROM interview_logs WHERE user_name = ?", (user_name,))
        count = cursor.fetchone()[0] + 1
        
        cursor.execute('''
        INSERT INTO interview_logs (user_name, interview_count, feedback)
        VALUES (?, ?, ?)
        ''', (user_name, count, f"総合判定: {rank} ({overall_score}点)\n{eval_text[:100]}..."))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB Error] Failed to save result: {e}")
        return False

def get_interview_history(user_name: str) -> list[dict]:
    """特定のユーザーの過去の面接履歴を取得します（最新順）。"""
    try:
        conn = get_connection()
        # 列名でアクセスできるように辞書型で取得
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
        SELECT * FROM interview_results 
        WHERE user_name = ? 
        ORDER BY created_at DESC
        ''', (user_name,))
        
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        conn.close()
        return results
    except Exception as e:
        print(f"[DB Error] Failed to fetch history: {e}")
        return []

# データベース初期化の実行
init_db()
