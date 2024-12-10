#    Copyright 2024 Google LLC

#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at

#        http://www.apache.org/licenses/LICENSE-2.0

#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

"""Imports conversations into Contact Center AI Insights.

Accepts either a local audio file or a GCS bucket of source audio files.
In the latter case, assumes that every file has the same audio properties.
Transcripts will be uploaded to the specified destination GCS bucket, and they
will be named with the same basename as the corresponding audio file.
For every audio file, a corresponding conversation will be created in Insights,
if metadata file(xml) is provided it will be added to the conversation.
Additionally, conditional on the `--analyze` flag, each conversation will also
be analyzed a single time. This allows the user to observe the results of
analysis after the script completes.
"""

import argparse
import os
import time
import xml.etree.ElementTree as ET
import google.auth
from google.auth import impersonated_credentials
import google.auth.transport.requests
from google.cloud import contact_center_insights_v1
from google.cloud import speech_v1p1beta1
from google.cloud import storage
import google.cloud.dlp_v2
from google.cloud.speech_v1p1beta1 import types as enums
import requests
import json
from urllib.parse import urlparse
from urllib.parse import urlunparse
import pickle


def _ParseArgs():
  """Parse script arguments."""
  parser = argparse.ArgumentParser()
  # Create a groups of args where exactly one of them must be set.
  # source_group = parser.add_mutually_exclusive_group(required=True)
  source_group = parser.add_argument_group(title='Bucket name or local path')
  source_group.add_argument(
      '--source_local_audio_path',
      help='Path to a local audio file to process as input.',
  )
  source_group.add_argument(
      '--source_audio_gcs_bucket',
      default=None,
      help=(
          'Path to a GCS bucket containing audio files to process as input. '
          'This bucket can be the same as the source bucket to colocate audio '
          'and transcript.'
      ),
  )
  source_group.add_argument(
      '--source_voice_transcript_gcs_bucket',
      help=(
          'Path to a GCS bucket containing voice transcripts to process as'
          ' input.'
      ),
  )
  source_group.add_argument(
      '--source_chat_transcript_gcs_bucket',
      help=(
          'Path to a GCS bucket containing chat transcripts to process as'
          ' input.'
      ),
  )
  parser.add_argument(
      '--dest_gcs_bucket',
      help=(
          'Name of the GCS bucket that will hold resulting transcript files.'
          ' Only relevant when providing audio files as input. Otherwise'
          ' ignored.'
      ),
  )
  parser.add_argument(
      'project_id',
      help='Project ID (not number) for the project to own the conversation.',
  )
  parser.add_argument(
      '--impersonated_service_account',
      help=(
          'A service account to impersonate. If specified, then GCP requests '
          'will be authenticated using service account impersonation. '
          'Otherwise, the gcloud default credential will be used.'
      ),
  )
  parser.add_argument(
      '--redact', default=False, help='Whether to redact the transcripts.'
  )
  parser.add_argument(
      '--analyze',
      default='False',
      help='Whether to analyze imported conversations. Default true.',
  )
  parser.add_argument(
      '--insights_endpoint',
      default='contactcenterinsights.googleapis.com',
      help='Name for the Insights endpoint to call',
  )
  parser.add_argument(
      '--language_code',
      default='en-US',
      help='Language code for all imported data.',
  )
  parser.add_argument(
      '--encoding', default='LINEAR16', help='Encoding for all imported data.'
  )
  parser.add_argument(
      '--sample_rate_hertz',
      default=0,
      type=int,
      help=(
          'Sample rate. If left out, Speech-to-text may infer it depending on '
          'the encoding.'
      ),
  )
  parser.add_argument(
      '--insights_api_version',
      default='v1',
      help='Insights API version. Options include `v1` and `v1alpha1`.',
  )
  parser.add_argument(
      '--agent_id',
      help='Agent identifier to attach to the created Insights conversations.',
  )
  parser.add_argument(
      '--agent_channel',
      default=2,
      help='Agent channel to attach to the created Insights conversations.',
  )
  parser.add_argument(
      '--xml_gcs_bucket',
      default=None,
      help='XML path to add labels to conversations.',
  )
  parser.add_argument(
      '--transcript_metadata_flag',
      default=None, 
      help=('''Flag will be set True if the metadata is present 
            inside the transcript''')
  )
  parser.add_argument(
      '--folder_name',
      default=None, 
      help=('''Folder name is required in case transcripts are present inside
            a folder and not in a bucket directly''')
  )
  return parser.parse_args()


def _DownloadFileFromGcs(
    bucket_name,
    source_blob_name,
    filename,
    project_id,
    impersonated_service_account,
):
  """Downloads a blob from the bucket.

  Args:
    bucket_name: The name of the GCS bucket that will hold the file.
    source_blob_name: Object blob to store.
    filename: Destination file name.
    project_id: The project ID (not number) to use for redaction.
    impersonated_service_account: The service account to impersonate.
  """
  storage_client = storage.Client(
      project=project_id,
      credentials=_GetClientCredentials(impersonated_service_account),
  )
  bucket = storage_client.bucket(bucket_name)
  blob = bucket.blob(source_blob_name)
  blob.download_to_filename(filename)


def _UploadFileToGcs(
    bucket_name,
    source_file_name,
    destination_blob_name,
    project_id,
    impersonated_service_account,
):
  """Uploads a local audio file to GCS.

  Args:
    bucket_name: The name of the GCS bucket that will hold the file.
    source_file_name: The name of the source file.
    destination_blob_name: The name of the blob that will be uploaded to GCS.
    project_id: The project ID (not number) to use for redaction.
    impersonated_service_account: The service account to impersonate.
  """
  storage_client = storage.Client(
      project=project_id,
      credentials=_GetClientCredentials(impersonated_service_account),
  )
  bucket = storage_client.bucket(bucket_name)
  blob = bucket.blob(destination_blob_name)
  blob.upload_from_filename(source_file_name)


def _TranscribeAsync(
    storage_uri,
    encoding,
    language_code,
    sample_rate_hertz,
    impersonated_service_account,
):
  """Transcribe long audio file from Cloud Storage.

  Args:
      storage_uri: URI for audio file in Cloud Storage, e.g.
        gs://[BUCKET]/[FILE]
      encoding: The encoding to use for transcription
      language_code: The language code to use for transcription
      sample_rate_hertz: The sample rate of the audio
      impersonated_service_account: The service account to impersonate.

  Returns:
      The transcription operation, which can be polled until done.
  """
  encoding_map = {
      'LINEAR16': enums.RecognitionConfig.AudioEncoding.LINEAR16,
      'MP3': enums.RecognitionConfig.AudioEncoding.MP3,
      'FLAC': enums.RecognitionConfig.AudioEncoding.FLAC,
      'AMR': enums.RecognitionConfig.AudioEncoding.AMR,
      'AMR_WB': enums.RecognitionConfig.AudioEncoding.AMR_WB,
      'OGG_OPUS': enums.RecognitionConfig.AudioEncoding.OGG_OPUS,
      'SPEEX_WITH_HEADER_BYTE': (
          enums.RecognitionConfig.AudioEncoding.SPEEX_WITH_HEADER_BYTE
      ),
  }
  # The recognition configuration. Assumes the audio is a two-channel phone
  # call.

  config = {
      'language_code': language_code,
      'encoding': encoding_map[encoding],
      'model': 'phone_call',
      'audio_channel_count': 2,
      'use_enhanced': True,
      'enable_separate_recognition_per_channel': True,
      'enable_automatic_punctuation': True,
      'enable_word_time_offsets': True,
  }
  if sample_rate_hertz > 0:
    config['sample_rate_hertz'] = sample_rate_hertz
  client = speech_v1p1beta1.SpeechClient(
      credentials=_GetClientCredentials(impersonated_service_account)
  )

  # changed: Error passed 3 args to long_running_recognize
  audio_file = speech_v1p1beta1.RecognitionAudio(uri=storage_uri)
  #   audio = {'uri': storage_uri}

  try:
    operation = client.long_running_recognize(config=config, audio=audio_file)
    return operation
  except google.api_core.exceptions.GoogleAPIError as e:
    print(
        'Error `{}` when scheduling async transcription for storage uri {}'
        .format(e, storage_uri)
    )
    return None


def _Redact(transcript_response, project_id, impersonated_service_account):
  """Redacts a transcript response.

  Args:
      transcript_response: The response from transcription.
      project_id: The project ID (not number) to use for redaction.
      impersonated_service_account: The service account to impersonate.

  Returns:
      The response from transcription.
  """
  dlp = google.cloud.dlp_v2.DlpServiceClient(
      #   project=project_id,
      credentials=_GetClientCredentials(impersonated_service_account)
  )

  # The list of types to redact. Making this too aggressive can damage word time
  # offsets. Eventually, a better solution could be determined than sending the
  # entire STT response to DLP so that only the transcript parts would be
  # potentially redacted.
  info_types = [
      'AGE',
      'CREDIT_CARD_NUMBER',
      'CREDIT_CARD_TRACK_NUMBER',
      'DOMAIN_NAME',
      'EMAIL_ADDRESS',
      'FEMALE_NAME',
      'MALE_NAME',
      'FIRST_NAME',
      'GENDER',
      'GENERIC_ID',
      'IP_ADDRESS',
      'LAST_NAME',
      'LOCATION',
      'PERSON_NAME',
      'PHONE_NUMBER',
      'STREET_ADDRESS',
  ]
  inspect_config = {
      'info_types': [{'name': info_type} for info_type in info_types]
  }
  deidentify_config = {
      'info_type_transformations': {
          'transformations': [
              {
                  'primitive_transformation': {
                      'character_mask_config': {
                          # Will replace PII terms with a series of '*'.
                          'masking_character': '*',
                          # Zero means no limit on characters to redact.
                          'number_to_mask': 0,
                      }
                  }
              }
          ]
      }
  }

  project_path = f'projects/{project_id}'
  item = {'value': str(transcript_response)}
  response = dlp.deidentify_content(
      request={
          'parent': project_path,
          'deidentify_config': deidentify_config,
          'inspect_config': inspect_config,
          'item': item,
      }
  )
  return response.item.value


def _RedactTranscript(transcript_response, project_id, \
                      impersonated_service_account):

  """Redacts a transcript response.

  Args:
      transcript_response: The response from transcription.
      project_id: The project ID (not number) to use for redaction.
      impersonated_service_account: The service account to impersonate.

  Returns:
      The response from transcription.
  """

  dlp = google.cloud.dlp_v2.DlpServiceClient(
      credentials=_GetClientCredentials(impersonated_service_account),
  )

  transcript_dict = json.loads(transcript_response)

  entry_list = transcript_dict['entries']

  headers = [{'name': key} for key in entry_list[0].keys()]

  rows = []
  for element in entry_list:
    rows.append(
        {
            'values': [
                {'string_value': str(element['start_timestamp_usec'])},
                {'string_value': element['text']},
                {'string_value': element['role']},
                {'string_value': str(element['user_id'])},
            ]
        }
    )

  items = {'table': {'headers': headers, 'rows': rows}}
  info_types = [
      'AGE',
      'CREDIT_CARD_NUMBER',
      'CREDIT_CARD_TRACK_NUMBER',
      'DOMAIN_NAME',
      'EMAIL_ADDRESS',
      'FEMALE_NAME',
      'MALE_NAME',
      'FIRST_NAME',
      'GENDER',
      'GENERIC_ID',
      'IP_ADDRESS',
      'LAST_NAME',
      'LOCATION',
      'PERSON_NAME',
      'PHONE_NUMBER',
      'STREET_ADDRESS',
  ]
  deidentify_config = {
      'record_transformations': {
          'field_transformations': [{
              'fields': [{'name': 'text'}],
              'info_type_transformations': {
                  'transformations': [{
                      'primitive_transformation': {
                          'character_mask_config': {'masking_character': '*'}
                      },
                      'info_types': [
                          {'name': info_type} for info_type in info_types
                      ],
                  }]
              },
          }]
      }
  }
  inspect_config = {
      'info_types': [{'name': info_type} for info_type in info_types]
  }

  project_path = f'projects/{project_id}'
  response = dlp.deidentify_content(
      request={
          'parent': project_path,
          'deidentify_config': deidentify_config,
          'inspect_config': inspect_config,
          'item': items,
      }
  )
  return_list = []
  for row in response.item.table.rows:
    row_list = []
    for col in row.values:
      if 'string_value' in col:
        row_list.append(col.string_value)
    return_list.append(row_list)
  json_entries_list = []
  for entry in return_list:
    json_entry = {
        'start_timestamp_usec': str(entry[0]),
        'text': entry[1],
        'role': entry[2],
        'user_id': int(entry[3]),
    }
    json_entries_list.append(json_entry)
  transcript_dict['entries'] = json_entries_list
  return transcript_dict


def _UploadTranscript(
    transcript_response,
    bucket,
    transcript_file_name,
    project_id,
    impersonated_service_account,
):
  """Uploads an audio file transcript to GCS.

  Args:
      transcript_response: The response from transcription.
      bucket: The bucket that will hold the transcript
      transcript_file_name: The name of the file that will be uploaded.
      project_id: The project ID (not number) to use for redaction.
      impersonated_service_account: The service account to impersonate.
  """
  # Use an identifier that is unique across transcriptions to prevent a race.
  tmp_file = 'tmp-{}-{}'.format(bucket, transcript_file_name)
  f = open(tmp_file, 'w')
  f.write(str(transcript_response))
  f.close()
  _UploadFileToGcs(
      bucket,
      tmp_file,
      transcript_file_name,
      project_id,
      impersonated_service_account,
  )
  os.remove(tmp_file)


def _CreateInsightsConversation(
    endpoint,
    api_version,
    project,
    gcs_audio_uri,
    gcs_transcript_uri,
    metadata,
    impersonated_service_account,
    medium=None,
    agent_channel=1,
):
  """Creates a conversation in Insights.

  Args:
      endpoint: The insights endpoint to use (prod, staging, etc)
      api_version: The Insights API version to use.
      project: The number of the project that will own the conversation
      gcs_audio_uri: The uri of the GCS audio file.
      gcs_transcript_uri: The uri of the GCS transcript file.
      metadata: Data about the conversation.
      impersonated_service_account: The service account to impersonate.
      medium: The medium of the conversation. Defaults to 1 for voice.
      agent_channel: The Agent track.

  Returns:
      The conversation ID of the created conversation.
  """
  oauth_token = _GetOauthToken(impersonated_service_account)
  url = (
      'https://{}/{}/projects/{}/locations/us-central1/conversations'
  ).format(endpoint, api_version, project)
  headers = {
      'charset': 'utf-8',
      'Content-type': 'application/json',
      'Authorization': 'Bearer {}'.format(oauth_token),
  }
  data = {'data_source': {'gcs_source': {'transcript_uri': gcs_transcript_uri}}}

  if metadata:
    if metadata['agent_id']:
      data['agent_id'] = metadata['agent_id']
      del metadata['agent_id']

    # set labels
    data['labels'] = metadata

  if gcs_audio_uri:
    data['data_source']['gcs_source']['audio_uri'] = gcs_audio_uri
  if medium:
    data['medium'] = medium

  # set channel
  if agent_channel:
    data['call_metadata'] = {}
    if agent_channel == 1:
      data['call_metadata']['customer_channel'] = 2
    else:
      data['call_metadata']['customer_channel'] = 1
    data['call_metadata']['agent_channel'] = agent_channel

  r = requests.post(url, headers=headers, json=data)
  if r.status_code == requests.codes.ok:
    print(
        'Successfully created conversation for transcript uri `{}` '
        'and audio uri `{}`.'.format(gcs_transcript_uri, gcs_audio_uri)
    )
    return r.json()['name']
  else:
    r.raise_for_status()


def _GetGcsUri(bucket, object_name):
  """Returns a GCS uri for the given bucket and object.

  Args:
      bucket: The bucket in the URI.
      object_name: The name of the object.

  Returns:
      The GCS uri.
  """
  return 'gs://{}/{}'.format(bucket, object_name)


def _GetGcsUris(bucket, project_id, impersonated_service_account,
                folder_name=None, uri=True):
  """Returns a list of GCS uris for files in a bucket.
  
  Args:
      bucket: The GCS bucket.
      project_id: The project ID (not number) to use.
      impersonated_service_account: The service account to impersonate.
      folder_name: Folder path if the file is inside a nested path inside bucket
      uri: Whether to return gcs uri or not
  Returns:
      The GCS uris or file name.
  """
  uris = []
  storage_client = storage.Client(
      project=project_id,
      credentials=_GetClientCredentials(impersonated_service_account))
  blobs = storage_client.list_blobs(bucket, prefix=folder_name)
  for blob in blobs:
    # Blobs ending in slashes are actually directory paths.
    if not blob.name.endswith('/'):
      # Redaction Error: 0.5MB size
      if blob.size <= 1e7:
        if uri:
          uris.append(_GetGcsUri(bucket, blob.name))
        else:
          uris.append(blob.name)
  return uris


def _GetClientCredentials(impersonated_service_account):
  """Gets client credentials for GCP requests.

  If an account to impersonate is provided, then it will be used rather than the
  default. Otherwise, default gcloud credentials will be used.

  Args:
      impersonated_service_account: The service account to impersonate.

  Returns:
      A credential for requests to GCP.
  """
  creds, _ = google.auth.default(
      scopes=['https://www.googleapis.com/auth/cloud-platform']
  )
  if not impersonated_service_account:
    return creds
  target_scopes = ['https://www.googleapis.com/auth/cloud-platform']
  target_credentials = impersonated_credentials.Credentials(
      source_credentials=creds,
      target_principal=impersonated_service_account,
      target_scopes=target_scopes,
      lifetime=3600,
  )
  # Override the source credentials so refresh will work.
  # See https://github.com/googleapis/google-auth-library-python/issues/416.
  # pylint: disable=protected-access
  target_credentials._source_credentials._scopes = creds.scopes
  return target_credentials


def _GetOauthToken(impersonated_service_account):
  """Gets an oauth token to use for HTTP requests to GCP.

  Assumes usage of Gcloud credentials.

  Args:
      impersonated_service_account: The service account to impersonate.

  Returns:
      The oauth token.
  """
  creds = _GetClientCredentials(impersonated_service_account)
  auth_req = google.auth.transport.requests.Request()
  creds.refresh(auth_req)
  return creds.token


# Needs modification based on customer's XML structure/fields
def _GetMetaData(file):
  """Parse XML file to get metadata.

  Args:
      file: XML file name

  Returns:
      data: Dictionary consisting of metadata
  """
  tree = ET.parse(file)
  root = tree.getroot()

  data = {}
  data['duration'] = str(root[0][1].text)
  data['agent_id'] = str(root[0][6].text)
  data['channel'] = str(root[0][8].text)
  data['sid'] = str(root[0][10].text)
  data['dbs'] = str(root[0][11].text)
  data['no_of_holds'] = str(root[0][13].text)
  data['hold_time'] = str(root[0][16].text)

  return data


def _GetMetaDataFromTranscription(file):
  """Parse JSON transcription file to get metadata.

  Args:
      file: JSON file name

  Returns:
      data: Dictionary consisting of metadata
  """
  with open(file) as transcription_file:
    transcription = json.load(transcription_file)   
  print(transcription['conversation_info'])
  meta_data = {}
  meta_data['ucid'] = transcription['conversation_info']['ucid']
  meta_data['agent_login_id'] = transcription['conversation_info']\
      ['agent_login_id']
  meta_data['dt_skey'] = transcription['conversation_info']['dt_skey']
  meta_data['src_scope'] = transcription['conversation_info']['src_scope']
  meta_data['src_divsn'] = transcription['conversation_info']['src_divsn']
  meta_data['src_sub_divsn'] = transcription['conversation_info']\
      ['src_sub_divsn']
  return meta_data


def _GetTranscribeAsyncCallback(
    project_id,
    dest_bucket,
    audio_uri,
    insights_endpoint,
    api_version,
    should_redact,
    agent_id,
    conversation_names,
    impersonated_service_account,
    agent_channel,
    xml_bucket,
):
  """A callback for asynchronous transcription.

  Args:
      project_id: The GCP project ID (not number) to hold the Insights
        conversation object.
      dest_bucket: The destination GCS bucket for the transcript file.
      audio_uri: The uri of the audio file that was transcribed.
      insights_endpoint: The endpoint for the Insights API.
      api_version: The Insights API version to use.
      should_redact: Whether to redact the transcription before saving.
      agent_id: An agent identifier to attach to the conversations.
      conversation_names: The list of conversation IDs created.
      impersonated_service_account: The service account to impersonate.
      agent_channel: The Agent track.
      xml_bucket: Bucket where XML files present for MetaData ingestion.

  Returns:
      The callback for asynchronous transcription.
  """

  def Callback(future):
    try:
      response = future.result()
      # print('response generated')
    except google.api_core.exceptions.GoogleAPICallError as e:
      print(
          'Error `{}`: failed to transcribe audio uri `{}` with operation `{}`'
          ' and error `{}`.'.format(
              e, audio_uri, future.operation.name, future.exception()
          )
      )
      return

    # time.sleep(1)
    try:
      if should_redact == 'True':
        # print('redacting')
        response = _Redact(response, project_id, impersonated_service_account)
    except google.api_core.exceptions.GoogleAPICallError as e:
      print(
          'Error `{}`: failed to redact transcription from audio uri `{}`.'
          .format(e, audio_uri)
      )
      return
    # print('After redacting')
    # time.sleep(1)
    transcript_name = '{}.txt'.format(
        os.path.basename(os.path.splitext(audio_uri)[0])
    )
    try:
      _UploadTranscript(
          response,
          dest_bucket,
          transcript_name,
          project_id,
          impersonated_service_account,
      )
      # print('uploaded transcript')
    except google.api_core.exceptions.GoogleAPICallError as e:
      print(
          'Error `{}`: failed to upload transcription from audio uri `{}`.'
          .format(e, audio_uri)
      )
      return
    # time.sleep(1)

    transcript_uri = _GetGcsUri(dest_bucket, transcript_name)
    try:
      # print('transcript_uri',transcript_uri)

      meta_data = {}
      if xml_bucket != 'None':
        tname = transcript_name.replace('.txt', '.xml')
        xml_file_path = f'/tmp/{tname}'  # f'{xml_path}/{tname}'
        _DownloadFileFromGcs(
            xml_bucket,
            tname,
            xml_file_path,
            project_id,
            impersonated_service_account,
        )
        meta_data = _GetMetaData(xml_file_path)
        # print("meta_data",meta_data)
        os.remove(xml_file_path)
      elif agent_id != 'None':
        meta_data['agent_id'] = agent_id

      conversation_name = _CreateInsightsConversation(
          insights_endpoint,
          api_version,
          project_id,
          audio_uri,
          transcript_uri,
          meta_data,
          impersonated_service_account,
          medium=None,
          agent_channel=agent_channel,
      )
      # print('conversation_name',conversation_name)
      # Note: Appending to a python list is thread-safe, hence no lock.
      conversation_names.append(conversation_name)
    except requests.exceptions.HTTPError as e:
      print(
          'Error `{}`: failed to create insights conversation from audio uri '
          '{} and transcript uri `{}`.'.format(e, audio_uri, transcript_uri)
      )

  return Callback


def _AddRedactedFolderToGcsUri(gcs_uri):
  """Create an intermediate path for redacted files.

  Args:
    gcs_uri: GCS uri where the transcripts are stored

  Returns: 
    Modified uri with redacted folder added before the file name
  """
  parsed_url = urlparse(gcs_uri)
  path_parts = parsed_url.path.split('/')
  path_parts.insert(1, 'redacted')
  modified_path = '/'.join(path_parts)
  modified_url = parsed_url._replace(path=modified_path)
  return urlunparse(modified_url)


def _ImportConversationsFromTranscript(
    transcript_uris,
    project_id,
    medium,
    insights_endpoint,
    api_version,
    should_redact,
    agent_id,
    impersonated_service_account,
    agent_channel,
    xml_bucket,
    transcript_bucket,
    transcript_metadata_flag
):
  """Create conversations in Insights for a list of transcript uris.

  Args:
      transcript_uris: The transcript uris for which conversations should be 
      created.
      project_id: The project ID (not number) to use for redaction and Insights.
      medium: The medium (1 for voice, 2 for chat).
      insights_endpoint: The Insights endpoint to send requests.
      api_version: The Insights API version to use.
      should_redact: Whether to redact transcriptions with DLP.
      agent_id: An agent identifier to attach to the conversations.
      impersonated_service_account: The service account to impersonate.
      agent_channel: channel of the agent
      xml_bucket: xml bucket for metadata
      transcript_bucket: bucket where transcript is stored
      transcript_metadata_flag: flag that specifies if metadata is present 
      inside transcript

  Returns:
      A list of conversations IDs for the created conversations.
  """

  conversation_names = []
  for transcript_uri in transcript_uris:
    meta_data = {}
    metadata_processed = False

    if should_redact == 'True':
      file_name = "/".join(transcript_uri.split("/")[3:])
      json_file_path = f'/tmp/{file_name.split("/")[-1]}'
      _DownloadFileFromGcs(
          transcript_bucket,
          file_name,
          json_file_path,
          project_id,
          impersonated_service_account
      )

      with open(json_file_path) as file:
        transcription = file.read()
        redacted_string = _RedactTranscript(transcription, project_id,
                                            impersonated_service_account)
        #type(redacted_string)  
      redacted_json_file_path = f'/tmp/{"redacted_"+file_name.split("/")[-1]}'
      redacted_string = json.dumps(redacted_string, indent=None)

      with open(redacted_json_file_path, "w") as redacted_file:
        redacted_file.write(redacted_string.replace('\\',""))
      redacted_blob_path = "redacted/"+file_name
      transcript_uri = "gs://"+transcript_bucket+"/"+redacted_blob_path

      _UploadFileToGcs(transcript_bucket, redacted_json_file_path,
                       redacted_blob_path, project_id,
                       impersonated_service_account)
      os.remove(redacted_json_file_path)
      if transcript_metadata_flag == 'True':
        meta_data = _GetMetaDataFromTranscription(json_file_path)
        if agent_id != 'None':
          meta_data['agent_id'] = agent_id
        metadata_processed = True
      os.remove(json_file_path)

    if xml_bucket != 'None' and metadata_processed == False:
      tname = transcript_uri.replace('.txt', '.xml')
      xml_file_path = f'/tmp/{tname}'#f'{xml_path}/{tname}'
      _DownloadFileFromGcs(
          xml_bucket,
          tname, 
          xml_file_path,
          project_id, 
          impersonated_service_account
      )
      meta_data = _GetMetaData(xml_file_path)
      os.remove(xml_file_path)

    elif transcript_metadata_flag == 'True' and metadata_processed == False:
      file_name = "/".join(transcript_uri.split("/")[3:])
      json_file_path = f'/tmp/{file_name.split("/")[-1]}'
      _DownloadFileFromGcs(
          transcript_bucket,
          file_name, 
          json_file_path,
          project_id, 
          impersonated_service_account
      )
      meta_data = _GetMetaDataFromTranscription(json_file_path)

      os.remove(json_file_path)
      if agent_id != 'None':
        meta_data['agent_id'] = agent_id

    elif agent_id != 'None' and metadata_processed == False:
      meta_data['agent_id'] = agent_id

    conversation_name = _CreateInsightsConversation(
        insights_endpoint,
        api_version,
        project_id,
        None,
        transcript_uri,
        meta_data,
        impersonated_service_account,
        medium,
        agent_channel=agent_channel,
    )
    conversation_names.append(conversation_name)
    # Sleep to avoid exceeding Insights quota.
    time.sleep(1)
  return conversation_names


def _ImportConversationsFromAudio(
    audio_uris,
    encoding,
    language_code,
    sample_rate_hertz,
    project_id,
    dest_bucket,
    insights_endpoint,
    api_version,
    should_redact,
    agent_id,
    impersonated_service_account,
    agent_channel,
    xml_bucket,
):
  """Create conversations in Insights for a list of audio uris.

  Args:
      audio_uris: The audio uris for which conversations should be created.
      encoding: The language encoding for Speech-to-text.
      language_code: The language code for Speech-to-text.
      sample_rate_hertz: The sample rate of the audios.
      project_id: The project ID (not number) to use for transcription,
        redaction, and Insights.
      dest_bucket: The destination GCS bucket for transcriptions.
      insights_endpoint: The Insights endpoint to send requests.
      api_version: The Insights API version to use.
      should_redact: Whether to redact transcriptions with DLP.
      agent_id: An agent identifier to attach to the conversations.
      impersonated_service_account: The service account to impersonate.
      agent_channel: The Agent Track.
      xml_bucket: Bucket where XML files present for MetaData ingestion.

  Returns:
      A list of conversations IDs for the created conversations.
  """
  conversation_names = []
  operations = []
  for audio_uri in audio_uris:
    operation = _TranscribeAsync(
        audio_uri,
        encoding,
        language_code,
        sample_rate_hertz,
        impersonated_service_account,
    )
    if not operation:
      continue
    operation.add_done_callback(
        # pylint: disable=too-many-function-args
        _GetTranscribeAsyncCallback(
            project_id,
            dest_bucket,
            audio_uri,
            insights_endpoint,
            api_version,
            should_redact,
            agent_id,
            conversation_names,
            impersonated_service_account,
            agent_channel,
            xml_bucket,
        )
    )
    operations.append(operation)
    # Sleep to avoid exceeding Speech-to-text quota.
    time.sleep(2)

  num_operations = len(operations)
  print(
      'Successfully scheduled `{}` transcription operations.'.format(
          num_operations
      )
  )

  while operations:
    operations = [operation for operation in operations if not operation.done()]
    if not operations:
      break
    print(
        'Still waiting for `{}` transcription operations to complete'.format(
            len(operations)
        )
    )
    # Sleep to avoid exceeding Speech-to-text quota.
    time.sleep(5)
  print(
      'Finished waiting for all `{}` transcription operations.'.format(
          num_operations
      )
  )
  return conversation_names


def _AnalyzeConversations(
    conversation_names,
    insights_endpoint,
    api_version,
    impersonated_service_account,
):
  """Analyzes the provided list of conversations.

  Args:
      conversation_names: The list of conversations to analyze.
      insights_endpoint: The Insights endpoint to call.
      api_version: The Insights API version to use.
      impersonated_service_account: The service account to impersonate.
  """
  analysis_operations = []
  oauth_token = _GetOauthToken(impersonated_service_account)
  headers = {
      'charset': 'utf-8',
      'Content-type': 'application/json',
      'Authorization': 'Bearer {}'.format(oauth_token),
  }

  for conversation_name in conversation_names:
    try:
      url = 'https://{}/{}/{}/analyses'.format(
          insights_endpoint, api_version, conversation_name
      )
      r = requests.post(url, headers=headers)
      print('Started analysis for conversation `{}`'.format(conversation_name))
      # Sleep to avoid exceeding Create Analysis quota in Insights.
      time.sleep(2)
      if r.status_code == requests.codes.ok:
        analysis_operations.append(r.json()['name'])
      else:
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
      print(
          'Error `{}`: failed to create analysis for conversation `{}`.'.format(
              e, conversation_name
          )
      )
  print(
      'Successfully scheduled `{}` analysis operations: {}'.format(
          len(analysis_operations), analysis_operations
      )
  )

  finished_operations = []

  while len(finished_operations) < len(analysis_operations):
    for analysis_operation in analysis_operations:
      try:
        url = 'https://{}/{}/{}'.format(
            insights_endpoint, api_version, analysis_operation
        )
        r = requests.get(url, headers=headers)
        if r.status_code == requests.codes.ok:
          json = r.json()
        else:
          json = {}

        if 'done' in json and json.get('done', None):
          finished_operations.append(analysis_operation)
        else:
          r.raise_for_status()
      except requests.exceptions.HTTPError as e:
        print(
            'Error `{}`: failed to poll analysis operation `{}`.'.format(
                e, analysis_operation
            )
        )
      time.sleep(1)
    time.sleep(5)
  print(
      'All `{}` analysis operations have finished.'.format(
          len(analysis_operations)
      )
  )


def _GetProcessedTranscripts(project_id):
  """Returns transcripts uri which are processed.

  Args:
      project_id: GCP Project Id

  Returns:
      transcripts: Transcripts uri which are processed
  """
  transcripts = []
  request = contact_center_insights_v1.ListConversationsRequest(
      parent=f'projects/{project_id}/locations/us-central1',
  )
  client = contact_center_insights_v1.ContactCenterInsightsClient()
  page_result = client.list_conversations(request=request)
  for response in page_result:
    # print(response.data_source.gcs_source.transcript_uri)
    transcript = response.data_source.gcs_source.transcript_uri
    if transcript not in transcripts:
      transcripts.append(response.data_source.gcs_source.transcript_uri)
  return transcripts


def _RemoveProcessedFiles(audio_uris, processed_audio_files):
  """Removes the processed files from audio_uris.

  Args:
      audio_uris: Audio files to process
      processed_audio_files: Processed audio files names

  Returns:
      unprocessed_audio_uris: Files which are left to process
  """
  unprocessed_audio_uris = []
  for file in audio_uris:
    if file.split('/')[-1].split('.')[0] not in processed_audio_files:
      unprocessed_audio_uris.append(file)
  return unprocessed_audio_uris


def main():
  pargs = _ParseArgs()
  project_id = pargs.project_id
  impersonated_service_account = pargs.impersonated_service_account
  insights_endpoint = pargs.insights_endpoint
  api_version = pargs.insights_api_version
  should_redact = pargs.redact
  agent_id = pargs.agent_id
  agent_channel = int(pargs.agent_channel)
  xml_bucket = pargs.xml_gcs_bucket
  analyze_conv = pargs.analyze
  folder_name = pargs.folder_name

  if pargs.source_local_audio_path or pargs.source_audio_gcs_bucket:
    # Inputs are audio files.
    dest_bucket = pargs.dest_gcs_bucket
    if pargs.source_local_audio_path:
      source_local_audio_path = pargs.source_local_audio_path
      source_audio_base_name = os.path.basename(source_local_audio_path)
      _UploadFileToGcs(
          dest_bucket,
          source_local_audio_path,
          source_audio_base_name,
          project_id,
          impersonated_service_account,
      )
      audio_uris = [_GetGcsUri(dest_bucket, source_audio_base_name)]
    elif pargs.source_audio_gcs_bucket:
      audio_uris = _GetGcsUris(
          pargs.source_audio_gcs_bucket,
          project_id,
          impersonated_service_account,
      )
      # print(audio_uris)
    else:
      audio_uris = []

    encoding = pargs.encoding
    language_code = pargs.language_code
    sample_rate_hertz = pargs.sample_rate_hertz

    # get processed audio files
    processed_audio_files = _GetGcsUris(
        dest_bucket, project_id, impersonated_service_account, uri=False
    )
    processed_audio_files = list(
        map(lambda x: x.split('.')[0], processed_audio_files)
    )

    # remove processed files
    audio_uris = _RemoveProcessedFiles(audio_uris, processed_audio_files)

    if not audio_uris:
      print('No audio file to process')
      conversation_names = []
    else:
      conversation_names = _ImportConversationsFromAudio(
          audio_uris,
          encoding,
          language_code,
          sample_rate_hertz,
          project_id,
          dest_bucket,
          insights_endpoint,
          api_version,
          should_redact,
          agent_id,
          impersonated_service_account,
          agent_channel,
          xml_bucket,
      )
  else:
    # Inputs are transcript files.
    if pargs.source_voice_transcript_gcs_bucket:
      medium = 1
      print(pargs.source_voice_transcript_gcs_bucket)
      transcript_bucket = pargs.source_voice_transcript_gcs_bucket
    elif pargs.source_chat_transcript_gcs_bucket:
      print(pargs.source_chat_transcript_gcs_bucket)
      transcript_bucket = pargs.source_chat_transcript_gcs_bucket
      medium = 2
    else:
      print('Provide at least one bucket for (Audio/Chat)')
      return

    transcript_metadata_flag = pargs.transcript_metadata_flag
    transcript_uris = _GetGcsUris(transcript_bucket, project_id,
                                  impersonated_service_account, folder_name)

    # get processed transcripts
    processed_transcripts_uris = _GetProcessedTranscripts(project_id)

    unprocessed_transcript_uris = []

    # filter processed transcripts
    if should_redact == 'True':
      for transcript_uri in transcript_uris:
        redacted_uri = _AddRedactedFolderToGcsUri(transcript_uri)
        if redacted_uri not in processed_transcripts_uris:
          unprocessed_transcript_uris.append(transcript_uri)
    else:
      unprocessed_transcript_uris = [
          i for i in transcript_uris if i not in processed_transcripts_uris
          ]
      print('Total transcripts', len(unprocessed_transcript_uris))

    with open('transcripts_uris', 'wb') as fp:
      pickle.dump(transcript_uris, fp)

    if not transcript_uris:
      print('No transcript to ingest')
      conversation_names = []
    else:
      conversation_names = _ImportConversationsFromTranscript(
          unprocessed_transcript_uris, project_id, medium, insights_endpoint,
          api_version, should_redact, agent_id,
          impersonated_service_account, agent_channel, xml_bucket, 
          transcript_bucket, transcript_metadata_flag)

  print(
      'Created `{}` conversation IDs: {}'.format(
          len(conversation_names), conversation_names
      )
  )

  if analyze_conv == 'True':
    print('Starting analysis for conversations.')
    _AnalyzeConversations(
        conversation_names,
        insights_endpoint,
        api_version,
        impersonated_service_account,
    )


if __name__ == '__main__':
  main()