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
                model="gemini-2.5-flash",
                contents="PING"
            )
            if response.text:
                return True, f"接続成功! モデル (gemini-2.5-flash) が利用可能です。\n(応答例: {response.text.strip()[:60]}...)"
            return False, "APIからの応答が空でした。"
        except Exception as e:
            error_msg = str(e)
            if "503" in error_msg or "UNAVAILABLE" in error_msg:
                return False, "ERROR 503: Gemini APIは現在一時的に高負荷なため、利用できません。時間をおいて再試行してください。"
            elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                return False, "ERROR 429: APIキーの利用制限（クォータ）を超過しました。無料枠の上限に達した可能性があります。"
            elif "400" in error_msg or "API_KEY_INVALID" in error_msg or "invalid" in error_msg.lower():
                return False, "ERROR 400: APIキーが無効であるか、形式が正しくありません。Google AI Studioのキーを正確に入力してください。"
            return False, f"接続エラーが発生しました: {error_msg}"

    def generate_first_question(self, name: str, job_type: str, es_pr: str) -> str:
        """エントリーシート(ES)と志望職種を分析し、最初の質問を生成します。"""
        if self.mode == "MOCK":
            return self._mock_first_question(name, job_type)
            
        system_instruction = (
            "あなたは優秀な企業の採用面接官（名前：ナナミ）です。学生のエントリーシート（ES）と志望職種を読み、本番の面接と同じクオリティの最初の質問を1つ生成してください。\n"
            "職種（特に技術職などの場合）に応じた具体的な内容を含めてください。\n"
            "最初の質問では、まず自己紹介を促し、続いてESに書かれた強みや経歴について簡潔に説明するように求めてください。\n\n"
            "出力フォーマットは必ず以下のJSONフォーマットのみにしてください（他の余計な文は一切含めないでください）：\n"
            "{\n"
            '    "question": "最初の質問文"\n'
            "}"
        )
        prompt = json.dumps({
            "name": name,
            "job_type": job_type,
            "es_pr": es_pr
        }, ensure_ascii=False)
        
        try:
            response_text = self._call_api(system_instruction, prompt)
            res_json = json.loads(response_text)
            return res_json.get("question", "")
        except Exception as e:
            print(f"[GeminiInterviewer] Error in generate_first_question: {e}. Falling back to MOCK.")
            return self._mock_first_question(name, job_type)

    def generate_deep_dive_question(self, es_pr: str, job_type: str, question_1: str, answer_1: str) -> tuple[str, str]:
        """第一問の回答内容を深く掘り下げる深掘り質問と、回答へのリアクションを生成します。"""
        if self.mode == "MOCK":
            return self._mock_deep_dive_question(es_pr, answer_1)
            
        system_instruction = (
            "あなたは企業の採用面接官（名前：ナナミ）です。学生のエントリーシート（ES）、志望職種、第一問の質問、およびそれに対する学生の回答を読み、回答内容を深く掘り下げる「深掘り質問」を1つ生成してください。\n"
            "回答の中で曖昧な部分や、特に強調されている専門用語（例: 開発言語、手法など）に焦点を当て、具体的にどのような行動をとったか、あるいはどのような困難を克服したかを聞いてください。\n"
            "また、回答に対する面接官らしい一言リアクション（肯定・共感・技術や経験に対する興味）を添えてください。\n\n"
            "出力フォーマットは必ず以下のJSONフォーマットのみにしてください（他の余計な文は一切含めないでください）：\n"
            "{\n"
            '    "feedback_intro": "回答への一言リアクション・評価（1〜2文）",\n'
            '    "question": "深掘り質問の文章"\n'
            "}"
        )
        prompt = json.dumps({
            "es_pr": es_pr,
            "job_type": job_type,
            "question_1": question_1,
            "answer_1": answer_1
        }, ensure_ascii=False)
        
        try:
            response_text = self._call_api(system_instruction, prompt)
            res_json = json.loads(response_text)
            return res_json.get("feedback_intro", ""), res_json.get("question", "")
        except Exception as e:
            print(f"[GeminiInterviewer] Error in generate_deep_dive_question: {e}. Falling back to MOCK.")
            return self._mock_deep_dive_question(es_pr, answer_1)

    def generate_evaluation_report(self, es_pr: str, job_type: str, question_1: str, answer_1: str, question_2: str, answer_2: str) -> dict:
        """面接の全対話ログを元に、総合的な面接の評価レポートを生成します。"""
        if self.mode == "MOCK":
            return self._mock_evaluation_report()
            
        system_instruction = (
            "あなたは優秀なキャリアアドバイザー、および企業の採用面接官（名前：ナナミ）です。学生のエントリーシート（ES）、志望職種、および面接の対話ログを元に、総合的な面接の評価レポートを作成してください。\n\n"
            "以下の項目について評価してください：\n"
            "1. consistency_score (0〜100点): 回答の一貫性。ESの内容と実際の回答が矛盾なく繋がっているか。\n"
            "2. content_quality_score (0〜100点): 回答の適切さ・具体性。エピソードの具体性や課題解決の深さ、職種へのマッチ度。\n\n"
            "評価に基づき、総合スコア（0〜100点）と総合判定ランク（S, A, B, Cのいずれか）を決定してください。\n"
            "また、全体の総評（会話の一貫性や強みがアピールできていた点へのフィードバック）と、今後の具体的な改善アドバイスを記述してください。\n\n"
            "出力フォーマットは必ず以下のJSONフォーマットのみにしてください（他の余計な文は一切含めないでください）：\n"
            "{\n"
            '    "overall_score": 総合スコア（数値）,\n'
            '    "rank": "総合判定ランク（文字列：S、A、B、Cのいずれか）",\n'
            '    "consistency_score": 一貫性スコア（数値）,\n'
            '    "content_quality_score": 適切さスコア（数値）,\n'
            '    "evaluation_summary": "面接官からの総評・フィードバック内容",\n'
            '    "improvement_advice": "具体的な改善アドバイス内容"\n'
            "}"
        )
        prompt = json.dumps({
            "es_pr": es_pr,
            "job_type": job_type,
            "conversation_log": [
                {"speaker": "interviewer", "text": question_1},
                {"speaker": "student", "text": answer_1},
                {"speaker": "interviewer", "text": question_2},
                {"speaker": "student", "text": answer_2}
            ]
        }, ensure_ascii=False)
        
        try:
            response_text = self._call_api(system_instruction, prompt)
            return json.loads(response_text)
        except Exception as e:
            print(f"[GeminiInterviewer] Error in generate_evaluation_report: {e}. Falling back to MOCK.")
            return self._mock_evaluation_report()

    def _call_api(self, system_instruction: str, prompt: str) -> str:
        """API呼び出しと例外処理の内部共通メソッド。"""
        if not self.client:
            raise RuntimeError("APIクライアントが初期化されていません。")
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json"
            )
        )
        return response.text

    # --- モックフォールバック用内部メソッド ---
    def _mock_first_question(self, name: str, job_type: str) -> str:
        return f"はじめまして、{name}さん。面接官のナナミです。本日はよろしくお願いいたします。それでは早速ですが、{job_type}の面接として、自己紹介をお願いいたします。併せて、エントリーシートに記載されたご自身の強みについてもお話しください。"

    def _mock_deep_dive_question(self, es_pr: str, answer_1: str) -> tuple[str, str]:
        keywords = ["行動力", "計画性", "リーダーシップ", "コミュニケーション", "開発", "プロトタイプ", "解決"]
        selected_kw = "行動力"
        for kw in keywords:
            if kw in es_pr or kw in answer_1:
                selected_kw = kw
                break
        feedback_intro = f"ご回答ありがとうございます。ご自身の強みである「{selected_kw}」を意識して、自発的に取り組まれている様子がよく伝わりました。"
        deep_dive_txt = f"それでは、その「{selected_kw}」を発揮した活動の中で、直面した「最も大きな困難」と、それをどのように乗り越えたかについて詳しく教えていただけますか？"
        return feedback_intro, deep_dive_txt

    def _mock_evaluation_report(self) -> dict:
        return {
            "overall_score": 88,
            "rank": "A",
            "consistency_score": 90,
            "content_quality_score": 85,
            "evaluation_summary": "エントリーシートでアピールされていた強みと、実際の質問回答内容に強い一貫性があります。具体例も伴っており説得力があります。",
            "improvement_advice": "さらに評価を高めるためには、行動の動機（なぜそれをしようと思ったのか）や、活動を通じて得られた学びをどう活かすかについて少し言及を加えると良いでしょう。"
        }
