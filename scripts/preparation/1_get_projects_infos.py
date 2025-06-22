import sys
import os
import shutil
from configparser import ConfigParser
import yaml
from datetime import datetime
import git
import json
import ast  # ← 追加

module_path = os.path.join(os.path.dirname(__file__), '../__module')
module_path = os.path.abspath(module_path)

if module_path not in sys.path:
    sys.path.append(module_path)
import utils
from dbFile import DB


def get_first_commit_time(repo_path, folder_path):
    repo = git.Repo(repo_path)
    commits = list(repo.iter_commits(paths=folder_path, reverse=True))
    if commits:
        first_commit = commits[0]
        first_commit_time = datetime.fromtimestamp(first_commit.committed_date)
        return first_commit_time
    else:
        return None


def convert_values_to_strings(d):
    if isinstance(d, dict):
        return {k: str(convert_values_to_strings(v)) for k, v in d.items()}
    elif isinstance(d, list):
        return [str(convert_values_to_strings(item)) for item in d]
    else:
        return str(d)


def fix_array_types(val):
    if isinstance(val, str) and val.startswith("["):
        try:
            return ast.literal_eval(val)
        except:
            return val
    return val


def clone_repo(repo_url, clone_path):
    if not os.path.exists(clone_path):
        os.makedirs(clone_path)
    else:
        shutil.rmtree(clone_path)
    git.Repo.clone_from(repo_url, clone_path)


def get_subdirectories(folder_path):
    subdirectories = [d for d in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, d))]
    return subdirectories


def load_yaml(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = yaml.safe_load(file)
    return convert_values_to_strings(data)


def get_files(folder_path):
    files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
    return files


def main():
    clone_url = 'https://github.com/google/oss-fuzz.git'
    clone_path = utils.resolve_relative_path_from_script('../../data/repos/oss-fuzz')
    # clone_repo(clone_url, clone_path)

    repo_path = clone_path
    projects_path = f'{clone_path}/projects'
    subdirectories = get_subdirectories(projects_path)
    subdirectories.sort()

    configObj = ConfigParser()
    configObj.read(utils.resolve_relative_path_from_script("../../config/envFile.ini"))
    postgresInfo = configObj["POSTGRES"]

    db = DB(database=postgresInfo["POSTGRES_DB"], user=postgresInfo["POSTGRES_USER"],
            password=postgresInfo["POSTGRES_PASSWORD"], host=postgresInfo["POSTGRES_IP"],
            port=postgresInfo["POSTGRES_PORT"])
    db.connect()
    all_keys = []
    for subdirectory in subdirectories:
        utils.save_to_file(f'subdirectory: {subdirectory}')
        files = get_files(f'{projects_path}/{subdirectory}')
        yaml_files = [f for f in files if f.endswith('.yaml')]

        if not yaml_files:
            continue

        first_commit_time = get_first_commit_time(repo_path, f'projects/{subdirectory}')

        keys = ['project', 'first_commit_datetime']
        values = [subdirectory, first_commit_time]

        yaml_data = load_yaml(f'{projects_path}/{subdirectory}/{yaml_files[0]}')
        for key, value in yaml_data.items():
            all_keys.append(key)
            keys.append(key)
            if isinstance(value, dict):
                value = json.dumps(value)
            elif isinstance(value, (list, tuple)) and not value:
                value = None
            value = fix_array_types(value)  # ← ここでリストに戻す
            values.append(value)

        columns = ", ".join(keys)
        placeholders = ", ".join(["%s"] * len(values))

        insert_query = f"""
        INSERT INTO project_info ({columns})
        VALUES ({placeholders})
        """

        utils.save_to_file(f'{subdirectory}, {len(values)}, {len(keys)}')
        try:
            db.cursor.execute(insert_query, values)
            db.connection.commit()
        except Exception as e:
            utils.save_to_file(f'{subdirectory}: {e}')
            db.connection.rollback()

    all_keys = list(set(all_keys))
    for key in all_keys:
        utils.save_to_file(f'{key}')


if __name__ == "__main__":
    main()
