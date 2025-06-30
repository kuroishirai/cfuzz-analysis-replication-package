# -*- coding: utf-8 -*-
"""
This script scrapes daily code coverage data for projects from the OSS-Fuzz coverage reports.

It performs the following steps:
1.  Reads a list of projects and their metadata (e.g., language, start date) from 'project_info.csv'.
2.  For each supported project, it iterates from its start date to the present, scraping daily
    coverage statistics (coverage percentage, lines covered, total lines).
3.  The scraping logic is tailored to handle different report formats for various programming languages
    (e.g., C/C++, Go, Python, JVM).
4.  It implements a resume functionality: if the script is run again, it checks for existing data
    and only scrapes for dates that have not yet been collected.
5.  The collected data for each project is saved to a separate CSV file in 'coverage_by_project/'.
6.  Finally, it merges all individual project CSVs into a single comprehensive file, 'total_coverage.csv'.

This script is designed to be run from the root of the replication package directory
(e.g., by executing `python scripts/preparation/3_get_coverage_data.py`).
"""

# --- Import necessary libraries ---
import os
import re
import time
import glob
from datetime import datetime, timedelta
from io import StringIO # Import StringIO to handle pandas FutureWarning

import pandas as pd
import requests
from requests.adapters import HTTPAdapter, Retry
from bs4 import BeautifulSoup


# --- Configuration ---
# This section contains all configurable paths and settings for the script.
# These paths are relative to the project root directory where the script is executed.

# Path to the input CSV file containing project information.
PROJECT_INFO_PATH = os.path.join('data', 'processed_data', 'csv', 'project_info.csv')
# Directory to store intermediate CSV files, one for each project.
PER_PROJECT_OUTPUT_DIR = os.path.join('data', 'processed_data', 'csv', 'coverage_by_project')
# Path to the final merged CSV file containing data for all projects.
FINAL_MERGED_PATH = os.path.join('data', 'processed_data', 'csv', 'total_coverage.csv')

# We collect data up to 2 days ago because the latest daily reports might be in the process of
# being generated or may not be stable yet.
FINISH_DATE = datetime.now() - timedelta(days=2)

# List of programming languages for which coverage report parsing is supported.
SUPPORTED_LANGUAGES = ['c', 'c++', 'rust', 'swift', 'python', 'jvm']


# --- Web Scraping Helper Functions ---

def get_soup_from_url(url):
    """
    Fetches content from a URL and returns a BeautifulSoup object.

    This function includes a retry mechanism for temporary server errors (5xx)
    to make the scraping process more robust. It gracefully handles 404 Not Found
    errors by returning None, which indicates that a report for a specific day
    does not exist.

    Args:
        url (str): The URL to scrape.

    Returns:
        BeautifulSoup: A BeautifulSoup object of the page content, or None if
                       the request fails or results in a 404 error.
    """
    session = requests.Session()
    # Configure retries for robustness against temporary network/server issues.
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))

    try:
        response = session.get(url, timeout=10)
        # If a report for a specific day doesn't exist, the server returns 404.
        if response.status_code == 404:
            return None
        # Raise an HTTPError for other bad responses (e.g., 403, 500).
        response.raise_for_status()
        # Use 'lxml' for parsing as it's generally faster than Python's built-in parser.
        return BeautifulSoup(response.content, 'lxml')
    except requests.exceptions.RequestException as e:
        print(f"  - Request error for URL {url}: {e}")
        return None

def parse_coverage_table(html_string, table_index=0):
    """
    Parses an HTML table from a string into a pandas DataFrame.

    Args:
        html_string (str): The HTML content as a string.
        table_index (int): The index of the table to extract from the page. Defaults to the first table.

    Returns:
        pd.DataFrame: A DataFrame containing the parsed table data, or None if no table is found.
    """
    try:
        # Pass the HTML string to pandas.read_html.
        # We wrap the string in a StringIO object to avoid a FutureWarning.
        # pandas is highly efficient at finding and parsing table elements.
        dfs = pd.read_html(io=StringIO(html_string))
        if dfs:
            return dfs[table_index]
        return None
    except Exception:
        # This can happen if the table is malformed or pandas cannot find any table.
        return None

# --- Main Data Extraction Logic ---

def get_coverage_data(project, language, day):
    """
    Scrapes and extracts coverage data for a given project, language, and day.

    The structure of the coverage reports varies by language, so this function
    contains specific logic for different language groups.

    Args:
        project (str): The name of the project (e.g., 'ffmpeg').
        language (str): The primary language of the project.
        day (str): The date string in 'YYYYMMDD' format.

    Returns:
        dict: A dictionary containing the date, project name, coverage stats,
              and a boolean 'exist' flag indicating if data was found.
    """
    base_url = f'https://storage.googleapis.com/oss-fuzz-coverage/{project}/reports/{day}/linux/'
    # Initialize a dictionary with default values. 'exist' will be set to True on success.
    data = {'date': day, 'project': project, 'coverage': None, 'covered_line': None, 'total_line': None, 'exist': False}

    # Pause briefly between requests to be polite to the server.
    time.sleep(0.5)

    # --- C, C++, Rust, Swift ---
    # These languages use a similar report format, typically found in 'file_view_index.html'.
    if language in ['c', 'c++', 'rust', 'swift']:
        url = base_url + 'file_view_index.html'
        soup = get_soup_from_url(url)
        if soup is None:
            return data # Report for this day does not exist.

        df = parse_coverage_table(str(soup))
        if df is None or 'Line Coverage' not in df.columns:
            return data # Table format is unexpected or missing.

        # The summary is in the last row of the table.
        coverage_str = df.tail(1)['Line Coverage'].values[0]
        # Example format: "90.0% (180/200)". We extract the numbers.
        numbers = re.findall(r'[\d\.]+', str(coverage_str))
        if len(numbers) >= 3:
            data.update({
                'coverage': float(numbers[0]),
                'covered_line': int(numbers[1]),
                'total_line': int(numbers[2]),
                'exist': True
            })

    # --- Go, Python, JVM ---
    # These languages use a different report format, typically at 'index.html'.
    elif language in ['go', 'python', 'jvm']:
        url = base_url + 'index.html'
        soup = get_soup_from_url(url)
        if soup is None:
            return data

        df = parse_coverage_table(str(soup))
        if df is None:
            return data

        # Python reports have 'statements' and 'missing' columns.
        if language == 'python':
            if 'statements' in df.columns and 'missing' in df.columns:
                total_statements = df.tail(1)['statements'].values[0]
                missing_lines = df.tail(1)['missing'].values[0]
                covered_lines = total_statements - missing_lines
                if total_statements > 0:
                    data.update({
                        'coverage': (covered_lines / total_statements) * 100,
                        'covered_line': covered_lines,
                        'total_line': total_statements,
                        'exist': True
                    })
        # JVM (Java/Kotlin) reports have 'Lines' and 'Missed' columns.
        # The 'Missed' column name can vary (e.g., 'Missed_1' or 'Missed.1').
        elif language == 'jvm':
            if 'Lines' in df.columns:
                total_lines = df.tail(1)['Lines'].values[0]
                # Find the correct 'missed' column name.
                missed_col = next((col for col in ['Missed_1', 'Missed.1'] if col in df.columns), None)
                if missed_col:
                    missed_lines = df.tail(1)[missed_col].values[0]
                    covered_lines = total_lines - missed_lines
                    if total_lines > 0:
                        data.update({
                            'coverage': (covered_lines / total_lines) * 100,
                            'covered_line': covered_lines,
                            'total_line': total_lines,
                            'exist': True
                        })
    return data

def merge_coverage_data(source_dir, final_path):
    """
    Merges all individual project CSVs from a source directory into a single file.

    Args:
        source_dir (str): The directory containing the per-project CSV files.
        final_path (str): The path to save the final merged CSV file.
    """
    print("\n--- Merging all coverage data ---")
    all_files = glob.glob(os.path.join(source_dir, "*.csv"))
    if not all_files:
        print("No individual coverage CSVs found to merge.")
        return

    df_list = [pd.read_csv(file) for file in all_files]
    merged_df = pd.concat(df_list, ignore_index=True)

    merged_df.to_csv(final_path, index=False, encoding='utf-8')
    print(f"Successfully merged {len(all_files)} files into {final_path}")


def main():
    """
    Main execution function of the script.
    """
    os.makedirs(PER_PROJECT_OUTPUT_DIR, exist_ok=True)

    # --- Step 1: Load Project List ---
    print(f"Loading project list from: {PROJECT_INFO_PATH}")
    if not os.path.exists(PROJECT_INFO_PATH):
        print(f"Error: Project info file not found. Please ensure the file exists.")
        return
    projects_df = pd.read_csv(PROJECT_INFO_PATH, parse_dates=['first_commit_datetime'])
    print(f"Found {len(projects_df)} projects in the list.")

    # --- Step 2: Iterate Through Projects and Scrape Data ---
    for _, project_info in projects_df.iterrows():
        project_name = project_info['project']
        language = project_info.get('language')

        if language not in SUPPORTED_LANGUAGES:
            # Silently skip projects with unsupported languages.
            continue

        print(f"\n--- Processing project: {project_name} (Language: {language}) ---")

        project_csv_path = os.path.join(PER_PROJECT_OUTPUT_DIR, f"{project_name}.csv")
        collected_records = []

        # Resume logic: Check if a CSV for this project already exists.
        if os.path.exists(project_csv_path):
            print(f"  - Found existing data file. Resuming from last collected date.")
            existing_df = pd.read_csv(project_csv_path, parse_dates=['date'])
            # Start collecting from the day after the last recorded date.
            start_date = existing_df['date'].max() + timedelta(days=1)
        else:
            existing_df = pd.DataFrame()
            # If no file exists, start from the project's first known commit date.
            start_date = project_info['first_commit_datetime']

        # Ensure the start date is not earlier than the project's first commit.
        if start_date < project_info['first_commit_datetime']:
             start_date = project_info['first_commit_datetime']

        print(f"  - Collecting data from {start_date.strftime('%Y-%m-%d')} to {FINISH_DATE.strftime('%Y-%m-%d')}")

        current_date = start_date
        while current_date <= FINISH_DATE:
            date_str = current_date.strftime('%Y%m%d')
            # Use 'end=\r' to keep the progress update on a single line.
            print(f"    - Checking date: {date_str}", end='\r')

            result = get_coverage_data(project_name, language, date_str)
            # Only append the result if the scraping was successful.
            if result['exist']:
                collected_records.append(result)

            current_date += timedelta(days=1)

        # Print a newline to move past the progress indicator line.
        print("\n  - Daily data collection for this project is complete.")

        # --- Step 3: Save or Update Project's CSV File ---
        if collected_records:
            new_df = pd.DataFrame(collected_records)
            # Combine historical data with newly scraped data.
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            combined_df.to_csv(project_csv_path, index=False, encoding='utf-8')
            print(f"  - Saved/updated {len(new_df)} new records to {project_csv_path}")
        else:
            print("  - No new data was found to save for this project.")

    # --- Step 4: Merge All Individual CSVs into One ---
    merge_coverage_data(PER_PROJECT_OUTPUT_DIR, FINAL_MERGED_PATH)


if __name__ == "__main__":
    print("This script requires Python packages: 'pandas', 'requests', 'beautifulsoup4', 'lxml'.")
    print("You can install them using: pip install pandas requests beautifulsoup4 lxml\n")
    main()
