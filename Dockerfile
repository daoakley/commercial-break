FROM python:3.12-slim
WORKDIR /app
COPY server.py /app/server.py
COPY viewing_context.py /app/viewing_context.py
COPY playback_identity.py /app/playback_identity.py
COPY realtime.py local_signals.py cover_mask.json /app/
COPY sponsored_badge.py sponsored_template.json /app/
ENV PYTHONUNBUFFERED=1
USER 65532:65532
EXPOSE 8080
CMD ["python", "/app/server.py"]
