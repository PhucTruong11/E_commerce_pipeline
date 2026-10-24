# Verified Linux/Python 3.13 base; update digest deliberately with the dependency lock.
ARG PYTHON_IMAGE=python:3.13-slim@sha256:57b29a7c050c4e679e4bea572e14b3965cf4b5839de2da49d55e49ffc4024f39
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 DBT_SEND_ANONYMOUS_USAGE_STATS=false \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 HOME=/tmp
WORKDIR /app
COPY requirements.lock.txt /app/requirements.lock.txt
RUN pip install --no-cache-dir -r requirements.lock.txt && pip check \
    && groupadd --gid 10001 ecom && useradd --uid 10001 --gid ecom --no-create-home ecom \
    && mkdir -p /state/build /state/releases /state/artifacts \
    && chown -R ecom:ecom /state
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY scripts /app/scripts
COPY ingestion /app/ingestion
COPY dbt /app/dbt
USER 10001:10001
ENTRYPOINT ["python", "-m", "scripts.environment"]
CMD ["check"]
