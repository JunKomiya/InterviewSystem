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

    def generate_case_intro(self, es_data: dict) -> str:
        """募集案件情報（job_type）を基に、案件説明と質問の呼びかけ文を生成します。"""
        real_name = es_data.get("name", "").strip()
        job_type = es_data.get("job_type", "").strip()
        
        if self.mode == "MOCK":
            return self._mock_case_intro(es_data)
            
        system_instruction = (
            "あなたは優秀な企業の面談担当者（名前：ナナミ）です。募集案件情報を読み、求職者（学生・エンジニア）に対して「案件の概要と仕事内容、必須スキルなど」をわかりやすく説明してください。\n"
            "説明の最後に、「こちらの案件について、何かご不明な点や詳しく聞きたいことはありますか？」と自然に質問を促してください。\n\n"
            "【面談担当者のペルソナ】\n"
            "- 口調: 丁寧でプロフェッショナルですが、学生の緊張をほぐすような温かみのあるトーン（「〜ですね」「〜でしょうか？」など）。\n"
            "- 振る舞い: ガチガチの定型文ではなく、人間の面談担当者が口頭で話すような自然なフレーズを意識してください。\n\n"
            "出力フォーマットは必ず以下のJSONフォーマットのみにしてください（他の余計な文は一切含めないでください）：\n"
            "{\n"
            '    "intro": "案件説明と呼びかけの文章"\n'
            "}"
        )
        prompt = json.dumps({"job_type": job_type}, ensure_ascii=False)
        
        try:
            response_text = self._call_api(system_instruction, prompt)
            res_json = json.loads(response_text)
            intro = res_json.get("intro", "")
            return self._unmask_data(intro, real_name)
        except Exception as e:
            print(f"[GeminiInterviewer] Error in generate_case_intro: {e}. Falling back to MOCK.")
            return self._mock_case_intro(es_data)

    def generate_case_qa_reply(self, es_data: dict, user_question: str) -> tuple[str, str]:
        """案件に対するユーザーからの質問に回答し、自己紹介（経歴説明）を促します。"""
        real_name = es_data.get("name", "").strip()
        job_type = es_data.get("job_type", "").strip()
        
        if self.mode == "MOCK":
            return self._mock_case_qa_reply(es_data, user_question)
            
        system_instruction = (
            "あなたは優秀な企業の面談担当者（名前：ナナミ）です。募集案件情報と、求職者から寄せられた質問内容を読み、面談担当者として誠実かつ丁寧に回答してください。\n"
            "回答の後に続けて、「それでは次に、ご自身のこれまでの経歴や自己PR、今回アピールしたい強みについて簡潔に説明をお願いいたします」と促してください。\n\n"
            "【出力フォーマット】\n"
            "システム側で制御するため、以下のJSONフォーマットのみで出力してください（他の余計な文は一切含めないでください）。\n"
            "※「reply」と「next_prompt」を繋げて表示しても、自然な地続き of 文章になるように記述してください。\n\n"
            "{\n"
            '    "reply": "ユーザーの質問に対する回答（1〜2文）",\n'
            '    "next_prompt": "経歴説明を促す言葉（1文）"\n'
            "}"
        )
        prompt = json.dumps({
            "job_type": job_type,
            "user_question": user_question
        }, ensure_ascii=False)
        
        try:
            response_text = self._call_api(system_instruction, prompt)
            res_json = json.loads(response_text)
            reply = res_json.get("reply", "")
            next_prompt = res_json.get("next_prompt", "")
            return self._unmask_data(reply, real_name), self._unmask_data(next_prompt, real_name)
        except Exception as e:
            print(f"[GeminiInterviewer] Error in generate_case_qa_reply: {e}. Falling back to MOCK.")
            return self._mock_case_qa_reply(es_data, user_question)

    def generate_deep_dive_question(self, es_data: dict, conversation_log: list) -> tuple[str, str]:
        """対話ログとESデータを元に、次の深掘り質問とリアクションを生成します。"""
        real_name = es_data.get("name", "").strip()
        masked_es_data, masked_log = self._mask_data(es_data, conversation_log)
        
        if self.mode == "MOCK":
            intro, q = self._mock_deep_dive_question(masked_es_data, masked_log)
            return self._unmask_data(intro, real_name), self._unmask_data(q, real_name)
            
        system_instruction = (
            "あなたは優秀な企業の面談担当者（名前：ナナミ）です。学生のスキルシート情報、募集案件情報、および【これまでの対話ログ】を深く読み込み、文脈を完全に理解した上で、次の「深掘り質問」を1つ生成してください。\n\n"
            "【質問生成の最重要ルール】\n"
            "1. **スキルと案件の照合**: スキルシートの経歴・経験技術と、案件情報の必須スキルを照合してください。\n"
            "2. **一致点・不足点の分析**: 案件内容と利用者の経験が一致している強み、または不足している弱みに焦点を当ててください。\n"
            "3. **深掘りされやすいポイントの選定**: 技術面談において特に深掘りされやすい経歴やスキルについて、具体的に問いかけてください。\n"
            "4. ESの内容（技術スキルや経験工程）を過剰に説明（要約）しすぎず、あくまで学生自身の口から引き出すための呼び水となる質問（1文）にしてください。\n\n"
            "【面談担当者（ナナミ）の対話ルール】\n"
            "- テンプレート感の排除: 毎回答に対して「素晴らしいですね」「ありがとうございます」と同じような褒め言葉から始めるのは避けてください。\n"
            "- リアルな相槌: 学生の経歴説明内容に応じて、「なるほど、〇〇という領域で開発されてきたのですね」「〇〇という技術を使われた背景が気になりました」など、自然に受け止める相槌（クッション言葉）にしてください。\n\n"
            "【出力フォーマット】\n"
            "システム側で制御するため、以下のJSONフォーマットのみで出力してください（他の余計な文は一切含めないでください）。\n"
            "※「feedback_intro」と「question」を繋げて表示しても、1人の人間が自然に話している地続きの文章になるように記述してください。\n\n"
            "{\n"
            '    "feedback_intro": "学生の発言に対する自然な相槌・興味の示し方（1〜2文）",\n'
            '    "question": "一致・不足点や深掘りポイントに基づいた、次に投げるべき具体的な深掘り質問（1文）"\n'
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

    def generate_final_qa_reply(self, es_data: dict, user_question: str) -> str:
        """最後の質問（逆質問）に回答し、面談を締めくくります。"""
        real_name = es_data.get("name", "").strip()
        
        if self.mode == "MOCK":
            return self._mock_final_qa_reply(es_data, user_question)
            
        system_instruction = (
            "あなたは優秀な企業の面談担当者（名前：ナナミ）です。求職者（学生・エンジニア）から面談の最後に寄せられた質問（逆質問）を読み、丁寧に回答した上で、本日の面談を温かく締めくくる挨拶を行ってください。\n\n"
            "【面談担当者のペルソナ】\n"
            "- 口調: 丁寧でプロフェッショナルかつ温かみのあるトーン。\n"
            "- 振る舞い: 質問への回答を終えた後、「本日はお時間をいただきありがとうございました。結果については後ほどご連絡いたします」といった面談終了の言葉を含めてください。\n\n"
            "出力フォーマットは必ず以下のJSONフォーマットのみにしてください（他の余計な文は一切含めないでください）：\n"
            "{\n"
            '    "reply": "逆質問への回答と締めの挨拶の文章"\n'
            "}"
        )
        prompt = json.dumps({"user_question": user_question}, ensure_ascii=False)
        
        try:
            response_text = self._call_api(system_instruction, prompt)
            res_json = json.loads(response_text)
            reply = res_json.get("reply", "")
            return self._unmask_data(reply, real_name)
        except Exception as e:
            print(f"[GeminiInterviewer] Error in generate_final_qa_reply: {e}. Falling back to MOCK.")
            return self._mock_final_qa_reply(es_data, user_question)

    def generate_evaluation_report(self, es_data: dict, conversation_log: list) -> dict:
        """面接の全対話ログを元に、総合的な面接の評価レポートを生成します。"""
        real_name = es_data.get("name", "").strip()
        masked_es_data, masked_log = self._mask_data(es_data, conversation_log)
        
        if self.mode == "MOCK":
            res_dict = self._mock_evaluation_report(conversation_log)
            return self._unmask_data(res_dict, real_name)
            
        system_instruction = (
            "あなたは優秀なキャリアアドバイザー、および企業の面談担当者（名前：ナナミ）です。学生のスキルシート情報、および【面接のすべての対話ログ】を元に、客観的かつ愛のある総合評価レポートを作成してください。\n\n"
            "【評価基準】\n"
            "1. consistency_score (0〜100点): 対話の一貫性と適切さを評価します。\n"
            "   - **相手が求めている回答とずれていないか**：質問の意図・文脈に正しく沿って対話ができているかを重視して評価してください。\n"
            "   - **専門用語のわかりやすい説明**：現場独自の用語や一般的でない用語（専門用語・社内用語など）をそのまま使わず、相手に伝わるように丁寧に説明できているかを評価してください。\n"
            "   - スキルシートに記載された内容と、実際の面談中の回答内容に矛盾がないかも合わせて評価します。\n"
            "2. content_quality_score (0〜100点): 回答のエピソードの品質や言葉遣いを評価します。\n"
            "   - **回答の具体性**：単に「やれました」「経験があります」だけでなく、「直面した課題、具体的な行動、得られた成果や学び」が具体的にアピールできているかを評価してください。\n"
            "   - **社会人として適切な言葉遣い**：面談の場としてふさわしい、適切な敬語・謙譲語やプロフェッショナルな言葉遣いになっているかを評価してください。\n"
            "   - 【重要】回答の長さが極端に短い場合（目安として1回の回答が概ね50文字未満、または一言・二言だけの不十分な回答など）は、具体性が著しく不足していると判断し、content_quality_score を大幅に減点（最大で40点以下）してください。\n\n"
            "【フィードバック文章（evaluation_summary, improvement_advice）の作成に関する厳格な禁止ルール】\n"
            "1. プログラミングで利用している引数・変数・キー名（例: consistency_score, content_quality_score, overall_score, rank, conversation_log, es_data, user_answer_1, user_answer_2, などの変数名・プログラムパラメータ名）を、フィードバック文（evaluation_summary および improvement_advice）の中に絶対に含めないでください。これらはシステム内部の変数であり、学生向けの文章に露出してはいけません。\n"
            "2. コード内で使用されている数値的な判定基準（例: 「50文字未満」「40点以下」などの数値）を、フィードバック文内にそのまま記載しないでください。数値的な基準は、すべて言葉による説明（例: 「回答の長さが極端に短い」「回答の具体性が不十分」「評価が大幅に低くなる」など）に変換してください。\n\n"
            "【判定ルール】\n"
            "- 総合スコア（overall_score）は上記2つのバランスを考慮して0〜100点で算出してください。\n"
            "- ランク（rank）はスコアに応じて決定してください（S: 90以上, A: 80-89, B: 60-79, C: 59以下）。\n\n"
            "出力フォーマットは必ず以下のJSONフォーマットのみにしてください（物理的な余計な文は一切含めないでください）：\n"
            "{\n"
            '    "overall_score": 総合スコア（数値）,\n'
            '    "rank": "総合判定ランク（文字列：S、A、B、Cのいずれか）",\n'
            '    "consistency_score": 一貫性スコア（数値）,\n'
            '    "content_quality_score": 適切さスコア（数値）,\n'
            '    "evaluation_summary": "面談担当者ナナミからの総評。良かった点や、面談を通じて伝わってきた本人の強みを優しくフィードバックしてください。特に指定された評価観点（意図の合致、言葉遣い、用語の説明）の良かった点を自然な日本語で含めてください。内部の変数や数値基準は一切含めないでください。",\n'
            '    "improvement_advice": "プロのキャリアアドバイザー視点での具体的な改善アドバイス。指定された評価観点（回答のズレ、具体性、言葉遣い、専門用語の説明）の中で不足していたポイントを「次回から〇〇についてもっと具体的に話すとさらに良くなります」など、実践的なアドバイスにしてください。こちらも内部変数や数値基準は一切含めないようにしてください。"\n'
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
    def _mock_case_intro(self, es_data: dict) -> str:
        name = es_data.get("name", "求職者")
        job_type = es_data.get("job_type", "開発案件")
        return (
            f"はじめまして、面談担当者のナナミです。本日はよろしくお願いいたします。\n\n"
            f"それではまず、今回の案件について簡単にご説明いたします。\n"
            f"今回のポジションは『{job_type}』の開発案件となります。仕事内容は、フロントエンドからバックエンドまでの設計・開発に携わっていただくポジションです。必須スキルとしてPythonやJavaScriptの実務開発経験、およびチーム開発でのGit使用経験を想定しております。\n\n"
            f"こちらの案件内容について、何かご不明な点や詳しく聞いておきたいことはございますか？"
        )

    def _mock_case_qa_reply(self, es_data: dict, user_question: str) -> tuple[str, str]:
        reply = (
            f"ご質問ありがとうございます。開発の体制についてですね。現在はメンバー5名前後のチームでアジャイル開発を行っており、GitHubを用いたプルリクエストベースでコードレビューを実施しながら進めております。コミュニケーションも活発で、比較的意見が通りやすい環境です。"
        )
        next_prompt = (
            f"それでは次に、ご自身のこれまでの経歴や自己PR、今回特にアピールしたい強みについて簡潔に説明をお願いいたします。"
        )
        return reply, next_prompt

    def _mock_deep_dive_question(self, es_data: dict, conversation_log: list) -> tuple[str, str]:
        tech_skills = es_data.get("tech_skills", "")
        selected_tech = tech_skills.split(",")[0] if tech_skills else "プログラミング"
        
        student_answers = [item["text"] for item in conversation_log if item.get("speaker") == "student"]
        answer_1 = student_answers[-1] if student_answers else ""
        
        feedback_intro = f"ご回答ありがとうございます。ご自身が学んでこられた「{selected_tech}」などの技術スキルを活かした取り組みについて、非常に興味深く伺いました。"
        deep_dive_txt = f"それでは、その中で特に「要件定義から実装」などの工程で、ご自身が最も困難だと感じた点と、それをどのように工夫して解決したかを教えていただけますか？"
        return feedback_intro, deep_dive_txt

    def _mock_final_qa_reply(self, es_data: dict, user_question: str) -> str:
        name = es_data.get("name", "求職者")
        return (
            f"ご質問ありがとうございます。面談後の選考フローについてですね。今回の面談の後、選考結果は1週間以内にメールにてご連絡差し上げます。その次は、弊社の開発リーダーを含めた二次面談を予定しております。\n\n"
            f"本日はお忙しい中、貴重なお時間をいただき誠にありがとうございました。{name}さんとお話しできて大変有意義でした。それでは、本日の面談は以上で終了とさせていただきます。お疲れ様でした！"
        )

    def _mock_evaluation_report(self, conversation_log: list = None) -> dict:
        overall_score = 90
        rank = "A"
        consistency_score = 92
        content_quality_score = 88
        summary = "面談でのやり取りにおいて、こちらの質問意図を正確に汲み取った明確な回答が得られました。言葉遣いも非常に丁寧で、現場用語を使う際も分かりやすい言葉に置き換えて説明されており、コミュニケーション力が高く評価できます。"
        advice = "さらに評価を高めるためには、ご自身の経歴を説明される際、課題に対してどのようにアプローチしたかという行動の具体性をより肉付けして話すように意識すると良いでしょう。"

        if conversation_log:
            student_answers = [item["text"] for item in conversation_log if item.get("speaker") == "student"]
            short_answers = [ans for ans in student_answers if len(ans.strip()) < 50]
            if short_answers:
                content_quality_score = 35
                consistency_score = min(consistency_score, 70)
                overall_score = int((consistency_score + content_quality_score) / 2)
                
                if overall_score >= 90:
                    rank = "S"
                elif overall_score >= 80:
                    rank = "A"
                elif overall_score >= 60:
                    rank = "B"
                else:
                    rank = "C"
                
                summary = "会話のキャッチボールにおいて丁寧な姿勢は見られましたが、回答が短く具体性に欠けている点が見られました。"
                advice = "質問への回答が極端に短いため、アピールが伝わりにくくなっています。特に自己紹介や経歴紹介では、行ったことの背景や課題へのアプローチをより具体的に説明し、専門用語を用いる場合は面談相手に伝わりやすい補足を加えるように工夫してみてください。"

        return {
            "overall_score": overall_score,
            "rank": rank,
            "consistency_score": consistency_score,
            "content_quality_score": content_quality_score,
            "evaluation_summary": summary,
            "improvement_advice": advice
        }
