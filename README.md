# FuzzingEffectiveness Replication Package

This repository contains the replication package for the study on the effectiveness of fuzzing. It includes scripts for data scraping, preprocessing, database storage, and analysis using Docker and PostgreSQL.

## 📦 Project Structure

```
FuzzingEffectiveness/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── data/
│   └── database/
│       └── backup_clean.sql       # Pre-cleaned database dump for reproducibility
├── program/
│   ├── preparation/               # Scripts for collecting and transforming data
│   │   ├── 1_get_projects_infos.py
│   │   ├── 2_transform_data.py
│   │   └── 3_get_coverage_data.py
│   ├── research_questions/        # Scripts for answering specific research questions
│   │   ├── rq1_detection_rate.py
│   │   ├── rq2_coverage_count.py
│   │   └── ...
│   └── test_db_connection.py      # Simple connection test to PostgreSQL
├── envFile.ini                    # Environment variables for DB settings
└── README.md
```

## 🚀 Getting Started

### 1. Requirements

- Docker
- Docker Compose

### 2. Configuration

Edit `envFile.ini` if needed (not required for basic usage):

```ini
[POSTGRES]
POSTGRES_DB = replication_db
POSTGRES_USER = replication_user
POSTGRES_PASSWORD = replication_pass
POSTGRES_PORT = 5432
POSTGRES_IP = db
```

### 3. Build and Run the Environment

```bash
docker compose build
docker compose up
```

### 4. Import Database Dump (Optional)

If not automatically imported, run:

```bash
docker compose exec -T db psql -U replication_user -d replication_db < data/database/backup_clean.sql
```

## 🧪 Run Scripts

You can run individual scripts inside the container:

```bash
# Test database connection
docker compose run --rm research python program/test_db_connection.py

# Run research question analysis (example)
docker compose run --rm research python program/research_questions/rq2_coverage_count.py
```

## 🗃️ Notes

- All code is tested to run inside a Docker container.
- The PostgreSQL service uses persistent volume storage (`pgdata`).
- All credentials and sensitive data have been removed from the final dump `backup_clean.sql`.

## 📄 License

This project is part of a replication package for academic research.  
Please cite appropriately if you use it in your work.
