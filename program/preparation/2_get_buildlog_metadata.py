# --- Import necessary libraries ---
import os
import requests
from requests.adapters import HTTPAdapter, Retry
import time
import pandas as pd
import glob # Used for finding all batch CSV files

def save_batch_to_csv(records_batch, file_path, headers):
    """
    Saves a batch of records to a CSV file using pandas.
    """
    if not records_batch:
        return
    try:
        df = pd.DataFrame(records_batch)
        df = df[headers]
        df['timeCreated'] = pd.to_datetime(df['timeCreated'], errors='coerce')
        df.to_csv(file_path, index=False, encoding='utf-8')
        print(f"  -> Successfully saved {len(records_batch)} records to {file_path}")
    except Exception as e:
        print(f"  -> Error saving batch to CSV: {e}")

def merge_batch_csvs(directory_path, final_csv_path):
    """
    Finds all 'buildlog_metadata_batch_*.csv' files in a directory,
    merges them into a single DataFrame, and saves it as one CSV file.
    The batch files are then deleted.
    """
    print("\n--- Starting Merge Process ---")
    
    # Find all batch CSV files using a wildcard pattern
    batch_files_pattern = os.path.join(directory_path, 'buildlog_metadata_batch_*.csv')
    batch_files = glob.glob(batch_files_pattern)
    
    if not batch_files:
        print("No batch files found to merge.")
        return

    print(f"Found {len(batch_files)} batch files to merge.")

    # Read each CSV and store it in a list of DataFrames
    list_of_dfs = []
    for f in batch_files:
        try:
            list_of_dfs.append(pd.read_csv(f))
        except Exception as e:
            print(f"Warning: Could not read or process file {f}. Skipping. Error: {e}")

    if not list_of_dfs:
        print("Could not read any data from batch files. Merge process aborted.")
        return

    # Concatenate all DataFrames in the list into a single one
    merged_df = pd.concat(list_of_dfs, ignore_index=True)
    
    # Save the final merged DataFrame
    merged_df.to_csv(final_csv_path, index=False, encoding='utf-8')
    print(f"Successfully merged {len(merged_df)} records into: {final_csv_path}")

    # Clean up by deleting the individual batch files
    print("Cleaning up batch files...")
    for f in batch_files:
        try:
            os.remove(f)
        except Exception as e:
            print(f"Warning: Could not delete batch file {f}. Error: {e}")
    print("Cleanup complete.")


def main():
    """
    Main execution function.
    This script assumes it is run from the project's root directory.
    
    IMPORTANT: This script fetches data using time-sensitive 'nextPageToken' from a live API.
    It is designed to be run in a single, uninterrupted session. Stopping and restarting
    may lead to incomplete data.

    Steps:
    1. Fetches build log metadata from the GCS JSON API.
    2. Filters records based on the length of the 'name' field.
    3. Saves the filtered data in temporary batches (every 10 pages) to separate CSV files.
    4. After fetching all data, merges all batch CSVs into a single, final CSV file.
    5. Deletes the temporary batch files.
    """
    # --- Configuration Section ---
    BUCKET_NAME = "oss-fuzz-gcb-logs"
    BASE_URL = f"https://storage.googleapis.com/storage/v1/b/{BUCKET_NAME}/o"
    
    # Directory for temporary batch files
    BATCH_OUTPUT_DIR = os.path.join('data', 'processed_data', 'csv', 'buildlog_metadata_batches')
    
    # Final merged CSV file path
    FINAL_CSV_PATH = os.path.join('data', 'processed_data', 'csv', 'buildlog_metadata.csv')

    TARGET_KEYS = ['name', 'selfLink', 'mediaLink', 'size', 'timeCreated']
    REQUIRED_NAME_LENGTH = len('log-6259f647-370a-40e2-916b-8f4aaf105697.txt')
    PAGES_PER_BATCH = 10
    WAIT_TIME_SECONDS = 5

    # --- Setup Section ---
    os.makedirs(BATCH_OUTPUT_DIR, exist_ok=True)

    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('https://', adapter)

    # --- Data Fetching Loop ---
    records_for_current_batch = []
    page_count = 0
    batch_file_index = 1
    params = {}

    print(f"Starting metadata collection from bucket: '{BUCKET_NAME}'")
    print("IMPORTANT: This process should run uninterrupted.")

    while True:
        page_count += 1
        print(f"\nFetching page {page_count} (for batch {batch_file_index})...")

        try:
            response = session.get(BASE_URL, params=params, timeout=(10, 30))
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}. Stopping collection.")
            break

        data = response.json()
        items = data.get('items', [])
        
        if items:
            for item in items:
                item_name = item.get('name')
                if item_name and len(item_name) == REQUIRED_NAME_LENGTH:
                    record = {key: item.get(key) for key in TARGET_KEYS}
                    records_for_current_batch.append(record)
        
        # Save to a new CSV file every PAGES_PER_BATCH pages
        if page_count % PAGES_PER_BATCH == 0:
            if records_for_current_batch:
                output_filename = f"buildlog_metadata_batch_{batch_file_index}.csv"
                output_filepath = os.path.join(BATCH_OUTPUT_DIR, output_filename)
                save_batch_to_csv(records_for_current_batch, output_filepath, TARGET_KEYS)
                records_for_current_batch.clear()
            batch_file_index += 1

        if 'nextPageToken' in data:
            params['pageToken'] = data['nextPageToken']
            print(f"  -> Next page found. Pausing for {WAIT_TIME_SECONDS} seconds...")
            time.sleep(WAIT_TIME_SECONDS)
        else:
            print("\nNo more pages found. Finalizing...")
            break

    # Save any remaining data after the loop finishes
    if records_for_current_batch:
        output_filename = f"buildlog_metadata_batch_{batch_file_index}.csv"
        output_filepath = os.path.join(BATCH_OUTPUT_DIR, output_filename)
        save_batch_to_csv(records_for_current_batch, output_filepath, TARGET_KEYS)

    # --- Final Step: Merge all batch CSVs ---
    merge_batch_csvs(BATCH_OUTPUT_DIR, FINAL_CSV_PATH)
    
    print("\n--- All Processes Complete ---")


if __name__ == "__main__":
    main()