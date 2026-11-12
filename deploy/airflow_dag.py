# Optional: run under Airflow instead of systemd/cron.
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG("cloudera_ai_health", start_date=datetime(2026, 1, 1), schedule="*/15 * * * *",
         catchup=False, default_args={"retries": 1, "retry_delay": timedelta(minutes=2)}) as dag:
    BashOperator(task_id="health_check",
                 bash_command="cd /opt/cdp-health && .venv/bin/python -m cdp_health --config config.yaml || [ $? -le 2 ]")
