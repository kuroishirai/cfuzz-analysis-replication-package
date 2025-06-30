FROM python:3.10-slim

WORKDIR /app

# lxmlビルドに必要なパッケージをすべてインストール
RUN apt-get update && apt-get install -y \
    git \
    libxml2-dev \
    libxslt1-dev \
    build-essential \
    python3-dev \
    && apt-get clean

COPY ./program /app/program
# COPY ./data /app/data
COPY requirements.txt /app/

# ★ wheel を先に入れて lxml のビルド失敗を防ぐ
RUN pip install --no-cache-dir wheel \
 && pip install --no-cache-dir lxml --use-pep517 \
 && pip install --no-cache-dir -r requirements.txt

CMD ["sleep", "infinity"]
