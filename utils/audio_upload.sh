#!/bin/bash
### audio_upload.sh

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

export source_audio_gcs_bucket=<SOURCE BUCKET NAME>
export xml_gcs_bucket=None
export agent_channel=1
export PROJECT_ID=<PROJECT ID>
export deidentify_template=projects/<PROJECT_ID>/locations/global/deidentifyTemplates/insights-demo-deidentify-template
export inspect_template=projects/<PROJECT_ID>/locations/global/inspectTemplates/insights-demo-inspect-template
export audio_format=flac
export agent_id=audio-upload


date +"%T.%3N"

python3 audio_upload.py --source_audio_gcs_bucket $source_audio_gcs_bucket --xml_gcs_bucket $xml_gcs_bucket --agent_channel $agent_channel --inspect_template $inspect_template --deidentify_template $deidentify_template --audio_format $audio_format --agent_id $agent_id $PROJECT_ID

date +"%T.%3N"