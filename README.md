# Block CCAI Insights

The Insights block allows you to export data from the CCAI Insights solution and analyze it in Looker. The flexibility of the data model gives you the ability to integrate Insights data with other first party data to unlock deep business insights.

Before utilizing this block, you will need to follow the instructions for exporting the [CCAI Insights data.](https://cloud.google.com/contact-center/insights/docs/export)

**Note:** you will need to set the job to run on a schedule with appropriate filters or integrate with Cloud Data Fusion. Do not utilize the Export button in the Insights interface as there are currently limits on the number of records able to be exported as well as no ability to append data in the target table.

**Included in the Block:**

+ Data Model: translates the CCAI Insights export schema and allows for customization of metrics.
+ One Explore: user-friendly point and click interface for performing ad-hoc queries.
+ Call Center Performance: Executive dashboard displaying high-level metrics intended for call center management.
+ Agent Performance: Performance metrics for an individual agent, linked from the Agent ID dimension.
+ Agent Operations: Performance metrics for agents in aggregate.
+ Conversation Lookup Dashboard: Detailed transcript and sentiment analysis for an individual conversation, linked from the Conversation Name dimension.
