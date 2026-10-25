FROM python:3.12-slim
WORKDIR /app
COPY server.py native_ads.py viewing_context.py playback_identity.py local_signals.py realtime.py /app/
COPY sponsored_badge.py sponsored_template.json cover_mask.json /app/
ENV PYTHONUNBUFFERED=1
USER 65532:65532
EXPOSE 8080
CMD ["python", "/app/server.py"]
