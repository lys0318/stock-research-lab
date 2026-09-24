FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 LAB_DATA_DIR=/tmp/lab OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
COPY pyproject.toml ./
COPY lab ./lab
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt && pip install --no-cache-dir --no-deps .
USER 10001
ENTRYPOINT ["python", "-m", "lab.cloud", "worker"]
