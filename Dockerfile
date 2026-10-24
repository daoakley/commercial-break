FROM python:3.12-slim
WORKDIR /app
COPY server.py /app/server.py
COPY sponsored_badge.py sponsored_template.json /app/
ENV PYTHONUNBUFFERED=1
USER 65532:65532
EXPOSE 8080
CMD ["python", "/app/server.py"]
