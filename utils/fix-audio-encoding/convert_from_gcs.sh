#!/bin/bash
### convert_from_gcs.sh

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

export src_gcs_bucket="<Source bucket name>"
export dest_gcs_bucket="<Destination bucket name>"
export project_id="<GCP Project ID>"
export impersonated_service_account=None
export sample_rate="<Sample rate in hertz>"

date +"%T.%3N"

python3 convert_from_gcs.py --src_gcs_bucket $src_gcs_bucket --dest_gcs_bucket $dest_gcs_bucket --project_id $project_id --impersonated_service_account $impersonated_service_account --sample_rate_hertz $sample_rate

date +"%T.%3N"