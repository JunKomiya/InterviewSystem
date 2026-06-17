import sqlite3

# 1. データベースファイルへの接続（ファイルがなければ自動で作られます）
DB_NAME = "interview_system.db"
conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

print(f"データベース '{DB_NAME}' に接続しました。")

# 2. テーブルの作成
# 質問データ用のテーブル
cursor.execute('''
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    industry TEXT,         -- 業界 (IT, 製造, 金融 など)
    question_text TEXT     -- 質問内容
)
''')

# 面接結果・フィードバック用のテーブル
cursor.execute('''
CREATE TABLE IF NOT EXISTS interview_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name TEXT,        -- 使用者名
    interview_count INTEGER, -- 何回目の面接か
    feedback TEXT          -- 前回フィードバック内容
)
''')
conn.commit()
print("テーブルの作成（または確認）が完了しました。")

# 3. テストデータの挿入（すでにデータがある場合はスキップする仕組み）
cursor.execute("SELECT COUNT(*) FROM questions")
if cursor.fetchone()[0] == 0:
    sample_questions = [
        ("IT", "学生時代に最も力を入れたプログラミング開発について教えてください。"),
        ("IT", "チーム開発で意見が衝突したとき、どのように解決しましたか？"),
        ("製造", "当社のものづくりに対する姿勢のどこに魅力を感じましたか？"),
        ("共通", "あなたの最大の強みと、それを表す具体的なエピソードを教えてください。")
    ]
    cursor.executemany("INSERT INTO questions (industry, question_text) VALUES (?, ?)", sample_questions)
    
    # テスト用の過去のフィードバックも1つ入れておく
    cursor.execute("INSERT INTO interview_logs (user_name, interview_count, feedback) VALUES (?, ?, ?)", 
                   ("プロト 太郎", 1, "結論ファーストで話すことを意識してください。視線がやや下を向きがちです。"))
    
    conn.commit()
    print("サンプルのテストデータを挿入しました。")

# 4. データの抽出テスト（例：IT業界の質問だけを引っ張ってくる）
print("\n--- 【テスト】IT業界の質問を検索します ---")
target_industry = "IT"
cursor.execute("SELECT question_text FROM questions WHERE industry = ? OR industry = '共通'", (target_industry,))
rows = cursor.fetchall()

for i, row in enumerate(rows, 1):
    print(f"質問 {i}: {row[0]}")

# 5. データの抽出テスト（例：プロト太郎さんの過去のフィードバックを取得する）
print("\n--- 【テスト】プロト太郎さんの前回のフィードバックを検索します ---")
cursor.execute("SELECT feedback FROM interview_logs WHERE user_name = ? ORDER BY interview_count DESC LIMIT 1", ("プロト 太郎",))
last_feedback = cursor.fetchone()
if last_feedback:
    print(f"前回のフィードバック: {last_feedback[0]}")

# 接続を閉じる
conn.close()