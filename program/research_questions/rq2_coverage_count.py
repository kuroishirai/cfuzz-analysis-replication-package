import sys
import os
import csv
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from configparser import ConfigParser
from tqdm import tqdm
from scipy.stats import pearsonr, spearmanr
import statistics

# --- Configuration ---
# Define constants for file paths and parameters to avoid hardcoding.
MODULE_PATH = 'program/__module'
DB_CONFIG_FILE = 'program/envFile.ini'
OUTPUT_DIR = 'data/result_data/rq2'
PROJECT_FIGURE_DIR = os.path.join(OUTPUT_DIR, 'projects')

# --- Main Script ---

def plot_project_coverage_trend(coverage_data, output_pdf_path="coverage_chart.pdf"):
    """
    Generates and saves a PDF chart showing the coverage trend for a single project.
    The chart includes coverage percentage, total lines, and covered lines over time.

    Args:
        coverage_data (list of tuples): A list where each tuple contains (covered_line, total_line).
        output_pdf_path (str): The path to save the output PDF file.

    Returns:
        str: The path to the saved PDF file, or None if plotting was skipped.
    """
    if not coverage_data:
        print("Warning: No data provided to plot. Skipping graph creation.")
        return None

    # Ensure the output directory for project-specific figures exists.
    os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)

    # 1. Prepare DataFrame
    df = pd.DataFrame(coverage_data, columns=["covered_line", "total_line"])
    if df.empty:
        print("Warning: DataFrame is empty. Skipping graph creation.")
        return None

    # Calculate coverage percentage, handling division by zero.
    df["coverage_percent"] = np.divide(
        df["covered_line"], df["total_line"],
        out=np.zeros_like(df["covered_line"], dtype=float),
        where=df["total_line"] != 0
    ) * 100
    df["session_index"] = range(len(df))

    # 2. Setup Plot Style
    sns.set_theme(style="white")
    fig, ax1 = plt.subplots(figsize=(5, 3))

    # 3. Prepare dual axes
    ax2 = ax1.twinx()
    ax1.set_zorder(ax2.get_zorder() + 1)
    ax1.patch.set_visible(False)

    # 4. Right Y-axis: Bar/Fill chart for line counts
    palette = sns.color_palette("muted")
    total_color, covered_color = palette[4], palette[2]

    # Use a filled area chart for many data points, and a bar chart for fewer.
    if len(df) > 150:
        ax2.fill_between(df.session_index, 0, df["total_line"], color=total_color, alpha=0.5, label="Total Lines")
        ax2.fill_between(df.session_index, 0, df["covered_line"], color=covered_color, alpha=0.9, label="Covered Lines")
    else:
        ax2.bar(df.session_index, df["total_line"], width=0.7, label="Total Lines", color=total_color, alpha=0.5)
        ax2.bar(df.session_index, df["covered_line"], width=0.7, label="Covered Lines", color=covered_color, alpha=0.9)

    ax2.set_ylabel("Number of Lines", fontsize=10)
    ax2.tick_params(axis='y', labelsize=8)
    ax2.grid(False)

    # 5. Left Y-axis: Line chart for coverage percentage
    line_color = palette[0]
    line = ax1.plot(
        df.session_index, df["coverage_percent"],
        color=line_color,
        alpha=0.8,
        label="Coverage (%)",
        linewidth=2.0,
        zorder=10,
        solid_capstyle='round'
    )
    # Add a white stroke effect to the line for better visibility
    plt.setp(line, path_effects=[
        path_effects.Stroke(linewidth=0.3, foreground='white'),
        path_effects.Normal()
    ])

    ax1.set_ylabel("Coverage (%)", fontsize=10, color=line_color)
    ax1.set_ylim(0, 105)
    ax1.tick_params(axis='y', colors=line_color, labelsize=8)
    ax1.set_xlabel("Coverage Measurement Count", fontsize=10)
    ax1.grid(False)

    # 6. Despine axes for a cleaner look
    sns.despine(ax=ax1, top=True, right=True, left=False, bottom=False)
    sns.despine(ax=ax2, top=True, right=False, left=True, bottom=False)

    # 7. Create a shared legend and adjust layout
    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    fig.legend(handles1 + handles2, labels1 + labels2, loc="lower center",
               bbox_to_anchor=(0.5, -0.055), ncol=3, frameon=False, fontsize=9)

    fig.tight_layout()

    # Save the figure to PDF
    fig.savefig(output_pdf_path, bbox_inches='tight')
    plt.close(fig)

    return output_pdf_path


def main():
    """
    Main function to perform RQ2 analysis.
    This script fetches coverage data from a database, calculates correlations,
    and generates plots to analyze coverage trends over fuzzing sessions.
    """
    print("--- Main process started ---")

    # Add the module path to sys.path for custom module imports
    if MODULE_PATH not in sys.path:
        sys.path.append(MODULE_PATH)
    from dbFile import DB
    import queries1

    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # --- 1. Database Connection and Data Fetching ---
    config = ConfigParser()
    config.read(DB_CONFIG_FILE)
    db_config = config["POSTGRES"]

    db = DB(database=db_config["POSTGRES_DB"], user=db_config["POSTGRES_USER"],
            password=db_config["POSTGRES_PASSWORD"], host=db_config["POSTGRES_IP"],
            port=db_config["POSTGRES_PORT"])
    db.connect()

    # Query to select projects with at least 365 coverage measurements
    query = """
        SELECT project
        FROM total_coverage
        WHERE coverage IS NOT NULL AND coverage > 0 AND date < '2025-01-08'
        GROUP BY project
        HAVING COUNT(*) >= 365
    """
    project_records = db.executeQuery("select", query)
    projects = [project[0] for project in project_records]
    

    # --- 2. Process Each Project ---
    all_project_correlations = []
    coverage_by_session_index = [[]] # List of lists, where index `i` holds coverage values for the i-th session

    print(f"\n--- Starting to process {len(projects)} projects ---")
    for project_name in tqdm(projects, desc="Processing projects"):
        query = queries1.GET_TOTAL_COVERAGE_EACH_PROJECT(project_name, 'coverage')
        
        raw_coverage_data = db.executeQuery("select", query)
        
        if not raw_coverage_data:
            continue

        # Calculate coverage percentage for each session
        coverage_trend = [
            (float(x[0]) / float(x[1])) * 100
            for x in raw_coverage_data if x[1] != 0  # Avoid division by zero
        ]

        # Calculate Spearman correlation between session index and coverage trend
        if len(coverage_trend) < 2:
            corr = np.nan
        else:
            corr, _ = spearmanr(range(len(coverage_trend)), coverage_trend)

        all_project_correlations.append(corr)

        # Plot and save a figure for projects with high correlation
        if not np.isnan(corr) and abs(corr) > 0.5:
            figure_path = os.path.join(PROJECT_FIGURE_DIR, f"{corr:.4f}_{project_name}.pdf")
            plot_project_coverage_trend(raw_coverage_data, figure_path)

        # Aggregate coverage data by session index across all projects
        for i, cov in enumerate(coverage_trend):
            if len(coverage_by_session_index) <= i:
                coverage_by_session_index.append([])
            coverage_by_session_index[i].append(cov)
    
    print("\n--- Project processing finished ---\n")

    # --- 3. Save Aggregated Data ---
    csv_path = os.path.join(OUTPUT_DIR, "coverage_by_session_index.csv")
    print(f"Saving coverage data per session index to: {csv_path}")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(coverage_by_session_index)
    print(f"Successfully saved. Total rows (max sessions): {len(coverage_by_session_index)}")

    # --- 4. Overall Correlation Analysis ---
    print("\n--- Analysis of All Project Correlations ---")
    correlations_with_nan = np.array(all_project_correlations)
    valid_correlations = correlations_with_nan[~np.isnan(correlations_with_nan)]
    
    print(f"Total projects processed: {len(correlations_with_nan)}")
    print(f"Number of projects with valid correlation: {len(valid_correlations)}")
    print(f"Average correlation: {np.mean(valid_correlations):.4f}, Median correlation: {np.median(valid_correlations):.4f}")

    # Generate and save Violin+Box plot for correlation coefficients
    plt.figure(figsize=(6, 4))
    plt.violinplot(valid_correlations, showmeans=False, showmedians=True)
    plt.boxplot(valid_correlations, positions=[1.15], widths=0.15, patch_artist=True, boxprops=dict(facecolor='lightblue', color='blue'))
    plt.xticks([1, 1.15], ['Violin', 'Box'])
    plt.ylabel('Correlation')
    plt.tight_layout()
    violin_path = os.path.join(OUTPUT_DIR, 'all_project_corr_violin_box.pdf')
    plt.savefig(violin_path, format='pdf')
    plt.close()
    print(f"Violin+Box plot saved to: {violin_path}")

    # Generate and save a histogram of correlation coefficients
    plt.figure(figsize=(5, 3))
    sns.histplot(valid_correlations, bins=40, color='skyblue', edgecolor='black', alpha=0.8)
    plt.xlabel('Correlation')
    plt.ylabel('Frequency')
    plt.tight_layout()
    hist_path = os.path.join(OUTPUT_DIR, 'all_project_corr_hist.pdf')
    plt.savefig(hist_path, format='pdf')
    plt.close()
    print(f"Correlation histogram saved to: {hist_path}")

    # --- 5. Boxplot of Coverage vs. Fuzzing Sessions ---
    print("\n--- Generating Boxplot of Coverage vs. Session Count ---")
    
    # Filter for sessions with at least 100 data points
    sessions_with_enough_data = [d for d in coverage_by_session_index if len(d) >= 100]
    print(f'Number of sessions with >= 100 projects: {len(sessions_with_enough_data)}')

    # Sample data for boxplot (e.g., one box every 100 sessions)
    n_step = 100
    boxplot_data = [coverage_by_session_index[i] for i in range(0, len(coverage_by_session_index), n_step) if len(coverage_by_session_index[i]) >= 100]
    
    # Define X-axis ticks and labels
    xtick_labels_full = [i for i in range(1, len(coverage_by_session_index) + 1, n_step) if len(coverage_by_session_index[i-1]) >= 100]
    label_step = 2
    xtick_positions = list(range(1, len(boxplot_data) + 1))[::label_step]
    xtick_labels = xtick_labels_full[::label_step]
    
    plt.figure(figsize=(5,3))
    ax1 = plt.gca()
    
    # Bar chart for the number of projects (background)
    ax2 = ax1.twinx()
    ax1.set_zorder(ax2.get_zorder() + 1)
    ax1.patch.set_visible(False)
    ax2.bar(range(1, len(boxplot_data) + 1), [len(data) for data in boxplot_data], color='#88c778', alpha=0.6, zorder=1)
    ax2.set_ylabel('Number of Projects')
    
    # Boxplot for coverage distribution (foreground)
    box = ax1.boxplot(boxplot_data, vert=True, patch_artist=True, zorder=3)
    for patch in box['boxes']:
        patch.set_facecolor('#e3eefa')
    for median in box['medians']:
        median.set_color('#000000')
    
    # Plot mean values as triangles
    for i, data in enumerate(boxplot_data, start=1):
        mean_value = np.mean(data)
        ax1.scatter(i, mean_value, color='#215F9A', marker='^', zorder=4, s=8)
    
    ax1.set_ylabel('Coverage (%)')
    ax1.set_ylim(0, 100)
    ax1.set_xlabel('Coverage Measurement Count')
    ax1.set_xticks(xtick_positions)
    ax1.set_xticklabels(xtick_labels)
    
    plt.tight_layout()
    boxplot_path = os.path.join(OUTPUT_DIR, 'session_coverage_boxplot.pdf')
    plt.savefig(boxplot_path, format='pdf', transparent=True)
    plt.close()
    print(f"Boxplot saved to: {boxplot_path}")

    # --- 6. Correlation of Average/Median Coverage Over Time ---
    print("\n--- Correlation of Average/Median Coverage over Time ---")
    average_trend = [statistics.mean(s) for s in sessions_with_enough_data]
    median_trend = [statistics.median(s) for s in sessions_with_enough_data]
    session_indices = list(range(len(sessions_with_enough_data)))
    
    if len(median_trend) > 1:
        pearson_avg = pearsonr(session_indices, average_trend)
        pearson_median = pearsonr(session_indices, median_trend)
        spearman_avg = spearmanr(session_indices, average_trend)
        spearman_median = spearmanr(session_indices, median_trend)

        print("Pearson correlation (Session Index vs. Average):", pearson_avg)
        print("Pearson correlation (Session Index vs. Median):", pearson_median)
        print("Spearman correlation (Session Index vs. Average):", spearman_avg)
        print("Spearman correlation (Session Index vs. Median):", spearman_median)
    else:
        print("Not enough data points to calculate correlation of coverage trends.")

    # Generate and save line plot for average and median trends
    print("Generating average/median line plot...")
    plt.figure(figsize=(6, 4))
    plt.plot(session_indices, average_trend, label='Average', marker='o', color='blue', markersize=1, linewidth=1)
    plt.plot(session_indices, median_trend, label='Median', marker='s', color='orange', markersize=1, linewidth=1)
    plt.xlabel('Session Index (with >= 100 projects)')
    plt.ylabel('Coverage (%)')
    plt.title('Average and Median Coverage Over Time')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    lineplot_path = os.path.join(OUTPUT_DIR, 'average_median_lineplot.pdf')
    plt.savefig(lineplot_path, format='pdf')
    plt.close()
    print(f"Line plot saved to: {lineplot_path}")

    print("\n--- Main process finished ---")


if __name__ == '__main__':
    main()