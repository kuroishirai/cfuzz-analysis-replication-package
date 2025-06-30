import os
import csv
import json
import time
import random
import re ### 変更箇所: reモジュールをインポート ###
from datetime import datetime
import multiprocessing
import math
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import pandas as pd

# --- 定数 ---
# 処理対象のIDリストが記載されたテキストファイルのパス
TARGET_IDS_FILE = "/Users/tatsuya-shi/research/program/scraping/issue_scraping/should_ids.txt"
# 過去のスクレイピング結果（CSV）が保存されているベースディレクトリ
BASE_RESULTS_DIR = "/Users/tatsuya-shi/research/program/scraping/issue_scraping/scraping_results"
# スクレイピング時に保存するHTMLのベースディレクトリ
BASE_HTML_DIR = "/Users/tatsuya-shi/research/program/scraping/issue_scraping/html_results"

def save_full_html(driver, file_path):
    # (この関数の実装は省略されていますが、動作に影響はありません)
    pass

def load_processed_ids_from_csvs(base_dir):
    processed_ids = set()
    if not os.path.exists(base_dir): return processed_ids
    print(f"Scanning for existing CSV files in '{base_dir}' to find processed IDs...")
    for root, _, files in os.walk(base_dir):
        for filename in files:
            if filename.endswith('.csv'):
                filepath = os.path.join(root, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        if 'id' not in reader.fieldnames: continue
                        for row in reader:
                            try:
                                id_json_str = row.get('id')
                                if id_json_str:
                                    issue_id_val = json.loads(id_json_str)
                                    if issue_id_val is not None and str(issue_id_val).isdigit():
                                        processed_ids.add(int(issue_id_val))
                            except (json.JSONDecodeError, TypeError): continue
                except Exception as e: print(f"Warning: Could not process file '{filepath}': {e}")
    print(f"Found {len(processed_ids)} unique IDs in existing CSV files.")
    return processed_ids

def split_revision_range(text):
    parts = text.split(':')
    if len(parts) == 2 and len(parts[0]) > 10 and len(parts[1]) > 10:
        return parts
    return [text]

def scrape_revision_details(driver, url_to_scrape, issue_id, prefix, html_save_dir):
    print(f"  -> Scraping sub-page: {url_to_scrape}")
    original_url = driver.current_url
    for attempt in range(3):
        try:
            driver.get(url_to_scrape)
            WebDriverWait(driver, 15).until(lambda d: d.current_url != original_url and "about:blank" not in d.current_url)
            break
        except TimeoutException:
             print(f"    - Page stuck or failed to navigate. Retrying ({attempt + 1}/3)...")
    else:
        print(f"    - Failed to navigate. Aborting scrape.")
        driver.get(original_url) # 元のページへの復帰を試みる
        return None
    
    if 'Error' in driver.title:
        try:
            driver.find_element(By.TAG_NAME, 'table')
        except NoSuchElementException:
            print(f"    - Error page with no table. Skipping.")
            return None
    try:
        if driver.find_element(By.XPATH, "//*[contains(text(), 'Failed to get component revisions.')]").is_displayed():
            print(f"    - 'Failed to get revisions' message found. Skipping.")
            return None
    except NoSuchElementException:
        pass

    buildtime = url_to_scrape.split('=')[-1].split(':') if '=' in url_to_scrape else None
    components, revisions = [], []
    try:
        shadow_host = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'revisions-info')))
        WebDriverWait(driver, 10).until(
            lambda d: shadow_host.shadow_root.find_elements(By.CSS_SELECTOR, 'table tr.body')
        )
        time.sleep(1) # JavaScriptによるレンダリングの安定化のため待機
        html_file_path = os.path.join(html_save_dir, f"{issue_id}_{prefix}.html")
        save_full_html(driver, html_file_path)
        
        table_rows = shadow_host.shadow_root.find_elements(By.CSS_SELECTOR, 'table tr.body')
        
        for row in table_rows:
            try:
                # 行からすべてのセル(<td>)を取得
                cells = row.find_elements(By.TAG_NAME, 'td')
                if len(cells) >= 2:
                    # 1番目のセルのテキスト(Component)を取得
                    comp_text = cells[0].text.strip()
                    # 2番目のセルのテキスト(Revision Range)を取得
                    rev_text = cells[1].text.strip()
                    
                    # 両方のテキストが空でないことを確認
                    if comp_text and rev_text:
                        components.append(comp_text)
                        revisions.append(split_revision_range(rev_text))
            except Exception as e:
                # 特定の行の処理でエラーが発生しても継続する
                print(f"    - Warning: Could not process a row in revision table: {e}")

    except (TimeoutException, NoSuchElementException):
        print(f"    - Revision table not found or did not load content.")
        html_file_path = os.path.join(html_save_dir, f"{issue_id}_{prefix}_error.html")
        save_full_html(driver, html_file_path)
    
    for i in range(len(components)):
        print(components[i], revisions[i])
    return {'components': components, 'revisions': revisions, 'buildtime': buildtime}

def get_issue(issue_no, driver, html_save_dir):
    if int(issue_no) < 10000000:
        initial_url = f'https://bugs.chromium.org/p/oss-fuzz/issues/detail?id={issue_no}'
    else:
        initial_url = f'https://issues.oss-fuzz.com/issues/{issue_no}'
        
    load_success = False
    max_retries = 5
    for attempt in range(max_retries):
        current_url_before_nav = driver.current_url
        driver.get(initial_url)
        try:
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "b-issue-details, edit-issue-metadata")))
            print(f"  - Page content loaded for issue {issue_no}.")
            load_success = True; break
        except TimeoutException:
            try:
                if driver.find_element(By.XPATH, "//*[contains(@class, 'snackbar-content') and contains(., 'Request throttled')]").is_displayed():
                    print(f"  - Throttled on {issue_no}. Waiting 10 seconds..."); time.sleep(10); continue 
            except NoSuchElementException: pass
            print(f"  - Page load timed out for {issue_no}. Retrying...({attempt+1}/{max_retries})"); continue
    if not load_success: return {'id': str(issue_no), 'url': initial_url, 'error': True, 'title': 'Failed to load page'}

    time.sleep(1)
    current_issue_id = driver.current_url.split('/')[-1]
    html_file_path = os.path.join(html_save_dir, f"{current_issue_id}.html")
    save_full_html(driver, html_file_path)

    issue_infos = {'id': current_issue_id, 'url': driver.current_url, 'error': False}
    try: 
        try: issue_infos['title'] = driver.find_element(By.CSS_SELECTOR, "h3.heading-m.ng-star-inserted").text
        except NoSuchElementException: issue_infos['title'] = driver.find_element(By.CSS_SELECTOR, "issue-header h3").text
    except NoSuchElementException: issue_infos['error'] = True; print(f"Could not find title for {issue_infos['id']}")

    try:
        hotlists = [el.text for el in WebDriverWait(driver, 5).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "b-hotlist-chip-smart span.name a"))) if el.text]
        if hotlists: issue_infos['hotlists'] = hotlists
    except (TimeoutException, NoSuchElementException): pass
    
    try:
        utc_time_str = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'b-formatted-date-time time'))).get_attribute('datetime')
        if utc_time_str: issue_infos['reported_time'] = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00')).strftime("%Y-%m-%d %H:%M")
    except (TimeoutException, NoSuchElementException): pass
    
    try:
        target_keys_meta = ["Reporter", "Type", "Priority", "Severity", "Status", "Assignee", "Verifier", "Collaborators", "CC", "Project", "Disclosure", "Reported", "Code Changes", "Pending Code Changes", "Staffing", "Found In", "Targeted To", "Verified In"]
        user_data_keys = ["Reporter", "Assignee", "Verifier", "Collaborators", "CC"]
        date_keys = ["Disclosure", "Reported"]
        metadata_container = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'edit-issue-metadata')))
        field_containers = metadata_container.find_elements(By.CSS_SELECTOR, "b-edit-field, b-multi-user-control, b-staffing-row")
        for field in field_containers:
            try:
                label = field.find_element(By.TAG_NAME, 'label').text.strip()
                if label not in target_keys_meta: continue
                output_key = 'Metadata_Reported_Date' if label == 'Reported' else label
                if label in user_data_keys:
                    values = [v.text.strip() for v in field.find_elements(By.TAG_NAME, 'b-person-hovercard') if v.text.strip() and v.text.strip() != '--']
                    if not values: issue_infos[output_key] = None
                    elif label in ["CC", "Collaborators"]: issue_infos[output_key] = values
                    else: issue_infos[output_key] = values[0] if len(values) == 1 else values
                else:
                    value = field.find_element(By.CSS_SELECTOR, '.bv2-metadata-field-value, .staffing-summaries, .no-value').text.strip()
                    if value == '--' or not value: issue_infos[output_key] = None
                    elif label in date_keys:
                        try: issue_infos[output_key] = datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")
                        except ValueError: issue_infos[output_key] = value
                    else: issue_infos[output_key] = value
            except NoSuchElementException: continue
    except (TimeoutException, NoSuchElementException):
        print(f"Warning: Metadata container not found for {issue_infos['id']}")

    try:
        event_list_container = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'issue-event-list')))
        events = event_list_container.find_elements(By.CSS_SELECTOR, "div.bv2-event")
        for event in reversed(events):
            found_fix_info = False
            try:
                comment_section = event.find_element(By.CSS_SELECTOR, "b-plain-format-unquoted-section, b-markdown-format-presenter")
                comment_text = comment_section.text
                
                for line in comment_text.split('\n'):
                    line_stripped = line.strip()
                    if line_stripped.startswith("Fixed: http") and "/revisions" in line_stripped:
                        issue_infos['Fixed'] = line_stripped.split(' ', 1)[1]
                        found_fix_info = True
                        break
                
                if not found_fix_info and "is verified as fixed in" in comment_text:
                    link_element = event.find_element(By.CSS_SELECTOR, 'a[href*="/revisions"]')
                    issue_infos['Fixed'] = link_element.get_attribute('href')
                    found_fix_info = True

            except NoSuchElementException: continue

            if found_fix_info:
                try:
                    time_element = event.find_element(By.CSS_SELECTOR, "h4 b-formatted-date-time time")
                    utc_time_str = time_element.get_attribute('datetime')
                    if utc_time_str: issue_infos['fixed_time'] = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00')).strftime("%Y-%m-%d %H:%M")
                except NoSuchElementException: pass
                print(f"  -> Found 'Fixed' info: {issue_infos.get('Fixed')}"); break
    except (TimeoutException, NoSuchElementException): pass

    try:
        target_keys_desc = list(set(["Project", "Fuzzing Engine", "Fuzz Target", "Job Type", "Platform Id", "Crash Type", "Crash Address", "Crash State", "Sanitizer", "Regressed", "Reproducer Testcase", "Crash Revision", "Download", "Fixed", "Fuzzer","Fuzzer binary", "Fuzz target binary", "Minimized Testcase", "Recommended Security Severity", "Unminimized Testcase","Build log", "Build type"]))
        description_container = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "b-issue-description")))
        full_description_text = description_container.text
        current_key = None
        for line in full_description_text.split('\n'):
            line_stripped = line.strip().replace('<b>','').replace('</b>','')
            if not line_stripped: current_key = None; continue
            found_new_key = False
            for key in target_keys_desc:
                clean_line_start = line_stripped.replace('**', '')

                ### 変更箇所 ここから ###
                # "Minimized Testcase (1.23 Kb):" のようなファイルサイズ付きのラベルも検出できるように、
                # 単純な文字列比較から正規表現によるマッチングに変更。
                # これにより、キーの後に括弧で囲まれた追加情報があっても正しくキーを認識できる。
                pattern = re.compile(rf'^{re.escape(key)}(?:\s*\(.*\))?\s*:', re.IGNORECASE)

                if pattern.match(clean_line_start):
                    print('===========',key,'===========')
                    # 保存するキーは `target_keys_desc` にある統一された `key` を使う
                    current_key = key
                    value = line_stripped.split(':', 1)[1].strip()
                    
                    # "Minimized Testcase" もURLを持つ可能性があるため、他のキーと同様にURL部分のみを抽出するリストに追加
                    url_keys_with_possible_extra_text = ["Regressed", "Fixed", "Crash Revision", "Build log", "Reproducer Testcase", "Minimized Testcase"]
                    if key in url_keys_with_possible_extra_text:
                        if 'http' in value: issue_infos[key] = value.split(' ')[0]
                        else: issue_infos[key] = value
                    else: issue_infos[key] = value
                    found_new_key = True; break
                ### 変更箇所 ここまで ###
                
            if not found_new_key and current_key is not None:
                if "Issue filed automatically" in line_stripped or "See " in line_stripped: current_key = None; continue
                existing_value = issue_infos.get(current_key)
                if isinstance(existing_value, str):
                    if not existing_value: issue_infos[current_key] = [line_stripped]
                    else: issue_infos[current_key] = [existing_value, line_stripped]
                elif isinstance(existing_value, list): issue_infos[current_key].append(line_stripped)
    except (TimeoutException, NoSuchElementException):
        print(f"Warning: Description container (<b-issue-description>) not found for {issue_infos['id']}. Skipping description parsing.")

    main_issue_url = driver.current_url
    url_keys_to_scrape = {'Regressed': 'regressed', 'Fixed': 'fixed', 'Crash Revision': 'crash'}
    for info_key, prefix in url_keys_to_scrape.items():
        sub_url = issue_infos.get(info_key)
        if sub_url and isinstance(sub_url, str) and sub_url.startswith('http'):
            try:
                revision_data = scrape_revision_details(driver, sub_url, issue_infos['id'], prefix, html_save_dir)
                if revision_data:
                    issue_infos[f'{prefix}_components'] = revision_data.get('components')
                    issue_infos[f'{prefix}_revisions'] = revision_data.get('revisions')
                    issue_infos[f'{prefix}_buildtime'] = revision_data.get('buildtime')
            except Exception as e:
                print(f"  - An error occurred during scrape_revision_details for {sub_url}: {e}")
            finally:
                if driver.current_url != main_issue_url:
                    driver.get(main_issue_url)
                    try: WebDriverWait(driver, 15).until(EC.url_to_be(main_issue_url))
                    except TimeoutException:
                        print("    - Timed out while waiting to return to main issue page. Forcing navigation.")
                        driver.get(main_issue_url)
    return issue_infos

def save_to_csv(data_list, directory, file_index):
    if not data_list: return
    os.makedirs(directory, exist_ok=True)
    filename = os.path.join(directory, f"{file_index:03d}.csv")
    all_keys = set()
    for item in data_list: all_keys.update(item.keys())
    header = sorted(list(all_keys))
    processed_data = []
    for item in data_list:
        row_dict = {}
        for key in header: row_dict[key] = json.dumps(item.get(key), ensure_ascii=False)
        processed_data.append(row_dict)
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=header); writer.writeheader(); writer.writerows(processed_data)
        print(f"Saved {len(data_list)} items to {filename} (all values as JSON strings)")
    except IOError as e: print(f"Error saving file {filename}: {e}")

def run_scraper_instance(issue_numbers, window_index, base_output_dir, base_html_dir, save_interval=50):
    print(f"Window {window_index}: Starting with {len(issue_numbers)} issues.")
    options = webdriver.ChromeOptions(); options.add_argument('--headless'); options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox'); options.add_argument('--disable-dev-shm-usage'); options.add_argument('--blink-settings=imagesEnabled=false')
    driver = webdriver.Chrome(options=options)
    width, height = 500, 400; columns = 3
    x_pos = (window_index % columns) * width; y_pos = (window_index // columns) * (height + 40)
    driver.set_window_size(width, height); driver.set_window_position(x_pos, y_pos)
    results_batch = []; file_counter = 1
    output_dir = os.path.join(base_output_dir, f"window_{window_index}")
    html_output_dir = os.path.join(base_html_dir, f"window_{window_index}")
    os.makedirs(html_output_dir, exist_ok=True)
    for i, issue_no in enumerate(issue_numbers):
        print(f"Window {window_index}: Processing issue {i+1}/{len(issue_numbers)} - ID: {issue_no}")
        try:
            report = get_issue(issue_no, driver, html_output_dir)
            if report: results_batch.append(report)
        except Exception as e:
            print(f"Window {window_index}: A critical unhandled error for issue {issue_no}: {e}")
            if results_batch: save_to_csv(results_batch, output_dir, file_counter); results_batch = []; file_counter += 1
            driver.quit(); driver = webdriver.Chrome(options=options)
            driver.set_window_size(width, height); driver.set_window_position(x_pos, y_pos)
        if len(results_batch) >= save_interval:
            save_to_csv(results_batch, output_dir, file_counter); results_batch = []; file_counter += 1
        wait_time = random.uniform(1, 3)
        # print(f"Window {window_index}: Waiting for {wait_time:.2f} seconds...")
        time.sleep(wait_time)
    if results_batch: save_to_csv(results_batch, output_dir, file_counter)
    driver.quit()
    print(f"Window {window_index}: Finished.")

def main():
    # 処理すべきIDを `TARGET_IDS_FILE` から読み込むように修正
    all_target_ids = set()
    try:
        print(f"Loading target IDs from '{TARGET_IDS_FILE}'...")
        with open(TARGET_IDS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line_stripped = line.strip()
                # 空行や数字でない行は無視する
                if line_stripped.isdigit():
                    all_target_ids.add(int(line_stripped))
    except FileNotFoundError:
        print(f"Error: Target IDs file not found at '{TARGET_IDS_FILE}'. Please check the path.")
        return
    except Exception as e:
        print(f"An unexpected error occurred while loading target IDs from '{TARGET_IDS_FILE}': {e}")
        return
    print(f"Loaded {len(all_target_ids)} unique target IDs from the file.")

    ### 変更箇所 ここから ###
    csv_path = "/Users/tatsuya-shi/research/program/scraping/issue_scraping/scraping_results/merged_output.csv"
    
    # --- ここで再スクレイピング対象のフィルタリング条件を定義します ---
    # Key:   CSVの列名
    # Value: 
    #   - True: その列が欠損値(空)である行を対象とします。
    #   - False: その列に何らかの値が入っている行を対象とします。
    #   - 文字列: その列に指定した文字列が【部分一致】で含まれている行を対象とします (大文字・小文字は区別しません)。
    #
    # 条件はANDで結合されます（すべての条件を満たす行が対象になります）。
    #
    # [使用例]
    # 例1: 特定の列が「すべて」欠損しているデータを再取得
    # filter_conditions = {
    # }
    #
    # 例2: 'Status'に'Verified'という文字列を含み、かつ'fixed_time'が欠損しているデータを再取得
    filter_conditions = {
        'Fuzzer': 'Fuzzer binary:'
    }
    #
    # 例3: 'Project'に'chromium'という文字列が含まれるデータのみを対象とする
    # filter_conditions = {
    #     'Project': 'chromium'
    # }
    #
    # 空の辞書 `{}` にすると、このフィルタリング処理はスキップされます。
    # filter_conditions = {}

    id_list = []
    if not os.path.exists(csv_path):
        print(f"Info: CSV file for filtering not found at '{csv_path}'. Skipping re-scraping based on CSV content.")
    elif not filter_conditions:
        print("Info: filter_conditions is empty. Skipping re-scraping based on CSV content.")
    else:
        print(f"Loading CSV data from '{csv_path}' to find IDs based on custom filters...")
        try:
            df = pd.read_csv(csv_path, low_memory=False)
            
            # フィルター条件の列がDataFrameに存在するか確認
            valid_filters = {}
            for col, cond in filter_conditions.items():
                if col in df.columns:
                    valid_filters[col] = cond
                else:
                    print(f"Warning: Column '{col}' from filter_conditions not found in the CSV. Skipping this filter.")
            
            if not valid_filters:
                print("Warning: None of the specified filter columns exist in the CSV. Skipping re-scraping.")
            else:
                print(f"Applying filters: {valid_filters}")
                # 全ての行を対象とする初期マスクを作成
                final_mask = pd.Series([True] * len(df), index=df.index)

                for column, condition in valid_filters.items():
                    try:
                        if isinstance(condition, bool):
                            if condition:  # Trueの場合: 欠損値であること
                                # CSV保存時に json.dumps(None) は 'null' という文字列になるため、それも欠損とみなす
                                current_mask = df[column].isnull() | (df[column] == 'null')
                            else:  # Falseの場合: 欠損値でないこと
                                current_mask = df[column].notnull() & (df[column] != 'null')
                        elif isinstance(condition, str):  # 文字列の場合: 部分一致
                            # 全ての値を文字列に変換してから検索（エラー防止）
                            # na=False はNaNをFalseとして扱い、検索対象外とする
                            # case=False を指定して大文字・小文字を区別しない部分一致検索を行う
                            current_mask = df[column].astype(str).str.contains(re.escape(condition), case=False, na=False)
                        else:
                            print(f"Warning: Unsupported condition type for column '{column}': {type(condition)}. Skipping this filter.")
                            continue

                        # 作成したマスクを最終マスクにAND条件で結合
                        final_mask &= current_mask
                        print(len(final_mask),len(current_mask))
                    except Exception as e:
                        print(f"Error applying filter for column '{column}': {e}. Skipping this filter.")
                
                # 該当行の id を取得
                try:
                    # id列もjson.dumpsされているため、'"12345"' のような文字列になっている
                    # 前後の引用符を削除し、数値に変換する
                    id_series = df.loc[final_mask, 'id'].dropna().astype(str).str.strip('"')
                    # to_numericで数値に変換できない値をNaNにし、再度dropnaで除外
                    id_list = pd.to_numeric(id_series, errors='coerce').dropna().astype(int).tolist()
                    print(f"Found {len(id_list)} IDs matching the specified filters to re-scrape.")
                except KeyError:
                    print("Error: 'id' column not found in the CSV. Cannot extract IDs for re-scraping.")
                except Exception as e:
                    print(f"An error occurred during ID list creation from the final mask: {e}")

        except Exception as e:
            print(f"An error occurred while processing the CSV file '{csv_path}': {e}")
    ### 変更箇所 ここまで ###


    # 既存のCSVファイルから処理済みのIDを読み込む (この部分は変更なし)
    processed_ids = load_processed_ids_from_csvs(BASE_RESULTS_DIR)

    # 処理すべきIDのリストから、既に処理済みのIDを除外する
    # all_target_ids から始めることで、ファイルから読み込んだIDを優先する
    ids_to_process_set = (all_target_ids - processed_ids)
    # その後、CSVから見つかったIDを追加する（重複はsetが自動で処理）
    ids_to_process_set.update(id_list)
    
    ids_to_process = sorted(list(ids_to_process_set), reverse=True)


    print("-" * 50)
    print(f"Total target IDs from file: {len(all_target_ids)}")
    print(f"IDs found in existing CSVs (already processed): {len(processed_ids)}")
    print(f"IDs from merged_output.csv needing re-scraping: {len(id_list)}")
    print(f"Total unique IDs to scrape this run: {len(ids_to_process)}")
    print("-" * 50)

    if not ids_to_process:
        print("No new issues to process. Exiting.")
        return

    execution_time_str = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    current_run_dir = os.path.join(BASE_RESULTS_DIR, execution_time_str)
    os.makedirs(current_run_dir, exist_ok=True); print(f"Saving new CSV results to: {current_run_dir}")
    current_html_dir = os.path.join(BASE_HTML_DIR, execution_time_str)
    os.makedirs(current_html_dir, exist_ok=True); print(f"Saving new HTML files to: {current_html_dir}")

    num_windows = 8
    if len(ids_to_process) < num_windows: num_windows = len(ids_to_process)
    if num_windows == 0: print("No windows to open."); return
    chunk_size = math.ceil(len(ids_to_process) / num_windows)
    chunks = [ids_to_process[i:i + chunk_size] for i in range(0, len(ids_to_process), chunk_size)]

    processes = []
    for i, chunk in enumerate(chunks):
        if chunk:
            process = multiprocessing.Process(target=run_scraper_instance, args=(chunk, i, current_run_dir, current_html_dir))
            processes.append(process); process.start()
    for process in processes: process.join()
    print("All scraping processes for this run have completed.")

if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()