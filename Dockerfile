# The page itself is not part of the image: it is uploaded into the /data volume
# via PUT /api/files/<name> (tools/publish.py), so updates need no rebuild.
FROM python:3.13-alpine

RUN adduser -D -H -u 10001 app && mkdir /data && chown app /data
COPY server/app.py /app/app.py

USER app
ENV DATA_DIR=/data PORT=8080 PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s CMD wget -qO- http://127.0.0.1:8080/health || exit 1

CMD ["python", "/app/app.py"]
