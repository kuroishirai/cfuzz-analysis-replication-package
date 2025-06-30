# --- START OF FILE 4_get_buildlog_analysis.py ---

import pandas as pd
import requests
import os
import glob
from datetime import datetime
import re
import json

SAVE_FOLDER = 'data/processed_data/csv/buildlog_analyzed_batches'
os.makedirs(SAVE_FOLDER, exist_ok=True)

def buildlog_analysis(row):
    
    # ▼▼▼ 修正点: 公開ログURLを生成して表示 ▼▼▼
    build_id = row['name']
    public_log_url = f"https://oss-fuzz-build-logs.storage.googleapis.com/log-{build_id}.txt"
    print(f"\n--- [START ANALYSIS] ID: {build_id} ---")
    print(f"Log URL: {public_log_url}")
    # ▲▲▲ 修正ここまで ▲▲▲

    try:
        time_created_dt = pd.to_datetime(row['timecreated'])
    except Exception as e:
        print(f"⚠️ 'timecreated'のパースに失敗しました: {row['timecreated']}, エラー: {e}")
        time_created_dt = None
        
    build_infos = {
        "id": build_id, # 修正に合わせて変数名を変更
        "size": int(row['size']),
        "project": "",
        "build_type": "",
        "result": "",
        "timecreated": time_created_dt,
        "modules": [],
        "path": [],
        "revisions": [],
        "types": [],
        "repo_urls": [],
        "download_link": row['medialink']
    }
    url = row['medialink'] # ダウンロード用URLは変更しない
    try:
        response = requests.get(url)
        response.raise_for_status()
        lines = response.text.splitlines()
        print(f"✅ Log downloaded successfully: {len(lines)} lines") # 表示メッセージを少し変更

    except Exception as e:
        print(f"❌ {build_id}: {e}")
        return build_infos
    
    if not lines or len(lines)==0:
        return build_infos
    
    # --- 変数と正規表現の初期化 ---
    docker_images = set()
    gcs_projects = set()
    path_list, type_list, repo_url_list, revision_list = [], [], [], []
    
    image_pattern = re.compile(r'Already have image: gcr\.io/oss-fuzz/([^\s:]+)')
    gcs_pattern = re.compile(r'No URLs matched: gs://oss-fuzz-coverage/([^/]+)/textcov_reports')
    jq_pattern = re.compile(r'jq_inplace [^ ]+ \'(.*?)\'')
    json_line_pattern = re.compile(r'Step #\d+:\s?(.*)')

    pattern_intro = re.compile(r'Step #(\d+): Pulling image: gcr.io/oss-fuzz-base/base-runner')
    pattern_fuzzing = re.compile(r"Unable to find image 'gcr.io/oss-fuzz-base/base-runner:latest' locally")
    pattern_html = re.compile(r'/report/.*\.html')
    pattern_error = re.compile(r'\nERROR.*')
    pattern_finish = re.compile(r'PUSH\s*DONE', re.DOTALL)
    pattern_fuzzer = re.compile(r'compile-(.*)-(.*)-x86_64')
    
    # --- 収集用変数 ---
    collecting_json = False
    json_lines = []
    
    print("[DEBUG] Starting line-by-line analysis...")
    
    

    for i, line in enumerate(lines):
        # プロジェクト名の抽出
        image_match = image_pattern.search(line)
        if image_match:
            project_name = image_match.group(1)
            # print(f"[DEBUG] Line {i}: Found project name from image: '{project_name}'")
            docker_images.add(project_name)
            if not build_infos['project']:
                build_infos['project'] = project_name

        gcs_match = gcs_pattern.search(line)
        if gcs_match:
            project_name_gcs = gcs_match.group(1)
            # print(f"[DEBUG] Line {i}: Found project name from GCS: '{project_name_gcs}'")
            gcs_projects.add(project_name_gcs)
            if not build_infos['project']:
                build_infos['project'] = project_name_gcs
        
        # Build Typeの特定
        match = re.match(r"Starting Step #\d+\s*(.*)", line)
        if match:
            after_text = match.group(1).strip().replace('"', '')
            if after_text == "" or 'srcmap' in after_text or 'build' in after_text:
                continue
            matched = True  # 一度でもマッチしたらTrueにする

            if 'coverage' in after_text:
                build_infos['build_type'] = 'coverage'

            elif 'introspector' in after_text:
                build_infos['build_type'] = 'introspector'

            elif any(keyword in after_text for keyword in ['address-x86_64', 'undefined-x86_64', 'memory-x86_64', 'none-x86_64', 'address-i386']):

                build_infos['build_type'] = 'Fuzzing'
            else:
                build_infos['build_type'] = 'Unknown'
        else:
            intro = re.search(pattern_intro, line)
            html = re.search(pattern_html, line)
            fuzzing = re.search(pattern_fuzzing, line)
            error = re.search(pattern_error, line)
            finish = re.search(pattern_finish, line)
            fuzzer = re.search(pattern_fuzzer, line)
            
            if intro:
                if intro.group(1) == '0':
                    build_infos['build_type'] = 'Introspector'
                elif intro.group(1) == '4':
                    build_infos['build_type'] = 'Coverage'
                elif intro.group(1) == '5':
                    build_infos['build_type'] = 'Fuzzing'
                else:
                    build_infos['build_type'] = 'Unknown'
            if html:
                build_infos['build_type'] = 'Coverage'
            if fuzzing:
                build_infos['build_type'] = 'Fuzzing'
            if fuzzer:
                # if fuzzer.group(2) == 'address' or fuzzer.group(2) == 'none':
                if fuzzer.group(2) in ['address', 'memory', 'undefined', 'none']:
                    build_infos['build_type'] = 'Fuzzing'
                elif fuzzer.group(2) == 'coverage':
                    build_infos['build_type'] = 'Coverage'
                elif fuzzer.group(2) == 'introspector':
                    build_infos['build_type'] = 'Introspector'
                else:
                    build_infos['build_type'] = 'Unknown'
            if finish:
                if build_infos['build_type'] != 'Coverage' and build_infos['build_type'] != 'Introspector':
                    build_infos['build_type'] = 'Fuzzing'
                result = 'Finish'
            elif error:
                if not build_infos['build_type'] in ['Coverage', 'Fuzzing', 'Introspector']:
                    build_infos['build_type'] = 'Error'
                result = 'Error'
            else:
                result = 'Halfway'
            
    
        # 【パターン1】jq_inplace コマンドの行を処理
        jq_match = jq_pattern.search(line)
        if jq_match:
            # print(f"[DEBUG] Line {i}: Found 'jq_inplace' command.")
            content = jq_match.group(1)
            path = re.search(r'"(.+?)"\s*=', content)
            type_ = re.search(r'type:\s*"(.+?)"', content)
            url_match = re.search(r'url:\s*"(.+?)"', content) # 変数名をurlからurl_matchに変更
            rev = re.search(r'rev:\s*"(.+?)"', content)

            if path and type_ and url_match and rev:
                # print(f"  [+] Extracted via jq_inplace: path={path.group(1)}")
                path_list.append(path.group(1))
                type_list.append(type_.group(1))
                repo_url_list.append(url_match.group(1))
                revision_list.append(rev.group(1))
            else:
                # print(f"  [-] jq_inplace found, but failed to extract all details.")
                pass

        # 【パターン2】JSONブロックの処理
        if "{" in line and line.strip().endswith('{') and not collecting_json:
            match = json_line_pattern.search(line)
            if match and match.group(1).strip() == '{':
                collecting_json = True
                json_lines = [match.group(1)]
                # print(f"[DEBUG] Line {i}: JSON block started.")
                continue

        if collecting_json:
            match = json_line_pattern.search(line)
            if match:
                json_lines.append(match.group(1))
            
            if line.strip().endswith('}'):
                collecting_json = False
                # print(f"[DEBUG] Line {i}: JSON block ended.")
                json_string = ''.join(json_lines)
                # print(f"[DEBUG] Attempting to parse JSON block:\n---\n{json_string}\n---")
                try:
                    parsed_json = json.loads(json_string)
                    # print("[DEBUG] JSON parsing successful.")
                    for path, details in parsed_json.items():
                        # print(f"  [+] Extracted from JSON block: path={path}")
                        path_list.append(path)
                        type_list.append(details.get('type', ''))
                        repo_url_list.append(details.get('url', ''))
                        revision_list.append(details.get('rev', ''))
                    # print(f"[DEBUG] Extracted {len(parsed_json)} items from JSON.")
                except json.JSONDecodeError as e:
                    # print(f"⚠️ [ERROR] JSON parsing failed: {e}")
                    pass
                json_lines = []
            


    # --- 結果の集計 ---
    build_infos["modules"] = [path.split('/')[-1].capitalize() for path in path_list]
    build_infos["path"] = path_list
    build_infos["types"] = type_list
    build_infos["repo_urls"] = repo_url_list
    build_infos["revisions"] = revision_list
    



    check_logs = [t.strip() for t in lines[-200:]]

    if "ERROR" in lines[-2] or "ERROR" in check_logs:
        build_infos['result'] = 'Error'
    elif "PUSH" in check_logs and "DONE" in check_logs:
        build_infos['result'] = 'Success'
    elif "ERROR: context deadline exceeded" in check_logs:
        build_infos['result'] = 'Error'
    else:
        build_infos['result'] = 'Unknown'

    print("\n--- [ANALYSIS COMPLETE] Final build_infos (JSON) ---")
    print(json.dumps(build_infos, indent=2, default=str, ensure_ascii=False))
    print("----------------------------------------------------")
    if build_infos['result'] in ['Unknown','']:
        print(build_infos['id'])
    if build_infos['build_type'] in ['']:
        print(build_infos['id'])
    return build_infos

# (main関数は変更なしのため省略)
def main():
    csv_path = "data/processed_data/csv/buildlog_metadata.csv"
    
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"エラー: CSVファイルが見つかりません: {csv_path}")
        return

    required_columns = ['name', 'selflink', 'medialink', 'size', 'timecreated']
    if not all(col in df.columns for col in required_columns):
        print("CSVに必要な列が不足しています")
        return

    existing_ids = set()
    for filepath in glob.glob(os.path.join(SAVE_FOLDER, '*.csv')):
        try:
            existing_df = pd.read_csv(filepath)
            if 'id' in existing_df.columns:
                existing_ids.update(existing_df['id'].dropna().tolist())
        except Exception as e:
            print(f"読み込み失敗: {filepath}, {e}")

    df = df[~df['name'].isin(existing_ids)]
    
    if df.empty:
        print("処理対象の新しいデータがありませんでした。")
        return

    print(f"未処理データの中から最初の10件を処理します (全{len(df)}件中)")
    
    results = []
    for i, row in df.head(10).iterrows():
        results.append(buildlog_analysis(row))
    
    if results:
        batch_df = pd.DataFrame(results)
        save_path = os.path.join(SAVE_FOLDER, f"batch_debug_{len(results)}_items.csv")
        batch_df.to_csv(save_path, index=False)
        print(f"\n💾 Saved {len(results)} entries to {save_path}")


if __name__ == "__main__":
    main()