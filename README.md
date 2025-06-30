# 📦 cfuzz-analysis-replication-package

This repository provides a replication package for the paper analyzing the relationship between fuzzing coverage and vulnerability detection.  
It includes data collection, storage, and analysis scripts using Docker and PostgreSQL.

## 📁 Directory Structure

```
.
├── data/
│   ├── processed_data/csv/
│   └── database/backup_clean.sql
├── program/
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/kuroishirai/cfuzz-analysis-replication-package.git
cd cfuzz-analysis-replication-package
```

### 2. Prepare your data

Place large files (e.g. CSVs, SQL dump) in the `data/` directory manually:

```
data/
├── processed_data/csv/
│   ├── issues.csv
│   ├── coverage_data.csv
│   ├── buildlog_data.csv
│   ├── buildlog_metadata.csv
│   └── ...
└── database/
    └── backup_clean.sql
```

> ⚠️ Do not commit large files to GitHub. Files >100MB will be rejected.

## 🐳 Docker Setup

### Reset Docker (Optional)

```bash
docker compose down --volumes
docker volume ls
docker volume rm fuzzingeffectiveness_pgdata
docker system prune -a --volumes -f
```

### Build and Launch

```bash
docker compose build --no-cache
docker compose up -d
```

## 🗃️ Restore Database

```bash
docker compose exec -T db psql -U replication_user -d replication_db < data/database/backup_clean.sql
```

## ✅ Run Analysis Programs

```bash
docker compose run --rm research python program/research_questions/rq1_detection_rate.py
docker compose run --rm research python program/research_questions/rq2_coverage_count.py
docker compose run --rm research python program/research_questions/rq3_diff_coverage_at_detection.py
```
