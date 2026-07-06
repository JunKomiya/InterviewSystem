import os
import glob
import time
import pandas as pd


TEMP_DIR = "temp_assets"

def log_gaze(msg: str):
    """ログを確実にファイル出力するためのヘルパー関数"""
    try:
        with open("gaze_recorder.log", "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

def cleanup_temp_files():
    """一時ファイルフォルダ内のテンポラリアセットをクリーンアップします。"""
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    # 音声ファイル
    for f in glob.glob(os.path.join(TEMP_DIR, "temp_audio_*.mp3")):
        try:
            os.remove(f)
        except Exception:
            pass
            
    # ビデオファイル（webmとmp4）
    for ext in ["*.webm", "*.mp4"]:
        for f in glob.glob(os.path.join(TEMP_DIR, f"temp_gaze_timelapse_{ext}")):
            try:
                os.remove(f)
            except Exception:
                pass
                
    # マップ画像ファイル
    for f in glob.glob(os.path.join(TEMP_DIR, "temp_gaze_map_*.png")):
        try:
            os.remove(f)
        except Exception:
            pass

def parse_excel_skillsheet(file_obj):
    """アップロードされたExcelファイルまたはファイルパスから経歴データを抽出します。"""
    xl = pd.ExcelFile(file_obj)
    
    # 実際にデータが記入されているシートを特定
    selected_sheet = None
    for sheet in xl.sheet_names:
        df = pd.read_excel(file_obj, sheet_name=sheet, header=None)
        if len(df) > 5 and len(df.columns) > 4:
            label = str(df.iloc[5, 1]).strip()
            name_val = str(df.iloc[5, 4]).strip()
            if label == "氏名" and pd.notna(df.iloc[5, 4]) and name_val != "" and name_val != "nan" and name_val != "氏名":
                selected_sheet = sheet
                break
                
    if not selected_sheet:
        raise ValueError("指定された技術経歴書フォーマットではありません。B6セルに『氏名』ラベルが存在することを確認してください。")
            
    df = pd.read_excel(file_obj, sheet_name=selected_sheet, header=None)
    
    es_data = {
        "name": "",
        "final_academic_background": "",
        "tech_skills": "",
        "qualifications": "",
        "experienced_processes": [],
        "experienced_processes_content": "",
        "job_type": "技術職 (エンジニア)"
    }
    
    try:
        # 1. 氏名: Row 5, Col 4
        if len(df) > 5 and len(df.columns) > 4:
            es_data["name"] = str(df.iloc[5, 4]).strip() if pd.notna(df.iloc[5, 4]) else ""
            
        # 2. 最終学歴: Row 6, Col 10
        if len(df) > 6 and len(df.columns) > 10:
            es_data["final_academic_background"] = str(df.iloc[6, 10]).strip() if pd.notna(df.iloc[6, 10]) else ""
            
        # 3. 技術スキル: Row 10, Col 1
        if len(df) > 10 and len(df.columns) > 1:
            es_data["tech_skills"] = str(df.iloc[10, 1]).strip() if pd.notna(df.iloc[10, 1]) else ""
            
        # 4. 資格名: Row 10, Col 10
        if len(df) > 10 and len(df.columns) > 10:
            es_data["qualifications"] = str(df.iloc[10, 10]).strip() if pd.notna(df.iloc[10, 10]) else ""
            
        # 5. 経験工程: Rows 14 to 20
        processes = []
        processes_details = []
        process_map = {
            "要件定義": "要件定義",
            "基本設計": "基本設計",
            "詳細設計": "詳細設計",
            "製造": "実装・プログラミング",
            "UT": "テスト・単体検証",
            "IT": "テスト・単体検証",
            "保守運用": "運用保守"
        }
        
        for r in range(14, 21):
            if len(df) > r and len(df.columns) > 3:
                proc_label = str(df.iloc[r, 1]).strip()
                is_checked = str(df.iloc[r, 2]).strip() in ["〇", "○", "x", "X", "1"]
                detail = str(df.iloc[r, 3]).strip() if pd.notna(df.iloc[r, 3]) else ""
                
                if proc_label in process_map:
                    mapped_name = process_map[proc_label]
                    if is_checked:
                        if mapped_name not in processes:
                            processes.append(mapped_name)
                        if detail:
                            processes_details.append(f"・{proc_label}: {detail}")
                            
        es_data["experienced_processes"] = processes
        
        # 6. 具体的な経験内容とプロジェクト経歴
        detail_lines = []
        if processes_details:
            detail_lines.append("【工程別の具体的な担当内容】")
            detail_lines.extend(processes_details)
            
        project_lines = []
        for r in range(26, len(df)):
            if len(df.columns) > 1:
                no_val = df.iloc[r, 1]
                
                if pd.notna(no_val) and str(no_val).strip().isdigit():
                    no_str = str(no_val).strip()
                    proj_desc = str(df.iloc[r, 5]).strip() if pd.notna(df.iloc[r, 5]) else ""
                    proj_period = str(df.iloc[r, 4]).strip() if pd.notna(df.iloc[r, 4]) else ""
                    proj_role = str(df.iloc[r, 9]).strip() if pd.notna(df.iloc[r, 9]) else ""
                    proj_env_lang = str(df.iloc[r, 10]).strip() if pd.notna(df.iloc[r, 10]) else ""
                    proj_env_db = str(df.iloc[r, 11]).strip() if pd.notna(df.iloc[r, 11]) else ""
                    proj_env_tools = str(df.iloc[r, 12]).strip() if pd.notna(df.iloc[r, 12]) else ""
                    
                    lang_clean = ", ".join([l.strip() for l in proj_env_lang.split("\n") if l.strip()])
                    db_clean = ", ".join([d.strip() for d in proj_env_db.split("\n") if d.strip()])
                    tools_clean = ", ".join([t.strip() for t in proj_env_tools.split("\n") if t.strip()])
                    
                    project_lines.append(f"\n■職務経歴 No.{no_str}")
                    project_lines.append(f"  - 期間: {proj_period}")
                    project_lines.append(f"  - 立場/人数: {proj_role.replace(chr(10), ' ')}")
                    project_lines.append(f"  - 業務内容:\n    {proj_desc.replace(chr(10), chr(10) + '    ')}")
                    project_lines.append(f"  - 開発環境:")
                    project_lines.append(f"    * 言語/FW: {lang_clean}")
                    project_lines.append(f"    * OS/DB: {db_clean}")
                    project_lines.append(f"    * ツール等: {tools_clean}")
                else:
                    comment_val = df.iloc[r, 1]
                    if pd.notna(comment_val) and str(comment_val).strip() != "" and not str(comment_val).strip().isdigit() and "技術経歴書" not in str(comment_val):
                        project_lines.append(f"\n■自己PR・その他コメント:\n{str(comment_val).strip()}")
                        
        if project_lines:
            detail_lines.append("\n【職務経歴・自己PR】")
            detail_lines.extend(project_lines)
            
        es_data["experienced_processes_content"] = "\n".join(detail_lines)
        
    except Exception as e:
        log_gaze(f"Excel parsing error: {e}")
        
    return es_data

