import sys
import os
import csv
from configparser import ConfigParser

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from tqdm import tqdm

# Add the module path to the system path to import custom modules.
module_path = 'program/__module'
if module_path not in sys.path:
    sys.path.append(module_path)

from dbFile import DB
import queries1


def save_raw_issues_to_csv(issues_data, output_path):
    """
    Saves the raw issue data to a CSV file.
    This function is used for creating an artifact of the issues analyzed.

    Args:
        issues_data (list of lists): The data to be saved.
        output_path (str): The path to the output CSV file.
    """
    if not issues_data:
        print("No issue data to save.")
        return

    # Create a generic header (e.g., 'issue_0', 'issue_1', ...)
    header = [f'issue_{i}' for i in range(len(issues_data[0]))]

    with open(output_path, mode='w', encoding='utf-8', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(header)
        csv_writer.writerows(issues_data)
    print(f"Saved raw issue data to: {output_path}")


def create_detection_rate_graph(iteration_stats, output_path, file_format='png'):
    """
    Creates and saves a dual-axis graph showing the vulnerability detection rate
    and the number of projects over fuzzing iterations.
    This corresponds to Figure 6 in the paper.

    Args:
        iteration_stats (dict): A dictionary with iteration stats, sorted by key.
        output_path (str): The path to the output image file.
        file_format (str): The format of the output image ('png', 'pdf', etc.).
    """
    if not iteration_stats:
        print("No data available to create the graph.")
        return
        
    detection_rates = []
    project_counts = []

    for iteration, stats in sorted(iteration_stats.items()):
        total_projects = stats[0]
        detected_projects_count = stats[1]
        
        # Calculate detection rate, avoiding division by zero
        rate = (detected_projects_count / total_projects * 100) if total_projects > 0 else 0
        detection_rates.append(rate)
        project_counts.append(total_projects)

    # Note for paper replication: The paper states "during the 26th fuzzing session,
    # the detection rate drops to 4.90%... Subsequently, it remains relatively stable".
    # The following analysis was used to calculate the statistics supporting this claim (e.g., IQR).
    late_stage_rates = detection_rates[25:]
    if late_stage_rates:
        min_rate, max_rate = min(late_stage_rates), max(late_stage_rates)
        p25, p75 = np.percentile(late_stage_rates, 25), np.percentile(late_stage_rates, 75)
        print(f"\nAnalysis of detection rates from iteration 26 onwards (for paper replication):")
        print(f"  - Min/Max: {min_rate:.2f}% / {max_rate:.2f}%")
        print(f"  - IQR (25th-75th percentile): {p25:.2f}% - {p75:.2f}%")

    fig, ax1 = plt.subplots(figsize=(5, 3))
    ax2 = ax1.twinx()
    
    # Ensure ax1 (line plot) is drawn on top of ax2 (bar plot)
    ax1.set_zorder(ax2.get_zorder() + 1)
    ax1.patch.set_visible(False)  # Make ax1's background transparent

    # Plot detection rate as a line graph on the primary y-axis
    ax1.plot(range(len(detection_rates)), detection_rates, color='b', marker='o', markersize=1.0, linewidth=1)
    ax1.set_ylabel('Detection Rate (%)', color='b')
    ax1.tick_params(axis='y', labelcolor='b')
    ax1.set_xlabel('Fuzzing Iteration')

    # Plot number of projects as a bar chart on the secondary y-axis
    ax2.bar(range(len(project_counts)), project_counts, alpha=0.6, color='g')
    ax2.set_ylabel('Number of Projects', color='g')
    ax2.tick_params(axis='y', labelcolor='g')
    
    plt.tight_layout()
    plt.savefig(output_path, format=file_format)
    plt.close()
    print(f"Saved detection rate graph to: {output_path}")


def collect_and_analyze_data():
    """
    Main function to collect data from the database, analyze it, and return the results.
    This function corresponds to the methodology for RQ1 described in the paper.
    
    Returns:
        tuple: A tuple containing:
            - final_stats (dict): Aggregated statistics for plotting.
            - vulnerability_issues (list): Raw issue data for artifact generation.
    """
    config = ConfigParser()
    config.read("program/envFile.ini")
    postgres_config = config["POSTGRES"]
        
    db = DB(database=postgres_config["POSTGRES_DB"], user=postgres_config["POSTGRES_USER"],
            password=postgres_config["POSTGRES_PASSWORD"], host=postgres_config["POSTGRES_IP"],
            port=postgres_config["POSTGRES_PORT"])
    db.connect()

    # --- Step 1: Select projects with sufficient historical data (Section IV-B in the paper) ---
    # Projects must have at least 365 days of coverage reports.
    query = """
        SELECT project
        FROM total_coverage
        WHERE coverage IS NOT NULL AND coverage > 0 AND date < '2025-01-08'
        GROUP BY project
        HAVING COUNT(*) >= 365
    """
    projects_result = db.executeQuery("select", query)
    eligible_projects = [project[0] for project in projects_result]
    print(f"Found {len(eligible_projects)} projects with at least 365 coverage reports (corresponds to 878 projects in the paper).")

    # --- Step 2: For each eligible project, count successful fuzzing builds over time ---
    iteration_stats = {}
    total_successful_builds = 0
    print("\n[Phase 1/3] Counting the number of projects per fuzzing iteration...")
    for project_name in tqdm(eligible_projects, desc="Processing projects"):
        query = queries1.SUCCESSED_FUZZING_BUILD(project_name)
        build_logs = db.executeQuery("select", query)
        for i in range(len(build_logs)):
            iteration = i + 1
            if iteration not in iteration_stats:
                # Structure: {iteration: {'total_projects': 0, 'detected_projects': []}}
                iteration_stats[iteration] = {'total_projects': 0, 'detected_projects': []}
            iteration_stats[iteration]['total_projects'] += 1
        total_successful_builds += len(build_logs)
    
    print(f"Counted {total_successful_builds:,} total successful fuzzing builds (corresponds to ~1.12 million sessions in the paper).")
    print(f"Maximum number of fuzzing iterations observed: {len(iteration_stats)}")

    # --- Step 3: Fetch fixed vulnerability issues for the eligible projects (Data for RQ1) ---
    query = queries1.SAME_DATE_BUILD_ISSUE(eligible_projects)
    vulnerability_issues = db.executeQuery("select", query)
    print(f"\n[Phase 2/3] Mapping {len(vulnerability_issues):,} vulnerability issues to fuzzing iterations...")
    print(f"(These are from {len(set(issue[1] for issue in vulnerability_issues))} unique projects, corresponding to 49,454 issues from 802 projects in the paper).")

    # --- Step 4: Map each vulnerability to a fuzzing iteration number ---
    current_project_name = ''
    project_build_logs = []
    for issue in tqdm(vulnerability_issues, desc="Mapping issues"):
        project_name = issue[1]
        issue_timestamp = issue[2]

        if project_name != current_project_name:
            current_project_name = project_name
            query = queries1.SUCCESSED_FUZZING_BUILD(current_project_name)
            project_build_logs = db.executeQuery("select", query)

        # Iteration number = number of successful builds before the issue was reported.
        builds_before_issue = [build for build in project_build_logs if issue_timestamp > build[1]]
        iteration_number = len(builds_before_issue)

        if iteration_number > 0 and iteration_number in iteration_stats:
            iteration_stats[iteration_number]['detected_projects'].append(project_name)

    # --- Step 5: Filter out iterations with fewer than 100 projects for statistical significance (Section VI-D) ---
    min_project_threshold = 100
    keys_to_remove = [key for key, value in iteration_stats.items() if value['total_projects'] < min_project_threshold]
    print(f"\n[Phase 3/3] Filtering and finalizing data...")
    print(f"Removing {len(keys_to_remove)} iterations with fewer than {min_project_threshold} projects.")
    for key in keys_to_remove:
        del iteration_stats[key]
    print(f"Retained {len(iteration_stats)} iterations for the final analysis (corresponds to 2,263rd session in the paper).")
    
    # --- Step 6: Finalize the data structure for plotting ---
    # Convert the list of detected project names to a unique count.
    final_stats = {}
    print("Aggregating final data for plotting...")
    for key, value in iteration_stats.items():
        total_projects = value['total_projects']
        detected_projects_count = len(set(value['detected_projects']))
        final_stats[key] = [total_projects, detected_projects_count]

    
    return final_stats, vulnerability_issues


def plot_histogram_from_csv(csv_path, key_col, value_col, bin_size=10, color='blue', title=None):
    """
    Reads a CSV file and plots a histogram by grouping a key column.
    This is a supplementary analysis function.

    Args:
        csv_path (str): Path to the CSV file.
        key_col (str): The name of the column to group by (e.g., 'Iteration').
        value_col (str): The name of the column to sum up (e.g., 'Detected_Projects_Count').
        bin_size (int): The size of each group.
        color (str): The color of the bars.
        title (str): The title of the graph.
    """
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_path}")
        return

    # Group the key column into bins
    df["Group"] = ((df[key_col] - 1) // bin_size + 1) * bin_size
    grouped_counts = df.groupby("Group")[value_col].sum()

    if not title:
        title = f"Total {value_col.replace('_', ' ')} per {bin_size} {key_col}s"

    plt.figure(figsize=(5, 3))
    plt.bar(grouped_counts.index, grouped_counts.values, width=bin_size * 0.9, alpha=0.7, color=color)
    plt.xlabel(f"{key_col} (Grouped by {bin_size})")
    plt.ylabel(f"Total {value_col.replace('_', ' ')}")
    plt.title(title)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.show()

    
def main():
    """
    Main execution function.
    """
    # Define directory for outputs. The path is kept from the original script.
    output_dir = 'data/result_data/rq1'
    os.makedirs(output_dir, exist_ok=True)
    
    # Define output file paths
    raw_issues_csv_path = os.path.join(output_dir, 'rq1_raw_issues_for_analysis.csv')
    stats_csv_path = os.path.join(output_dir, 'rq1_detection_rate_stats.csv')
    graph_png_path = os.path.join(output_dir, 'rq1_detection_rate.png')
    graph_pdf_path = os.path.join(output_dir, 'rq1_detection_rate.pdf')

    # Collect and analyze data. This is the most time-consuming step.
    final_stats, raw_issues = collect_and_analyze_data()

    # --- Save Artifacts ---
    # Save the raw issues for reference and reproducibility
    save_raw_issues_to_csv(raw_issues, raw_issues_csv_path)

    # Save the aggregated statistics to a CSV file
    csv_header = ['Iteration', 'Total_Projects', 'Detected_Projects_Count']
    with open(stats_csv_path, mode='w', newline='', encoding='utf-8') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(csv_header)
        for iteration, stats in sorted(final_stats.items()):
            writer.writerow([iteration] + stats)
    print(f"Saved aggregated statistics to: {stats_csv_path}")
            
    # Create and save the primary detection rate graph (Figure 6 in the paper)
    create_detection_rate_graph(final_stats, graph_png_path, file_format='png')
    create_detection_rate_graph(final_stats, graph_pdf_path, file_format='pdf')
    
    # Create and display a supplementary histogram for further insight
    plot_histogram_from_csv(
        csv_path=stats_csv_path,
        key_col='Iteration',
        value_col='Detected_Projects_Count',
        bin_size=100
    )
    
if __name__ == "__main__":
    main()