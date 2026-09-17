FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY static/ ./static/
COPY workflows/ ./workflows/

# /state is a Docker named volume by default, and a new named volume takes its
# ownership from whatever is at that path in the image. The uid the container
# runs as is the operator's choice (RUN_AS), so it cannot be chowned to one
# here - 1777 is what /tmp does, and this is a private volume holding one app's
# settings.
RUN mkdir -p /state && chmod 1777 /state

# Nothing is written inside the image itself, so there is no reason to be root.
RUN useradd --uid 1001 --create-home appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
