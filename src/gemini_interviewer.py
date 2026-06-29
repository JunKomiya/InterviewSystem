import os
import json
from google import genai
from google.genai import types

class GeminiInterviewer:
    def __init__(self, api_key: str = "", mode: str = "AI"):
        # APIキーの前後の空白や改行をクレンジング
        self.api_key = api_key.strip() if api_key else ""
        self.mode = mode  # "AI" または "MOCK"
        
        # 指定がない場合は環境変数から取得してクレンジング
        if not self.api_key:
            self.api_key = os.environ.get("GEMINI_API_KEY", "").strip()
            
        self.client = None
        # AIモードの場合のみクライアントを初期化
        if self.mode == "AI":
            try:
                if self.api_key:
                    self.client = genai.Client(api_key=self.api_key)
                else:
                    self.client = genai.Client()
            except Exception as e:
                # 初期化失敗時は自動的にモックモードに切り替え
                print(f"[GeminiInterviewer] Client initialization failed. Switching to MOCK mode. Error: {e}")
                self.mode = "MOCK"

    def verify_connection(self) -> tuple[bool, str]:
        """APIの接続テストを行い、疎通確認結果を返します。モックモードの場合は常に成功を返します。"""
        if self.mode == "MOCK":
            return True, "モックモード（接続テストは常に成功します）"
            
        if not self.client:
            return False, "APIクライアントが初期化されていません。APIキーを確認してください。"
            
        try:
            response = self.client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents="PING"
            )
            if response.text:
                return True, f"接続成功! モデル (gemini-3.1-flash-lite) が利用可能です。\n(応答例: {response.text.strip()[:60]}...)"
            return False, "APIからの応答が空でした。"
        except Exception as e:
            error_msg = str(e)
            try:
                if self.client:
                    models = self.client.models.list()
                    model_names = [m.name for m in models]
                    print(f"[DEBUG] Available models: {model_names}")
            except Exception as le:
                print(f"[DEBUG] Failed to list models: {le}")
                
            if "503" in error_msg or "UNAVAILABLE" in error_msg:
                return False, "ERROR 503: Gemini APIは現在一時的に高負荷なため、利用できません。時間をおいて再試行してください。"
            elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                return False, "ERROR 429: APIキーの利用制限（クォータ）を超過しました。無料枠の上限に達した可能性があります。"
            elif "API_KEY_INVALID" in error_msg or "invalid" in error_msg.lower() and "key" in error_msg.lower():
                return False, "ERROR 400: APIキーが無効であるか、形式が正しくありません。Google AI Studioのキーを正確に入力してください。"
            return False, f"接続エラーが発生しました: {error_msg}"

    def generate_first_question(self, es_data: dict) -> str:
        """エントリーシート(ES)情報を分析し、最初の質問を生成します。"""
        real_name = es_data.get("name", "").strip()
        masked_es_data, _ = self._mask_data(es_data)
        
        if self.mode == "MOCK":
            res = self._mock_first_question(masked_es_data)
            return self._unmask_data(res, real_name)
            
        system_instruction = (
            "あなたは優秀な企業の採用面接官（名前：ナナミ）です。学生のエントリーシート（ES）情報と志望職種を読み、本番の面接の冒頭として最も自然で、リアルな最初の質問を1つ生成してください。\n\n"
            "【面接官のペルソナ】\n"
            "- 口調: 丁寧でプロフェッショナルですが、学生の緊張をほぐすような温かみのあるトーン（「〜ですね」「〜でしょうか？」など）。\n"
            "- 振る舞い: ガチガチの定型文ではなく、人間の面接官が口頭で話すような自然なフレーズを意識してください。\n\n"
            "【質問の生成ルール】\n"
            "1. 最初に学生の名前を呼び、面接を始める挨拶（「本日はよろしくお願いします」など）を自然に含めてください。\n"
            "2. ESの内容（技術スキルや経験工程）を質問文の中で過剰に説明（要約）しすぎず、あくまで学生自身に口から説明してもらうための呼び水となる質問にしてください。\n"
            "3. 最初の質問では「簡単な自己紹介」と、それに続けて「今回アピールしたい自身の強みや経歴の概要」を簡潔に話すよう促してください。\n\n"
            "出力フォーマットは必ず以下のJSONフォーマットのみにしてください（他の余計な文は一切含めないでください）：\n"
            "{\n"
            '    "question": "最初の質問文"\n'
            "}"
        )
        prompt = json.dumps(masked_es_data, ensure_ascii=False)
        
        try:
            response_text = self._call_api(system_instruction, prompt)
            res_json = json.loads(response_text)
            question = res_json.get("question", "")
            return self._unmask_data(question, real_name)
        except Exception as e:
            print(f"[GeminiInterviewer] Error in generate_first_question: {e}. Falling back to MOCK.")
            res = self._mock_first_question(masked_es_data)
            return self._unmask_data(res, real_name)

    def generate_deep_dive_question(self, es_data: dict, conversation_log: list) -> tuple[str, str]:
        """対話ログとESデータを元に、次の深掘り質問とリアクションを生成します。"""
        real_name = es_data.get("name", "").strip()
        masked_es_data, masked_log = self._mask_data(es_data, conversation_log)
        
        if self.mode == "MOCK":
            intro, q = self._mock_deep_dive_question(masked_es_data, masked_log)
            return self._unmask_data(intro, real_name), self._unmask_data(q, real_name)
            
        system_instruction = (
            "あなたは企業の採用面接官（名前：ナナミ）です。学生のエントリーシート（ES）情報、および【これまでの対話ログ】を深く読み込み、文脈を完全に理解した上で、次の「深掘り質問」を1つ生成してください。\n\n"
            "【面接官（ナナミ）の対話ルール】\n"
            "- テンプレート感の排除: 毎回答に対して「素晴らしいですね」「ありがとうございます」と同じような褒め言葉から始めるのは絶対に避けてください。\n"
            "- リアルな相槌: 学生の回答内容に応じて、「なるほど、〇〇という部分に注力されたのですね」「〇〇という技術を使われた背景が気になりました」など、相手の発言を自然に受け止める相槌（クッション言葉）にしてください。\n"
            "- 深掘りの視点: 回答の曖昧な部分、専門用語、あるいは「なぜその行動をとったのか（動機）」「直面した困難とそれをどう乗り越えたか（再現性）」に焦点を当て、1回につき1つの明確な質問を投げかけてください。\n\n"
            "【出力フォーマット】\n"
            "システム側で制御するため、以下のJSONフォーマットのみで出力してください（他の余計な文は一切含めないでください）。\n"
            "※「feedback_intro」と「question」をそのまま繋げて表示しても、1人の人間が自然に話している地続きの文章になるように記述してください。\n\n"
            "{\n"
            '    "feedback_intro": "学生の発言に対する自然な相槌・共感・興味の示し方（1〜2文。毎回答同じパターンにならないように）",\n'
            '    "question": "文脈を踏まえた、次に投げるべき具体的な深掘り質問（1文）"\n'
            "}"
        )
        prompt = json.dumps({
            "es_data": masked_es_data,
            "conversation_log": masked_log
        }, ensure_ascii=False)
        
        try:
            response_text = self._call_api(system_instruction, prompt)
            res_json = json.loads(response_text)
            intro = res_json.get("feedback_intro", "")
            q = res_json.get("question", "")
            return self._unmask_data(intro, real_name), self._unmask_data(q, real_name)
        except Exception as e:
            print(f"[GeminiInterviewer] Error in generate_deep_dive_question: {e}. Falling back to MOCK.")
            intro, q = self._mock_deep_dive_question(masked_es_data, masked_log)
            return self._unmask_data(intro, real_name), self._unmask_data(q, real_name)

    def generate_evaluation_report(self, es_data: dict, conversation_log: list) -> dict:
        """面接の全対話ログを元に、総合的な面接の評価レポートを生成します。"""
        real_name = es_data.get("name", "").strip()
        masked_es_data, masked_log = self._mask_data(es_data, conversation_log)
        
        if self.mode == "MOCK":
            res_dict = self._mock_evaluation_report(conversation_log)
            return self._unmask_data(res_dict, real_name)
            
        system_instruction = (
            "あなたは優秀なキャリアアドバイザー、および企業の採用面接官（名前：ナナミ）です。学生のエントリーシート（ES）情報、および【面接のすべての対話ログ】を元に、客観的かつ愛のある総合評価レポートを作成してください。\n\n"
            "【評価基準】\n"
            "1. consistency_score (0〜100点): ESに記載された技術スキル・経験工程と、実際の面接での回答内容に矛盾がないか、一貫して軸が通っているかを評価します。\n"
            "2. content_quality_score (0〜100点): エピソードの具体性。単に「やりました」だけでなく、「課題に対してどう考え、どう行動したか」がエンジニア（志望職種）として魅力的に伝わっているかを評価します。\n"
            "   - 【重要】回答の長さが極端に短い場合（目安として1回の回答が概ね50文字未満、または一言・二言だけの不十分な回答など）、どれほどESの内容と一貫していても、具体性が著しく不足していると判断し、content_quality_score を大幅に減点（最大で40点以下）してください。さらに、改善アドバイスにおいて「回答が短すぎるため、より詳細にアピールするように」という旨を優しく指摘してください。\n\n"
            "【フィードバック文章（evaluation_summary, improvement_advice）の作成に関する厳格な禁止ルール】\n"
            "1. プログラミングで利用している引数・変数・キー名（例: consistency_score, content_quality_score, overall_score, rank, conversation_log, es_data, user_answer_1, user_answer_2, などの変数名・プログラムパラメータ名）を、フィードバック文（evaluation_summary および improvement_advice）の中に絶対に含めないでください。これらはシステム内部の変数であり、学生向けの文章に露出してはいけません。\n"
            "2. コード内で使用されている数値的な判定基準（例: 「50文字未満」「40点以下」などの数値）を、フィードバック文内にそのまま記載しないでください。数値的な基準は、すべて言葉による説明（例: 「回答の長さが極端に短い」「回答の具体性が不十分」「評価が大幅に低くなる」など）に変換してください。\n\n"
            "【判定ルール】\n"
            "- 総合スコア（overall_score）は上記2つのバランスを考慮して0〜100点で算出してください。\n"
            "- ランク（rank）はスコアに応じて厳密に決定してください（S: 90以上, A: 80-89, B: 60-79, C: 59以下）。\n\n"
            "出力フォーマットは必ず以下のJSONフォーマットのみにしてください（他の余計な文は一切含めないでください）：\n"
            "{\n"
            '    "overall_score": 総合スコア（数値）,\n'
            '    "rank": "総合判定ランク（文字列：S、A、B、Cのいずれか）",\n'
            '    "consistency_score": 一貫性スコア（数値）,\n'
            '    "content_quality_score": 適切さスコア（数値）,\n'
            '    "evaluation_summary": "面接官ナナミからの総評。良かった点や、面接を通じて伝わってきた本人の強みを優しくフィードバックしてください。決してプログラム引数や数値的な閾値を含めず、自然な日本語のみで記述してください。",\n'
            '    "improvement_advice": "プロのキャリアアドバイザー視点での具体的な改善アドバイス。「次回から〇〇についてもっと具体的に話すとさらに良くなります」など、実践的な内容にしてください。こちらもプログラム引数や数値的な閾値を一切含めないようにしてください。"\n'
            "}"
        )
        prompt = json.dumps({
            "es_data": masked_es_data,
            "conversation_log": masked_log
        }, ensure_ascii=False)
        
        try:
            response_text = self._call_api(system_instruction, prompt)
            res_dict = json.loads(response_text)
            return self._unmask_data(res_dict, real_name)
        except Exception as e:
            print(f"[GeminiInterviewer] Error in generate_evaluation_report: {e}. Falling back to MOCK.")
            res_dict = self._mock_evaluation_report(conversation_log)
            return self._unmask_data(res_dict, real_name)

    def _call_api(self, system_instruction: str, prompt: str) -> str:
        """API呼び出しと例外処理の内部共通メソッド。"""
        if not self.client:
            raise RuntimeError("APIクライアントが初期化されていません。")
        response = self.client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json"
            )
        )
        return response.text

    def _mask_data(self, es_data: dict, conversation_log: list = None) -> tuple[dict, list]:
        """送信データの個人情報（名前）をプレースホルダーにマスクします。"""
        real_name = es_data.get("name", "").strip()
        masked_es_data = es_data.copy()
        if real_name:
            masked_es_data["name"] = "__CANDIDATE_NAME__"
            
        if conversation_log is None:
            return masked_es_data, []
            
        masked_log = []
        for turn in conversation_log:
            masked_turn = turn.copy()
            if real_name and "text" in masked_turn and isinstance(masked_turn["text"], str):
                masked_turn["text"] = masked_turn["text"].replace(real_name, "__CANDIDATE_NAME__")
            masked_log.append(masked_turn)
        return masked_es_data, masked_log

    def _unmask_data(self, data: any, real_name: str) -> any:
        """APIからのレスポンスデータに含まれる仮名を実名に戻します（再帰的処理）"""
        if not real_name:
            return data
        if isinstance(data, str):
            return data.replace("__CANDIDATE_NAME__", real_name)
        elif isinstance(data, dict):
            return {k: self._unmask_data(v, real_name) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._unmask_data(item, real_name) for item in data]
        return data

    # --- モックフォールバック用内部メソッド ---
    def _mock_first_question(self, es_data: dict) -> str:
        name = es_data.get("name", "学生")
        job_type = es_data.get("job_type", "開発職")
        tech_skills = es_data.get("tech_skills", "")
        return f"はじめまして、{name}さん。面接官のナナミです。本日はよろしくお願いいたします。それでは早速ですが、{job_type}の面接として自己紹介をお願いいたします。併せて、お持ちの技術スキルである「{tech_skills}」やこれまでの学習経験を含めてお話しください。"

    def _mock_deep_dive_question(self, es_data: dict, conversation_log: list) -> tuple[str, str]:
        tech_skills = es_data.get("tech_skills", "")
        selected_tech = tech_skills.split(",")[0] if tech_skills else "プログラミング"
        # Extract student's answer safely
        student_answers = [item["text"] for item in conversation_log if item.get("speaker") == "student"]
        answer_1 = student_answers[-1] if student_answers else ""
        
        feedback_intro = f"ご回答ありがとうございます。ご自身が学んでこられた「{selected_tech}」などの技術スキルを活かした取り組みについて、非常に興味深く伺いました。"
        deep_dive_txt = f"それでは、その中で特に「要件定義から実装」などの工程で、ご自身が最も困難だと感じた点と、それをどのように工夫して解決したかを教えていただけますか？"
        return feedback_intro, deep_dive_txt

    def _mock_evaluation_report(self, conversation_log: list = None) -> dict:
        # デフォルトの優秀な評価
        overall_score = 90
        rank = "A"
        consistency_score = 92
        content_quality_score = 88
        summary = "エントリーシートでアピールされていた強みと、実際の質問回答内容に強い一貫性があります。具体例も伴っており説得力があります。"
        advice = "さらに評価を高めるためには、行動の動機（なぜそれをしようと思ったのか）や、活動を通じて得られた学びをどう活かすかについて少し言及を加えると良いでしょう。"

        # 実際の会話ログから回答の長さを判定
        if conversation_log:
            student_answers = [item["text"] for item in conversation_log if item.get("speaker") == "student"]
            short_answers = [ans for ans in student_answers if len(ans.strip()) < 50]
            if short_answers:
                content_quality_score = 35
                consistency_score = min(consistency_score, 70)  # 回答が短すぎるため一貫性の評価もやや下げる
                overall_score = int((consistency_score + content_quality_score) / 2)
                
                # ランク再計算
                if overall_score >= 90:
                    rank = "S"
                elif overall_score >= 80:
                    rank = "A"
                elif overall_score >= 60:
                    rank = "B"
                else:
                    rank = "C"
                
                summary = "回答内容にESとの明らかな矛盾は見られませんが、回答文が非常に短く、アピールとしての具体性に欠けています。"
                advice = "自己紹介や深掘り質問に対する回答が短すぎます。面接官にあなたの魅力や経験がしっかりと伝わるよう、具体的な取り組みや課題へのアプローチをもっと詳しく説明するようにしてください。"

        return {
            "overall_score": overall_score,
            "rank": rank,
            "consistency_score": consistency_score,
            "content_quality_score": content_quality_score,
            "evaluation_summary": summary,
            "improvement_advice": advice
        }
