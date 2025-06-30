# --- Import necessary libraries ---
import os
import shutil
import yaml
from datetime import datetime
import git
import json
import pandas as pd # Used for easy data handling and CSV export.

# --- Helper Functions ---
# (Helper functions are the same as the previous version)
def get_first_commit_time(repo_path, folder_path):
    """Finds the datetime of the first commit for a specific folder within a Git repository."""
    try:
        repo = git.Repo(repo_path)
        commits = list(repo.iter_commits(paths=folder_path, reverse=True))
        if commits:
            first_commit = commits[0]
            return datetime.fromtimestamp(first_commit.committed_date)
        return None
    except (git.exc.GitCommandError, git.exc.NoSuchPathError) as e:
        print(f"Warning: Could not get commit time for path '{folder_path}'. Error: {e}")
        return None

def preprocess_yaml_value(value):
    """Prepares YAML values for CSV export by converting complex types to strings."""
    if isinstance(value, dict):
        return json.dumps(value)
    if isinstance(value, (list, tuple)) and not value:
        return None
    if isinstance(value, list):
        return str(value)
    return value

def clone_repo(repo_url, clone_path):
    """Clones a Git repository. Skips if the directory already exists."""
    print(f"Checking repository at: {clone_path}")
    if os.path.exists(clone_path):
        print("Repository already exists. Skipping clone.")
    else:
        print(f"Cloning from {repo_url}...")
        os.makedirs(os.path.dirname(clone_path), exist_ok=True)
        git.Repo.clone_from(repo_url, clone_path)
        print("Clone complete.")

def load_yaml_file(file_path):
    """Loads a YAML file safely and returns its content."""
    with open(file_path, 'r', encoding='utf-8') as file:
        try:
            return yaml.safe_load(file)
        except yaml.YAMLError as e:
            print(f"Error parsing YAML file: {file_path}\n{e}")
            return None

def main():
    """
    Main execution function.
    This script assumes it is run from the project's root directory.
    1. Clones the OSS-Fuzz repository into 'data/collect_data/repos/'.
    2. Extracts metadata and commit data for each project.
    3. Compiles all data and saves it as a processed CSV file in 'data/processed_data/'.
    """
    # --- Configuration Section ---
    # This script is expected to be executed from the project's root directory.
    # All paths are defined relative to the project root.

    # URL of the repository to be analyzed
    CLONE_URL = 'https://github.com/google/oss-fuzz.git'
    
    # Path for raw data collection (where the repo is cloned).
    # Relative to project root: 'data/collect_data/repos/oss-fuzz'
    REPO_PATH = os.path.join('data', 'collect_data', 'repos', 'oss-fuzz')
    
    # Path to save the processed metadata CSV file.
    # Relative to project root: 'data/processed_data/project_info.csv'
    OUTPUT_CSV_PATH = os.path.join('data', 'processed_data','csv', 'project_info.csv')

    # Ensure the output directory ('data/processed_data') exists.
    # The script will create it if it doesn't exist.
    os.makedirs(os.path.dirname(OUTPUT_CSV_PATH), exist_ok=True)
    
    # --- Step 1: Clone Repository ---
    clone_repo(CLONE_URL, REPO_PATH)

    # --- Step 2: Collect and Process Project Information ---
    projects_dir = os.path.join(REPO_PATH, 'projects')
    if not os.path.isdir(projects_dir):
        print(f"Error: 'projects' directory not found at {projects_dir}")
        print("Please ensure you are running the script from the project root directory,")
        print("and the cloning process was successful.")
        return

    project_subdirs = [d for d in os.listdir(projects_dir) if os.path.isdir(os.path.join(projects_dir, d))]
    project_subdirs.sort()

    all_projects_data = []
    print(f"\nFound {len(project_subdirs)} projects. Starting data collection...")

    for i, project_name in enumerate(project_subdirs):
        print(f"[{i+1}/{len(project_subdirs)}] Processing project: {project_name}")
        project_path = os.path.join(projects_dir, project_name)
        
        yaml_file_path = os.path.join(project_path, 'project.yaml')
        if not os.path.exists(yaml_file_path):
            print(f"  - Warning: project.yaml not found for {project_name}. Skipping.")
            continue

        project_data = {'project': project_name}

        relative_project_path_for_git = os.path.join('projects', project_name)
        first_commit_time = get_first_commit_time(REPO_PATH, relative_project_path_for_git)
        project_data['first_commit_datetime'] = first_commit_time

        yaml_data = load_yaml_file(yaml_file_path)
        if yaml_data:
            for key, value in yaml_data.items():
                project_data[key] = preprocess_yaml_value(value)
        
        all_projects_data.append(project_data)

    print("\nData collection complete.")

    # --- Step 3: Save Processed Data to CSV ---
    if not all_projects_data:
        print("No data was collected. Exiting without creating a CSV.")
        return

    df = pd.DataFrame(all_projects_data)

    if 'first_commit_datetime' in df.columns:
        cols = ['project', 'first_commit_datetime']
        other_cols = sorted([c for c in df.columns if c not in cols])
        df = df[cols + other_cols]

    df.to_csv(OUTPUT_CSV_PATH, index=False, encoding='utf-8')
    print(f"Successfully saved processed data to: {OUTPUT_CSV_PATH}")


if __name__ == "__main__":
    main()