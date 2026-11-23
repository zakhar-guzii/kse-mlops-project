FROM apache/airflow:3.3.1-python3.12

# Same versions as uv.lock; change them together.
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" numpy==2.5.5 rasterio==1.5.2 "psycopg[binary]==3.3.9"
