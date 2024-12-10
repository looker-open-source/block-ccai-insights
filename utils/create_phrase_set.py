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

"""Create PhraseSet to provide hints to the speech recognizer.

To favor specific words and phrases in the results.
"""

from google.api_core import client_options
from google.cloud import speech_v2
from google.cloud.speech_v2.types import cloud_speech


def create_phrase_set(
    project_id,
    phrase_set_id,
    phrases
):
  """Creates PhraseSet based on the provided phrases.
    
  Args:
      project_id: GCP Project Id
      phrase_set_id: Name given to the phrase set
      phrases: List of words and phrases 
  """
  options = client_options.ClientOptions(api_endpoint="speech.googleapis.com")
  # Create a client
  client = speech_v2.SpeechClient(client_options=options)

  # Create a persistent PhraseSet to reference in a recognition request
  request = cloud_speech.CreatePhraseSetRequest(
      parent=f"projects/{project_id}/locations/global",
      phrase_set_id=phrase_set_id,
      phrase_set=cloud_speech.PhraseSet(phrases=[{"value": phrase, "boost": 20}
                                                 for phrase in phrases]),
  )

  operation = client.create_phrase_set(request=request)
  phrase_set = operation.result()

  print("phrase_set\n", phrase_set)


PROJECT_ID = "<PROJECT_ID>"
PHRASE_SET_ID = "<NAME FOR PHRASE SET>"
PHRASES = ["<PHRASES>"]

create_phrase_set(
    PROJECT_ID,
    PHRASE_SET_ID,
    PHRASES
)