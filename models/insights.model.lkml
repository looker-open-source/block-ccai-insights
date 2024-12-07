connection: "@{CONNECTION_NAME}"

# include all the views
include: "/views/**/*.view" # Include All Views
include: "/dashboards/*.dashboard.lookml" # Include All Dashboards

datagroup: insights_default_datagroup {
  # sql_trigger: SELECT MAX(id) FROM etl_log;;
  max_cache_age: "1 hour"
}

persist_with: insights_default_datagroup

explore: insights_data {
  label: "CCAI Insights"
  join: insights_data__words {
    view_label: "4: Words"
    sql: LEFT JOIN UNNEST(${insights_data.words}) as insights_data__words ;;
    relationship: one_to_many
  }

  join: insights_data__labels {
    view_label: "1: Conversations"
    sql: LEFT JOIN UNNEST(${insights_data.labels}) as insights_data__labels ;;
    relationship: one_to_many
  }

  join: insights_data__topics {
    view_label: "1: Conversations"
    sql: LEFT JOIN UNNEST(${insights_data.topics}) as insights_data__topics ;;
    relationship: one_to_many
  }

  join: insights_data__entities {
    view_label: "3: Entities"
    sql: LEFT JOIN UNNEST(${insights_data.entities}) as insights_data__entities ;;
    relationship: one_to_many
  }

  join: insights_data__sentences {
    view_label: "2: Sentences"
    sql: LEFT JOIN UNNEST(${insights_data.sentences}) as insights_data__sentences ;;
    relationship: one_to_many
  }

  join: insights_data__sentences__annotations {
    view_label: "2: Sentences"

    sql: LEFT JOIN UNNEST(${insights_data__sentences.annotations}) as insights_data__sentences__annotations ;;
    relationship: one_to_many
  }

  join: insights_data__sentences__intent_match_data {
    view_label: "2: Sentences"
    sql: LEFT JOIN UNNEST(${insights_data__sentences.intent_match_data}) as insights_data__sentences__intent_match_data ;;
    relationship: one_to_many
  }

  join: insights_data__sentences__phrase_match_data {
    view_label: "2: Sentences"
    sql: LEFT JOIN UNNEST(${insights_data__sentences.phrase_match_data}) as insights_data__sentences__phrase_match_data ;;
    relationship: one_to_many
  }

  join: insights_data__sentences__dialogflow_intent_match_data {
    view_label: "2: Sentences"
    sql: LEFT JOIN UNNEST(${insights_data__sentences.dialogflow_intent_match_data}) as insights_data__sentences__dialogflow_intent_match_data ;;
    relationship: one_to_many
  }

  join: sentence_turn_number {
    view_label: "2: Sentences"
    relationship: one_to_many
    sql_on: ${insights_data.conversation_name}=${sentence_turn_number.conversation_name}
    and ${insights_data__sentences.sentence} = ${sentence_turn_number.sentence}
    and ${insights_data__sentences.created_raw} = ${sentence_turn_number.created_raw};;
  }

  join: human_agent_turns {
    view_label: "1: Conversations"
    relationship: one_to_one
    sql_on: ${insights_data.conversation_name} = ${human_agent_turns.conversation_name} ;;
  }

  join: daily_facts {
    view_label: "1: Conversations"
    relationship: many_to_one
    sql_on: ${insights_data.load_date}=${daily_facts.load_date} AND ${insights_data.type} = ${daily_facts.conversation_type};;
  }

}
