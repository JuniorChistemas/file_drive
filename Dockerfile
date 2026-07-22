FROM python:3.13-slim

RUN apt-get update && apt-get install -y \
    ghostscript \
    && rm -rf /var/lib/apt/lists/*

# Usuario no-root con UID/GID 1000 (coincide con el usuario host para los bind mounts)
RUN groupadd -g 1000 appuser && useradd -m -u 1000 -g appuser appuser

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Directorios de trabajo con ownership del usuario de la app
RUN mkdir -p /app/logs \
    /app/app/storage/temp \
    /app/app/storage/processed \
    /app/app/storage/failed \
    /app/app/storage/duplicated \
    && chown -R appuser:appuser /app

USER appuser

CMD ["python", "-m", "app.main"]
