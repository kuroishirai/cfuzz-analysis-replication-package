import sys
import os
import csv
import numpy as np
import matplotlib.pyplot as plt
from configparser import ConfigParser
from tqdm import tqdm
from scipy import stats
from matplotlib.ticker import FuncFormatter


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
def print_summary_statistics(data, name):
    """Calculates and prints summary statistics in a table format."""
    print(f"\n--- Summary Statistics for '{name}' Group ---")
    
    if not data:
        print("No data available.")
        return

    data_np = np.array(data)
    total_count = len(data_np)
    
    # Proportions
    positive_prop = np.sum(data_np > 0) / total_count * 100 if total_count > 0 else 0
    zero_prop = np.sum(data_np == 0) / total_count * 100 if total_count > 0 else 0
    negative_prop = np.sum(data_np < 0) / total_count * 100 if total_count > 0 else 0
    
    # Representative values
    mean_val = np.mean(data_np)
    median_val = np.median(data_np)
    std_val = np.std(data_np)
    min_val = np.min(data_np)
    max_val = np.max(data_np)
    q1_val = np.percentile(data_np, 25)
    q3_val = np.percentile(data_np, 75)
    

    # Print table
    print(f"+--------------------------+----------------------+")
    print(f"| Metric                   | Value                |")
    print(f"+--------------------------+----------------------+")
    print(f"| Count                    | {total_count:<20} |")
    print(f"| Positive Change Rate (%) | {f'{positive_prop:.2f}':<20} |")
    print(f"| Zero Change Rate (%)     | {f'{zero_prop:.2f}':<20} |")
    print(f"| Negative Change Rate (%) | {f'{negative_prop:.2f}':<20} |")
    print(f"| Mean                     | {f'{mean_val:.4f}':<20} |")
    print(f"| Median                   | {f'{median_val:.4f}':<20} |")
    print(f"| Std. Deviation           | {f'{std_val:.4f}':<20} |")
    print(f"| Min                      | {f'{min_val:.4f}':<20} |")
    print(f"| Q1                       | {f'{q1_val:.4f}':<20} |")
    print(f"| Q3                       | {f'{q3_val:.4f}':<20} |")
    print(f"| Max                      | {f'{max_val:.4f}':<20} |")
    print(f"+--------------------------+----------------------+")



def create_boxplot(output_path, values):
    box_edge_color = '#444444'
    linthresh = 0.01  # 線形領域を小さく設定
    widths = 0.7
    key = 'Coverage'
    
    # plt.figure(figsize=(1.5, 2.5))
    plt.figure(figsize=(2.0, 2.5))
    # バイオリンプロットを追加（縦向きにする）
    # violin_parts = plt.violinplot(values, showmeans=False, showmedians=False, showextrema=False, vert=True, widths=0.7) # vpの幅
    # for pc in violin_parts['bodies']:
    #     pc.set_facecolor('#A3BCE2')  # ライトブルー
    #     pc.set_edgecolor('black')   # VPの枠線
    #     pc.set_alpha(0.5)
    
    # 箱ひげ図を追加（縦向きにする）
    box = plt.boxplot(values, patch_artist=True, widths=0.5, showfliers=True)#, whis=[0, 100])   # 箱ひげ図の幅
    for patch in box['boxes']:
        patch.set_facecolor('#e3eefa')  # ライトブルー
        patch.set_linewidth(widths)    # 枠全部の太さ
        patch.set_edgecolor(box_edge_color)    # 箱の枠
    
    # 中央値の線の太さを変更
    plt.setp(box['medians'], color='#FF0000', linewidth=0.3)  # 中央値の線の太さを変更
    
    # 四分位範囲の線を太くする
    for whisker in box['whiskers']:
        whisker.set_linewidth(widths)
        whisker.set_color(box_edge_color)     # 繋ぐ線
        
    for cap in box['caps']:
        cap.set_linewidth(widths)
        cap.set_color(box_edge_color)         # 箱の上下の線
    
    # 外れ値の表示（大きさ，色，透明度）を変更
    for flier in box['fliers']:
        flier.set(marker='o', alpha=0.5, markersize=2, markeredgewidth=0.2, markeredgecolor='#c83c3c')  # 外れ値の設定と枠の太さと枠のカラー
    
    mean_value = np.mean(values)
    
    
    
    
    # stats_funcs.check_normal(values)
    
    
    plt.scatter(1, mean_value, color='#2f6ba3', marker='^', s=15, zorder=3, label='Mean')  # 平均値を赤い点で表示

    plt.ylabel(f'{key} Difference')
    plt.xticks([])
    
    # symlogスケールと目盛り設定
    plt.yscale('symlog', linthresh=linthresh)

    if key != 'Coverage':
        plt.subplots_adjust(left=0.433, right=0.99, top=0.97, bottom=0.008)
    else:
        plt.ylim(-100, 100)
        plt.subplots_adjust(left=0.43, right=0.99, top=0.972, bottom=0.017)

        # 目盛り位置を設定
        ticks = [-10**2, -10**1, -1, -0.1, -0.01, 0, 0.01, 0.1, 1, 10**1, 10**2]
        plt.yticks(ticks)

        # 目盛りラベルをフォーマット
        def symlog_label_formatter(x, pos):
            if x == 0:
                return "0"
            exponent = int(np.log10(abs(x)))
            if x < 0:
                return f"$-10^{{{exponent}}}$"
            return f"$10^{{{exponent}}}$"
            # return x

        plt.gca().get_yaxis().set_major_formatter(FuncFormatter(symlog_label_formatter))



    # 図をPDF形式で保存
    plt.tight_layout(pad=0)
    plt.savefig(output_path, bbox_inches='tight')
    plt.close()



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
    count = [0,0,0,0,0,0,0,0,0]
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
            # print(current_project, len(fuzzing_builds), len(coverage_builds), len(total_coverages))

        if not fuzzing_builds or not coverage_builds or not total_coverages:
            continue
        # --- Link issue to builds and coverage data ---
        last_fuzz_build = next((b for b in reversed(fuzzing_builds) if b[0] < issue_timestamp), None)
        if not last_fuzz_build:
            continue
            
        first_cov_build = next((b for b in coverage_builds if b[0] > issue_timestamp), None)
        if not first_cov_build or first_cov_build[3] not in ['HalfWay', 'Finish']:
            continue
            
        if (first_cov_build[0] - last_fuzz_build[0]).total_seconds() / 3600 > 24:
            continue
        
        if sorted(last_fuzz_build[2][1:-2].split(',')) != sorted(first_cov_build[2][1:-2].split(',')):
            continue
        
        # same
        
        # --- Find the corresponding coverage change ---
        coverage_change_pair = []
        for i in range(1,len(total_coverages)):
            if (total_coverages[i][0].date() - issue_timestamp.date()).days == 1:
                if total_coverages[i][1] == 0:
                    break
                coverage_change_pair = [total_coverages[i-1], total_coverages[i]]
                break
        if len(coverage_change_pair) == 0:
            continue
        if len(coverage_change_pair) == 2:
            prev_cov, curr_cov = coverage_change_pair
            if len(prev_cov) > 2 and len(curr_cov) > 2 and prev_cov[2] > 0 and curr_cov[2] > 0: # Avoid division by zero and index errors
                diff_percent = (curr_cov[1] / curr_cov[2] - prev_cov[1] / prev_cov[2]) * 100
                diff_covered = curr_cov[1] - prev_cov[1]
                diff_total = curr_cov[2] - prev_cov[2]
                # ★★★ 修正点 1: issue_timestampをリストに追加 ★★★
                detected_changes.append([diff_percent, diff_covered, diff_total, project_name, issue_timestamp])

    print(f"\nFound {len(detected_changes)} instances of coverage change on bug detection.")
    
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
    
    # --- Print Summary Statistics ---
    print_summary_statistics(detected_coverage_diffs, "Detected")
    print_summary_statistics(non_detected_coverage_diffs, "Not Detected")
    print_summary_statistics([d[2] for d in detected_changes], "Detected Total")

    stat, p_value = stats.levene(detected_coverage_diffs, non_detected_coverage_diffs)

    print(f"Levene's test statistic: {stat:.4f}")
    print(f"P-value: {p_value:.4f}")

    stat, p_value = stats.brunnermunzel(detected_coverage_diffs, non_detected_coverage_diffs)

    print(f"Brunner-Munzel W statistic: {stat:.4f}")
    print(f"P-value: {p_value:.4f}")
    
    
    create_comparison_plots(detected_coverage_diffs, non_detected_coverage_diffs)
    
    create_boxplot(os.path.join(OUTPUT_DIR, 'detected.pdf'), detected_coverage_diffs)
    create_boxplot(os.path.join(OUTPUT_DIR, 'non_detected.pdf'), non_detected_coverage_diffs)
    
    print("\n--- RQ3 Analysis Finished ---")

if __name__ == '__main__':
    main()