# CCAI Insights Topic Model Label Evaluation

This repository contains SQL code and resources for evaluating the efficacy of Topic Model labeling within CCAI Insights using BigQuery export data.

## Purpose

The provided SQL query analyzes conversation data exported from CCAI Insights to BigQuery. It focuses on assessing the performance of the Topic Model by comparing predicted topics with manually applied labels. This analysis helps to understand the accuracy and effectiveness of the Topic Model in categorizing conversations.

## SQL Query Logic

The query performs the following steps:

**Data Preparation:**

*   Declares and sets variables to define the BigQuery project, dataset, and table containing the CCAI Insights export data.
*   Constructs the `insights_table` variable to hold the fully qualified table name.
*   Defines a `query_string` variable that will hold the complete SQL query.

**Topic Aggregation:**

*   Uses a Common Table Expression (CTE) called `IssuesAgg` to group conversation data by `conversationName` and aggregate all predicted topics (`issues`) into an array named `issues_array`. The array is ordered by `score` in descending order, ensuring the top predicted topic is the first element.

**Label Aggregation:**

*   Uses another CTE called `LabelsAgg` to group conversation data by `conversationName` and aggregate all manually applied labels into a JSON string named `labels_json`.

**Data Extraction and Transformation:**

*   Joins the base table with the `IssuesAgg` and `LabelsAgg` CTEs on `conversationName`.
*   Extracts the top predicted topic name (`Top_Topic`) and its score (`Top_Topic_scores`) from the `issues_array`.
*   Extracts the names and scores of other predicted topics (`Other_topics` and `Other_topics_scores`) and concatenates them into comma-separated strings.
*   Includes the `labels_json` for comparison with predicted topics.
*   Generates a `random_seed` based on `conversationName` using `FARM_FINGERPRINT` for consistent ordering of results.

**Query Execution:**

*   Executes the dynamically constructed `query_string` using `EXECUTE IMMEDIATE`.

## How to Use

**Prerequisites:**

*   Access to a Google Cloud project with CCAI Insights enabled.
*   BigQuery dataset containing exported CCAI Insights data.
*   Understanding of SQL and BigQuery.

**Configuration:**

*   Modify the `project_id`, `dataset_id`, and `table_name` variables in the SQL code to match your BigQuery environment.

**Execution:**

*   Run the SQL query in the BigQuery console or using the `bq` command-line tool.

## Output

The query returns a table with the following columns:

*   `conversationName`: Unique identifier for each conversation.
*   `transcript`: Full conversation transcript.
*   `turnCount`: Number of turns in the conversation.
*   `agentId`: Identifier for the agent involved in the conversation.
*   `Top_Topic`: Name of the top predicted topic.
*   `Top_Topic_scores`: Score of the top predicted topic.
*   `Other_topics`: Comma-separated string of other predicted topic names.
*   `Other_topics_scores`: Comma-separated string of scores for other predicted topics.
*   `labels_json`: JSON string containing manually applied labels.
*   `random_seed`: Deterministic random seed for consistent ordering.

## Analysis

The output data can be used to:

*   Compare the `Top_Topic` with the `labels_json` to assess the accuracy of topic prediction.
*   Analyze the distribution of `Top_Topic` values to understand topic frequency.
*   Calculate the correlation between `Top_Topic_scores` and the presence of relevant labels.
*   Identify conversations where the Topic Model performed poorly and investigate potential reasons.

This analysis will provide valuable insights into the effectiveness of the Topic Model in labeling conversations and identify areas for potential improvement.

