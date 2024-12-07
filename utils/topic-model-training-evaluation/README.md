# CCAI Insights Topic Model Training Evaluation

This script exports an issue model from a CCAI Insights project to BigQuery for analysis and evaluation.

## Prerequisites

* **Google Cloud Project:** A Google Cloud project with billing enabled.
* **CCAI Insights Project:** An active CCAI Insights project with a trained issue model.
* **BigQuery Dataset:** A BigQuery dataset to store the exported issue model data.
* **Service Account:** A service account with permissions to access both GCS and BigQuery.
* **Google Colab:** This script is designed to run in a Google Colab environment.

## Setup

1. **Enable APIs:** Enable the following APIs in your Google Cloud project:
    * Cloud Storage API
    * BigQuery API
2. **Authentication:** Authenticate your Colab environment to access your Google Cloud project.
3. **Install Libraries:** Install the required libraries:
    ```bash
    pip install google-cloud-storage google-cloud-bigquery
    ```
4. **Export Issue Model:** In your CCAI Insights project, export the issue model as a JSON file to a GCS bucket.

## Usage

1. **Update Script:** Update the `import_issue_model_to_bq` function call with your:
    * GCS URI of the exported JSON file
    * BigQuery project ID
    * BigQuery dataset ID
    * BigQuery table ID
2. **Run Script:** Execute the script in your Colab environment.

## Script Details

The script performs the following actions:

1. **Reads Issue Model:** Reads the issue model JSON file from the specified GCS URI.
2. **Extracts Data:** Extracts relevant information from the JSON, such as issue names, display names, descriptions, and sample utterances.
3. **Creates BigQuery Table:** Creates a new table in the specified BigQuery dataset if it doesn't exist.
4. **Loads Data:** Loads the extracted issue model data into the BigQuery table.

## Evaluating Taxonomy in BigQuery

Once the issue model data is in BigQuery, you can use SQL queries to analyze and evaluate the taxonomy:

* **Issue Distribution:** Analyze the distribution of issues based on their frequency in the dataset.
* **Sample Utterance Analysis:** Examine the sample utterances associated with each issue to assess their relevance and diversity.
* **Issue Relationships:** Explore the relationships between different issues based on their co-occurrence in conversations.
* **Taxonomy Structure:** Evaluate the overall structure of the taxonomy and identify any potential gaps or inconsistencies.

## Example Queries

* **Count the number of issues:**
    ```sql
    SELECT COUNT(*) FROM `your-project.your_dataset.your_table`
    ```
* **List the top 10 most frequent issues:**
    ```sql
    SELECT displayName, COUNT(*) AS count FROM `your-project.your_dataset.your_table` GROUP BY displayName ORDER BY count DESC LIMIT 10
    ```
* **Show sample utterances for a specific issue:**
    ```sql
    SELECT sampleUtterances FROM `your-project.your_dataset.your_table` WHERE displayName = 'Your Issue Name'
    ```

This README provides a basic guide for using the script and evaluating the taxonomy. You can adapt the script and queries to your specific needs and use cases.


