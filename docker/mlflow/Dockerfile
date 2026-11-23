FROM ghcr.io/mlflow/mlflow:v3.16.1

# The image has neither a PostgreSQL driver nor an S3 client.
RUN pip install --no-cache-dir psycopg2-binary==2.9.13 boto3==1.44.9
