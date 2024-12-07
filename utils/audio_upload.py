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

Accepts a GCS bucket of source audio files.
For every audio file, a corresponding conversation will be created in Insights,
using Audio Upload feature which transcribes the audio using STT v2 recognizer
and perform redaction and model adaptation using DLP and phrase set templates
respectively. 
"""

import argparse
import os
import time
import xml.etree.ElementTree as ET
import google.auth
from google.auth import impersonated_credentials
import google.auth.transport.requests
from google.cloud import contact_center_insights_v1
from google.cloud import storage
import requests


def _ParseArgs():
  """Parse script arguments."""
  parser = argparse.ArgumentParser()
  # Create a groups of args where exactly one of them must be set.
  # source_group = parser.add_mutually_exclusive_group(required=True)
  source_group = parser.add_argument_group(title='Bucket name or local path')

  source_group.add_argument(
      '--source_audio_gcs_bucket',
      default=None,
      help=(
          'Path to a GCS bucket containing audio files to process as input. '
          'This bucket can be the same as the source bucket to colocate audio '
          'and transcript.'
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
      '--inspect_template',
      default=None,
      help='Template used for inspecting info types in DLP.',
  )

  parser.add_argument(
      '--deidentify_template',
      default=None,
      help='Template used for deidentifying info types in DLP.',
  )

  parser.add_argument(
      '--audio_format', default=None, help='Audio file format/extension.'
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


def _UploadInsightsConversation(
    endpoint,
    api_version,
    project,
    gcs_audio_uri,
    metadata,
    impersonated_service_account,
    inspect_template,
    deidentify_template,
    medium=None,
    agent_channel=1,
):
  """Uploads a conversation in Insights.

  Args:
    endpoint: The insights endpoint to use (prod, staging, etc).
    api_version: The Insights API version to use.
    project: The number of the project that will own the conversation.
    gcs_audio_uri: The uri of the GCS audio file.
    metadata: Data dictionary about conversations.
    impersonated_service_account: The service account to impersonate.
    inspect_template: Template to inspect info types in transcripts.
    deidentify_template: Template to deidentify the info types in transcripts.
    medium: The medium of the conversation. Defaults to 1 for voice.
    agent_channel: Channel on which agent utterances are recorded.

  Returns:
    The conversation ID of the created conversation.
  """
  oauth_token = _GetOauthToken(impersonated_service_account)
  url = (
      'https://{}/{}/projects/{}/locations/us-central1/conversations:upload'
  ).format(endpoint, api_version, project)
  headers = {
      'charset': 'utf-8',
      'Content-type': 'application/json',
      'Authorization': 'Bearer {}'.format(oauth_token),
  }
  data = {'data_source': {'gcs_source': {'audio_uri': gcs_audio_uri}}}

  if metadata:
    if metadata.get('agent_id', None):
      data['agent_id'] = metadata['agent_id']
      del metadata['agent_id']

    if metadata.get('agent_name', None):
      # data['agent_name'] = metadata['agent_name']
      del metadata['agent_name']

    if metadata:
      # set labels
      data['labels'] = metadata

  # print("data",data)
  # if gcs_audio_uri:
  #     data['data_source']['gcs_source']['transcript_uri'] = transcript_uri

  # if medium:
  #     data['medium'] = medium

  # set channel
  if agent_channel:
    data['call_metadata'] = {}
    if agent_channel == 1 or agent_channel == 3:
      data['call_metadata']['customer_channel'] = 2
      data['call_metadata']['agent_channel'] = 1
    else:
      data['call_metadata']['customer_channel'] = 1
      data['call_metadata']['agent_channel'] = agent_channel

  if inspect_template != 'None':
    redaction_config = {'inspect_template': inspect_template}
    if deidentify_template != 'None':
      redaction_config['deidentify_template'] = deidentify_template
    conversation = {'conversation': data, 'redaction_config': redaction_config}
  else:
    conversation = {'conversation': data}

  # print("conversation:",conversation)

  r = requests.post(url, headers=headers, json=conversation)
  if r.status_code == requests.codes.ok:
    # print('Successfully created conversation for audio uri `{}`.'
    # .format(gcs_audio_uri))
    return r.json()['name']
    # return r
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


def _GetGcsUris(bucket, project_id, impersonated_service_account, uri=True):
  """Returns a list of GCS uris for files in a bucket.

  Args:
      bucket: The GCS bucket.
      project_id: The project ID (not number) to use.
      impersonated_service_account: The service account to impersonate.
      uri: Whether to return gcs uri or not

  Returns:
      The GCS uris or file name.
  """
  uris = []
  metadata = []
  storage_client = storage.Client(
      project=project_id,
      credentials=_GetClientCredentials(impersonated_service_account),
  )
  blobs = storage_client.list_blobs(bucket)
  for blob in blobs:
    # Blobs ending in slashes are actually directory paths.
    if not blob.name.endswith('/'):
      # Redaction Error: >0.5MB transcript size
      # if blob.size<=1e7:
      if uri:
        uris.append(_GetGcsUri(bucket, blob.name))
      else:
        uris.append(blob.name)

      metadata.append(blob.metadata)
  return uris, metadata


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


def _GetOperation(operation_name):
  """Gets an operation.

  Args:
      operation_name: The operation name. Format is
        'projects/{project_id}/locations/{location_id}/operations/{operation_id}'.
        For example,
        'projects/my-project/locations/us-central1/operations/123456789'.

  Returns:
      An operation.
  """
  # Construct an Insights client that will authenticate via Application Default
  # Credentials.
  # See authentication details at
  # https://cloud.google.com/docs/authentication/production.
  insights_client = contact_center_insights_v1.ContactCenterInsightsClient()

  # Call the Insights client to get the operation.
  operation = insights_client.transport.operations_client.get_operation(
      operation_name
  )

  return operation


def _UploadBulkAudio(
    audio_uris,
    metadata,
    project_id,
    insights_endpoint,
    api_version,
    agent_id,
    impersonated_service_account,
    agent_channel,
    xml_bucket,
    inspect_template,
    deidentify_template,
    audio_format,
):
  """Create conversations in Insights for a list of audio uris.

  Args:
    audio_uris: The audio uris for which conversations should be created.
    metadata: Data about the audio files.
    project_id: The project ID (not number) to use for transcription,
      redaction, and Insights.
    insights_endpoint: The Insights endpoint to send requests.
    api_version: The Insights API version to use.
    agent_id: An agent identifier to attach to the conversations.
    impersonated_service_account: The service account to impersonate.
    agent_channel: The Agent Track.
    xml_bucket: Bucket where XML files present for MetaData ingestion.
    inspect_template: To inspect the info types
    deidentify_template: To de-identify the info types
    audio_format: Audio file format/extension

  Returns:
    A list of conversations IDs for the created conversations.
  """
  # conversation_names = []
  operation_names = []
  for audio_uri, metad in zip(audio_uris, metadata):
    # get metadata
    meta_data = {}
    if metad:
      meta_data = metad
    elif xml_bucket != 'None':
      tname = (
          audio_uri.replace('gs://', '')
          .split('/')[-1]
          .replace(f'.{audio_format}', '.xml')
      )
      # print(tname)
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

    operation_name = _UploadInsightsConversation(
        insights_endpoint,
        api_version,
        project_id,
        audio_uri,
        meta_data,
        impersonated_service_account,
        inspect_template,
        deidentify_template,
        medium=None,
        agent_channel=agent_channel,
    )
    # print(operation)
    # conversation_names.append(conversation)
    operation_names.append(operation_name)

    # sleep the ingestion to avoid exceeding quota
    time.sleep(1)

  # print(conversation_names)

  num_operations = len(operation_names)
  print(
      'Successfully scheduled `{}` audio upload operations.'.format(
          num_operations
      )
  )

  # operations = [_GetOperation(operation_name)
  # for operation_name in operation_names]
  # print([operation.done for operation in operations])
  # while operations:
  #     operations = [operation for operation in operations
  # if not operation.done]
  #     if not operations:
  #         break
  #     print('Still waiting for `{}` audio upload operations to complete'
  # .format(len(operations)))
  #     # Sleep to avoid exceeding Speech-to-text quota.
  #     time.sleep(1)
  # print('Finished waiting for all `{}` audio upload operations.'.format(
  #     num_operations))
  return operation_names


def _GetProcessedAudios(project_id):
  """Returns transcripts uri which are processed.

  Args:
    project_id: GCP Project Id

  Returns:
    audios: Transcripts uri which are processed
  """
  audios = []
  request = contact_center_insights_v1.ListConversationsRequest(
      parent=f'projects/{project_id}/locations/us-central1',
  )
  client = contact_center_insights_v1.ContactCenterInsightsClient()
  page_result = client.list_conversations(request=request)
  for response in page_result:
    audio = response.data_source.gcs_source.audio_uri
    if audio not in audios:
      audios.append(audio)
  return audios


def _RemoveProcessedFiles(audio_uris, processed_audio_files, metadata):
  """Removes the processed files from audio_uris.

  Args:
    audio_uris: Audio files to process.
    processed_audio_files: Processed audio files names.
    metadata: Data about the audio files.

  Returns:
    unprocessed_audio_uris: Files which are left to process.
    unprocessed_metadata: Metadata corresponding to the unprocessed files.
  """
  unprocessed_audio_uris = []
  unprocessed_metadata = []
  for file, metad in zip(audio_uris, metadata):
    if file not in processed_audio_files:
      unprocessed_audio_uris.append(file)
      unprocessed_metadata.append(metad)
  return unprocessed_audio_uris, unprocessed_metadata


def main():
  pargs = _ParseArgs()
  project_id = pargs.project_id
  impersonated_service_account = pargs.impersonated_service_account
  insights_endpoint = pargs.insights_endpoint
  api_version = pargs.insights_api_version
  agent_id = pargs.agent_id
  agent_channel = int(pargs.agent_channel)
  xml_bucket = pargs.xml_gcs_bucket
  # analyze_conv = pargs.analyze
  inspect_template = pargs.inspect_template
  deidentify_template = pargs.deidentify_template
  audio_format = pargs.audio_format

  source_audio_gcs_bucket = pargs.source_audio_gcs_bucket

  # pargs.source_local_audio_path or
  if source_audio_gcs_bucket:
    # Inputs are audio files.
    audio_uris, metadata = _GetGcsUris(
        source_audio_gcs_bucket, project_id, impersonated_service_account
    )

    # get processed audio files
    processed_audio_files = _GetProcessedAudios(project_id)

    # remove processed files
    audio_uris, metadata = _RemoveProcessedFiles(
        audio_uris, processed_audio_files, metadata
    )

    if not audio_uris:
      print('No audio file to process')
      # conversation_names = []
    else:
      operation_names = _UploadBulkAudio(
          audio_uris,
          metadata,
          project_id,
          insights_endpoint,
          api_version,
          agent_id,
          impersonated_service_account,
          agent_channel,
          xml_bucket,
          inspect_template,
          deidentify_template,
          audio_format,
      )
      print('Uploaded `{}` conversations'.format(
          len(operation_names)))

  else:
    print('Please provide audio files GCS bucket')


if __name__ == '__main__':
  main()