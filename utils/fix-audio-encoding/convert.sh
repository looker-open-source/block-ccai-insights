#!/bin/bash
### convert.sh

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

export INPUT_AUDIO_PATH="<local input folder path>"
export OUTPUT_AUDIO_PATH="<local output folder path>"
echo $INPUT_AUDIO_PATH
echo $OUTPUT_AUDIO_PATH

date +"%T.%3N"
for x in $(find $INPUT_AUDIO_PATH -name "*.wav")
 do
   PREFIXPATH=${x%*/*}
   y=$(echo "$x" | cut -d"/" -f5)
         echo "$x"
         echo "$y"
   g=${y%%.*}
   ffmpeg -i "$x" -ar 8000 "$OUTPUT_AUDIO_PATH"/"$g".flac 
done
date +"%T.%3N"