FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 ATT_DB_PATH=/data/attendance.db \
    FORWARDED_ALLOW_IPS="*"
# FORWARDED_ALLOW_IPS: cloud hosts (Render, Railway, Fly.io) and Caddy put a proxy in front of the app; trusting its
# X-Forwarded-For header gives every visitor their own rate limit instead of sharing the proxy's address.
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -r -u 10001 att && mkdir /data && chown att /data
COPY app ./app
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh
VOLUME /data
EXPOSE 8000
# PORT is set by most cloud hosts; 8000 otherwise
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import os,urllib.request as u;u.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\",\"8000\")}/healthz',timeout=3)"
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
