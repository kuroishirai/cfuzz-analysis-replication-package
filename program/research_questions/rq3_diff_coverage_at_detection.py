import sys
import os
import csv
import numpy as np
import matplotlib.pyplot as plt
from configparser import ConfigParser
from tqdm import tqdm
from scipy.stats import mannwhitneyu

# --- Configuration ---
MODULE_PATH = 'program/__module'
DB_CONFIG_FILE = 'program/envFile.ini'
OUTPUT_DIR = 'data/result_data/rq3'
OUTPUT_CSV_DETECTED = os.path.join(OUTPUT_DIR, 'detected_coverage_changes.csv')
OUTPUT_CSV_NON_DETECTED = os.path.join(OUTPUT_DIR, 'non_detected_coverage_changes.csv')

# Add custom module path
if MODULE_PATH not in sys.path:
    sys.path.append(MODULE_PATH)
from dbFile import DB

# --- Helper Functions for Statistical Analysis ---

def calculate_cliffs_delta(list1, list2):
    """Calculates Cliff's Delta, a non-parametric effect size measure."""
    n1, n2 = len(list1), len(list2)
    if n1 == 0 or n2 == 0:
        return 0.0, "N/A"
        
    greater = 0
    lesser = 0
    for x in list1:
        for y in list2:
            if x > y:
                greater += 1
            elif x < y:
                lesser += 1
    delta = (greater - lesser) / (n1 * n2)
    
    abs_delta = abs(delta)
    if abs_delta < 0.147:
        magnitude = "negligible"
    elif abs_delta < 0.33:
        magnitude = "small"
    elif abs_delta < 0.474:
        magnitude = "medium"
    else:
        magnitude = "large"
        
    return delta, magnitude

def analyze_and_print_stats(group1, group2, group1_name="Detected", group2_name="Not Detected"):
    """Performs and prints statistical comparison between two groups."""
    print("\n" + "="*50)
    print(f"Statistical Analysis: {group1_name} vs. {group2_name}")
    print("="*50)

    n1, n2 = len(group1), len(group2)
    print(f"Sample sizes: n1={n1}, n2={n2}")
    if n1 < 2 or n2 < 2:
        print("Not enough data for statistical tests.")
        return

    # Mann-Whitney U Test
    u_statistic, p_value = mannwhitneyu(group1, group2, alternative='two-sided')
    print(f"\n--- Mann-Whitney U Test ---")
    print(f"U-statistic: {u_statistic:.2f}")
    print(f"P-value: {p_value:.4g}")
    if p_value < 0.05:
        print("Result: Statistically significant difference.")
    else:
        print("Result: No statistically significant difference.")

    # Effect Size (Cliff's Delta)
    delta, magnitude = calculate_cliffs_delta(group1, group2)
    print(f"\n--- Effect Size (Cliff's Delta) ---")
    print(f"Delta: {delta:.4f} ({magnitude})")
    print("="*50 + "\n")


# --- Helper Functions for Plotting ---

def create_comparison_plots(detected_data, non_detected_data):
    """Generates and saves box plots and histograms for the two data groups."""
    print("--- Generating comparison plots ---")

    # --- Box Plot (Symmetric Log Scale) ---
    plt.figure(figsize=(4, 3))
    
    data_to_plot = [detected_data, non_detected_data]
    labels = ['Detected', 'Not Detected']
    
    box = plt.boxplot(data_to_plot, patch_artist=True, labels=labels, showfliers=True)
    
    colors = ['#A3BCE2', '#E2A3A3']
    for patch, color in zip(box['boxes'], colors):
        patch.set_facecolor(color)

    plt.ylabel('Coverage Difference (%)')
    plt.yscale('symlog', linthresh=0.01)
    plt.grid(axis='y', linestyle='--', alpha=0.6)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'coverage_diff_boxplot.pdf'))
    plt.close()
    print(f"Box plot saved to {os.path.join(OUTPUT_DIR, 'coverage_diff_boxplot.pdf')}")

    # --- Histograms ---
    all_data = np.concatenate([detected_data, non_detected_data])
    bins = np.linspace(np.min(all_data), np.max(all_data), 50)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 3), sharey=True, sharex=True)
    ax1.hist(detected_data, bins=bins, color='skyblue', edgecolor='black')
    ax1.set_title('Detected')
    ax1.set_xlabel('Coverage Difference (%)')
    ax1.set_ylabel('Frequency')
    
    ax2.hist(non_detected_data, bins=bins, color='salmon', edgecolor='black')
    ax2.set_title('Not Detected')
    ax2.set_xlabel('Coverage Difference (%)')

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'coverage_diff_histograms.pdf'))
    plt.close()
    print(f"Histograms saved to {os.path.join(OUTPUT_DIR, 'coverage_diff_histograms.pdf')}")


# --- Main Logic ---
def main():
    """
    Main function to analyze the difference in code coverage when bugs are detected versus when they are not.
    """
    print("--- RQ3 Analysis Started ---")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- 1. Database Connection and Initial Data Fetching ---
    config = ConfigParser()
    config.read(DB_CONFIG_FILE)
    db_config = config["POSTGRES"]
    db = DB(database=db_config["POSTGRES_DB"], user=db_config["POSTGRES_USER"],
            password=db_config["POSTGRES_PASSWORD"], host=db_config["POSTGRES_IP"],
            port=db_config["POSTGRES_PORT"])
    db.connect()

    # Get all fixed issues from projects that have at least 365 days of coverage data.
    issue_query = """
        SELECT project, number, rts
        FROM issues
        WHERE project IN (
            SELECT project FROM total_coverage
            WHERE coverage IS NOT NULL AND coverage > 0 AND date < '2025-01-08'
            GROUP BY project HAVING COUNT(*) >= 365
        )
        AND rts < '2025-01-08'
        AND status IN ('Fixed','Fixed (Verified)')
        ORDER BY project, rts;
    """
    all_issues = db.executeQuery("select", issue_query)
    print(f"Fetched {len(all_issues)} fixed issues from target projects.")

    # --- 2. Process Data Project by Project ---
    detected_changes = []      # [[diff_percent, diff_covered, diff_total, project_name, issue_timestamp], ...]
    non_detected_changes = []  # [[diff_percent, diff_covered, diff_total], ...]
    
    current_project = ''
    fuzzing_builds, coverage_builds, total_coverages = [], [], []

    for issue in tqdm(all_issues, desc="Processing issues"):
        project_name, _, issue_timestamp = issue
        
        # --- Fetch project-specific data when the project changes ---
        if current_project != project_name:
            # First, process the remaining non-detected coverage changes from the previous project
            if total_coverages:
                # ★★★ 修正点 2: 正しいインデックス(d[4])から日付を取得 ★★★
                detected_dates = {d[4].date() for d in detected_changes if d[3] == current_project}
                for i in range(1, len(total_coverages)):
                    if total_coverages[i][0].date() not in detected_dates:
                        prev_cov, curr_cov = total_coverages[i-1], total_coverages[i]
                        if len(prev_cov) > 2 and len(curr_cov) > 2 and prev_cov[2] > 0 and curr_cov[2] > 0:
                            diff_percent = (curr_cov[1] / curr_cov[2] - prev_cov[1] / prev_cov[2]) * 100
                            diff_covered = curr_cov[1] - prev_cov[1]
                            diff_total = curr_cov[2] - prev_cov[2]
                            non_detected_changes.append([diff_percent, diff_covered, diff_total])
            
            # Now, fetch data for the new project
            current_project = project_name
            fuzzing_builds = db.executeQuery("select", f"SELECT timecreated, modules, revisions FROM buildlog_data WHERE project = '{current_project}' AND build_type = 'Fuzzing' AND result IN ('HalfWay','Finish') AND DATE(timecreated) < '2025-01-08' ORDER BY timecreated;")
            coverage_builds = db.executeQuery("select", f"SELECT timecreated, modules, revisions, result FROM buildlog_data WHERE project = '{current_project}' AND build_type = 'Coverage' AND DATE(timecreated) < '2025-01-09' ORDER BY timecreated;")
            total_coverages = db.executeQuery("select", f"SELECT date, covered_line, total_line FROM total_coverage WHERE project = '{current_project}' AND covered_line IS NOT NULL AND DATE(date) < '2025-01-09' ORDER BY date;")

        # --- Link issue to builds and coverage data ---
        last_fuzz_build = next((b for b in reversed(fuzzing_builds) if b[0] < issue_timestamp), None)
        if not last_fuzz_build:
            continue
            
        first_cov_build = next((b for b in coverage_builds if b[0] > issue_timestamp), None)
        if not first_cov_build or first_cov_build[3] not in ['HalfWay', 'Finish']:
            continue
            
        if sorted(last_fuzz_build[2][1:-2].split(',')) != sorted(first_cov_build[2][1:-2].split(',')):
            continue

        if (first_cov_build[0] - last_fuzz_build[0]).total_seconds() / 3600 > 24:
            continue
            
        # --- Find the corresponding coverage change ---
        coverage_change_pair = []
        for i in range(len(total_coverages)):
            if total_coverages[i][0].date() == issue_timestamp.date():
                if i > 0:
                    coverage_change_pair = [total_coverages[i-1], total_coverages[i]]
                break
        
        if len(coverage_change_pair) == 2:
            prev_cov, curr_cov = coverage_change_pair
            if len(prev_cov) > 2 and len(curr_cov) > 2 and prev_cov[2] > 0 and curr_cov[2] > 0: # Avoid division by zero and index errors
                diff_percent = (curr_cov[1] / curr_cov[2] - prev_cov[1] / prev_cov[2]) * 100
                diff_covered = curr_cov[1] - prev_cov[1]
                diff_total = curr_cov[2] - prev_cov[2]
                # ★★★ 修正点 1: issue_timestampをリストに追加 ★★★
                detected_changes.append([diff_percent, diff_covered, diff_total, project_name, issue_timestamp])

    
    print(f"\nFound {len(detected_changes)} instances of coverage change on bug detection.")
    print(f"Found {len(non_detected_changes)} instances of coverage change without bug detection.")
    
    # --- 3. Save Processed Data to CSV ---
    with open(OUTPUT_CSV_DETECTED, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['CoverageChangePercent', 'CoveredLinesChange', 'TotalLinesChange'])
        # Save only the first 3 columns, as before
        writer.writerows([row[:3] for row in detected_changes])
    print(f"Saved detected changes data to {OUTPUT_CSV_DETECTED}")
    
    with open(OUTPUT_CSV_NON_DETECTED, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['CoverageChangePercent', 'CoveredLinesChange', 'TotalLinesChange'])
        writer.writerows(non_detected_changes)
    print(f"Saved non-detected changes data to {OUTPUT_CSV_NON_DETECTED}")

    # --- 4. Perform Analysis and Generate Plots ---
    detected_coverage_diffs = [row[0] for row in detected_changes]
    non_detected_coverage_diffs = [row[0] for row in non_detected_changes]

    analyze_and_print_stats(detected_coverage_diffs, non_detected_coverage_diffs)
    create_comparison_plots(detected_coverage_diffs, non_detected_coverage_diffs)
    
    print("\n--- RQ3 Analysis Finished ---")

if __name__ == '__main__':
    main()