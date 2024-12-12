# Block CCAI Insights

The Insights block allows you to export data from the CCAI Insights solution and
analyze it in Looker. The flexibility of the data model gives you the ability to
integrate Insights data with other first party data to unlock deep business
insights. Before utilizing this block, you will need to follow the instructions
for exporting the CCAI Insights data.

## Instructions

1. Copy each of files from the dashboards, models and views folders into a new
   LookML Project.
2. Copy the manifest.lkml file into the LookML project.
3. Update the db_connection_name constant in the manifest file with your db
   connection name.
4. Update the insights_table constant in the manifest file with your Insight
   export's dataset.table name.

**Note:** This Looker block is compatible with [BQ Schema
*v4](https://cloud.google.com/contact-center/insights/docs/bigquery-all-schemas)
*and higher

## Included in the Block:

+ Data Model: translates the CCAI Insights export schema and allows for
  customization of metrics.
+ One Explore: user-friendly point and click interface for performing ad-hoc
  queries.
+ Call Center Performance: Executive dashboard displaying high-level metrics
  intended for call center management.
+ Agent Performance: Performance metrics for an individual agent, linked from
  the Agent ID dimension.
+ Agent Operations: Performance metrics for agents in aggregate.
+ Conversation Lookup Dashboard: Detailed transcript and sentiment analysis for
  an individual conversation, linked from the Conversation Name dimension.

## Troubleshooting

Common LookML Error: "Ensure the database connection is working and the modeled
syntax is appropriate to the connections SQL dialect. Query execution failed: -
Name agents not found insight insights_data at [13:32]" The Insights BQ export
schema is still on v3 whereas the field "agents" is a nested field in v4+
schemas. You may need to request to allowlist your instance to a later version
and recreate the BQ export.