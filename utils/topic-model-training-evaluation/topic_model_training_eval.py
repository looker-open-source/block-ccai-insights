from google.colab import auth
from google.cloud import storage
from google.cloud import bigquery
import json

def import_issue_model_to_bq(gcs_uri, project_id, dataset_id, table_id):
    """
    Imports issue model JSON from GCS to BigQuery in Colab environment

    Args:
        gcs_uri (str): GCS URI of the JSON file (gs://bucket/path)
        project_id (str): Target BigQuery project ID
        dataset_id (str): Target BigQuery dataset ID
        table_id (str): Target BigQuery table ID
    """
    # Parse bucket and blob path from GCS URI
    bucket_name = gcs_uri.split('/')[2]
    blob_path = '/'.join(gcs_uri.split('/')[3:])

    # Read JSON from GCS
    storage_client = storage.Client(project=project_id)
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(blob_path)
    content = json.loads(blob.download_as_string())

    # Extract issues data
    rows = []
    for issue in content.get('issues', []):
        row = {
            'name': issue.get('name'),
            'displayName': issue.get('displayName'),
            'displayDescription': issue.get('displayDescription'),
            'sampleUtterances': issue.get('sampleUtterances', [])
        }
        rows.append(row)

    # Define BigQuery schema
    schema = [
        bigquery.SchemaField('name', 'STRING'),
        bigquery.SchemaField('displayName', 'STRING'),
        bigquery.SchemaField('displayDescription', 'STRING'),
        bigquery.SchemaField('sampleUtterances', 'STRING', mode='REPEATED')
    ]

    # Initialize BigQuery client
    bq_client = bigquery.Client(project=project_id)
    table_ref = f"{project_id}.{dataset_id}.{table_id}"

    # Create table if it doesn't exist
    table = bigquery.Table(table_ref, schema=schema)
    table = bq_client.create_table(table, exists_ok=True)

    # Load data to BigQuery
    job_config = bigquery.LoadJobConfig()
    job_config.source_format = bigquery.SourceFormat.NEWLINE_DELIMITED_JSON
    job_config.schema = schema
    job_config.write_disposition = bigquery.WriteDisposition.WRITE_TRUNCATE

    job = bq_client.load_table_from_json(
        rows,
        table_ref,
        job_config=job_config
    )
    job.result()  # Wait for job to complete


import_issue_model_to_bq(
    'gs://cf-bucket-24812/model_export.json',
    'gsd-ccai-insights-offering',
    'insights_analytics',
    'issue_model_table'
)