FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LAB_DATA_DIR=/data LAB_BIND=0.0.0.0 LAB_PORT=8795
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home lab
COPY detector.py storage.py server.py sponsored_badge.py sponsored_template.json ./
COPY train.py evaluate.py teacher_train.py ./
COPY diagnose.py ./
COPY review.html ./
RUN mkdir /data && chown lab:lab /data
USER lab
EXPOSE 8795
CMD ["python", "server.py"]
