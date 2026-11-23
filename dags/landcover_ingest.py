"""One run ingests one batch: the batch_id parameter, else the year of data_interval_start.

"@yearly" uses CronTriggerTimetable, so a backfill run for 2019-01-01 has
data_interval_start 2019-01-01 and loads the 2019 batch. In Airflow 3.3.1 a plain
`dags trigger --logical-date` takes its interval from the trigger time instead.
"""

import os

import pendulum
from airflow.sdk import Param, dag, task

from landcover import pipeline


@dag(
    schedule="@yearly",
    start_date=pendulum.datetime(2017, 1, 1, tz="UTC"),
    end_date=pendulum.datetime(2022, 1, 1, tz="UTC"),
    catchup=False,
    params={"batch_id": Param(None, type=["null", "string"])},
)
def landcover_ingest():
    @task
    def extract(params=None, data_interval_start=None):
        year = data_interval_start.year if data_interval_start else None
        batch_id = pipeline.resolve_batch(params["batch_id"], year)
        return {"batch_id": batch_id, "tile_ids": pipeline.extract(pipeline.batch_dir(batch_id))}

    @task
    def validate(batch):
        pipeline.validate(pipeline.batch_dir(batch["batch_id"]), batch["tile_ids"])
        return batch

    @task
    def transform(batch):
        rows = pipeline.transform(pipeline.batch_dir(batch["batch_id"]), batch["tile_ids"])
        return {"batch_id": batch["batch_id"], "rows": rows}

    @task
    def load(batch):
        pipeline.load(os.environ["WAREHOUSE_DSN"], batch["batch_id"], batch["rows"])
        return batch["batch_id"]

    @task
    def build_features(batch_id):
        pipeline.build_features(os.environ["WAREHOUSE_DSN"], batch_id)
        return batch_id

    @task
    def quality_check(batch_id):
        share = pipeline.quality_check(os.environ["WAREHOUSE_DSN"], batch_id)
        print(f"{batch_id}: ignored-pixel share {share:.3f} <= {pipeline.MAX_IGNORED_SHARE}")

    quality_check(build_features(load(transform(validate(extract())))))


landcover_ingest()
