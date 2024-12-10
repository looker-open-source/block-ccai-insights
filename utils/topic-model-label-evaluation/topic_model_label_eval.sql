-- Declare all variables at the start
DECLARE project_id STRING;
DECLARE dataset_id STRING;
DECLARE table_name STRING;
DECLARE insights_table STRING;
DECLARE query_string STRING;

-- Set variables
SET project_id = 'gsd-ccai-insights-offering';
SET dataset_id = 'ccai_insights_export';
SET table_name = 'test_export';

-- Concatenate to create fully qualified table name
SET insights_table = CONCAT(project_id, '.', dataset_id, '.', table_name);

-- Construct the query string
SET query_string = '''
WITH IssuesAgg AS (
 SELECT
   conversationName,
   ARRAY_AGG(issues_unnested ORDER BY issues_unnested.score DESC) AS issues_array
 FROM
   ''' || insights_table || ''',
   UNNEST(issues) AS issues_unnested
 GROUP BY
   conversationName
),


LabelsAgg AS (
 SELECT
   conversationName,
   STRING_AGG(TO_JSON_STRING(labels_unnested)) AS labels_json
 FROM
   ''' || insights_table || ''',
   UNNEST(labels) AS labels_unnested
 GROUP BY
   conversationName
)


SELECT
 main.conversationName,
 transcript,
 turnCount,
 agent.agentId,
 -- Extract top topic name from the first element in the ordered array
 JSON_EXTRACT_SCALAR(TO_JSON_STRING(issues_array[SAFE_OFFSET(0)]), '$.name') AS Top_Topic,
 -- Extract top topic score from the first element in the ordered array and cast to FLOAT64
 CAST(JSON_EXTRACT_SCALAR(TO_JSON_STRING(issues_array[SAFE_OFFSET(0)]), '$.score') AS FLOAT64) AS Top_Topic_scores,
 -- Extract names of other topics and concatenate them into a single string
 ARRAY_TO_STRING(
   ARRAY(
     SELECT
       JSON_EXTRACT_SCALAR(TO_JSON_STRING(issue), '$.name')
     FROM
       UNNEST(issues_array) AS issue
     WHERE
       issue != issues_array[SAFE_OFFSET(0)] -- Exclude the top topic
   ),
   ', '
 ) AS Other_topics,
 -- Extract scores of other topics, convert to string, and concatenate into a single string
 ARRAY_TO_STRING(
   ARRAY(
     SELECT
       CAST(JSON_EXTRACT_SCALAR(TO_JSON_STRING(issue), '$.score') AS STRING)
     FROM
       UNNEST(issues_array) AS issue
     WHERE
       issue != issues_array[SAFE_OFFSET(0)] -- Exclude the top topic
   ),
   ', '
 ) AS Other_topics_scores,
 l.labels_json,
 FARM_FINGERPRINT(main.conversationName) AS random_seed -- Create a random seed based on conversationName
FROM
 ''' || insights_table || ''' main
LEFT JOIN
 UNNEST(main.agents) AS agent -- Unnest the agents array to access agentId
LEFT JOIN
 IssuesAgg i ON main.conversationName = i.conversationName
LEFT JOIN
 LabelsAgg l ON main.conversationName = l.conversationName
ORDER BY
 random_seed -- Use the deterministic random seed for ordering
LIMIT 150;
''';


-- Execute the dynamically constructed query
EXECUTE IMMEDIATE query_string;