#!/bin/bash

pip install -r requirements.txt

this_dir=$(pwd)
cp settings_template.yaml settings.yaml
sed -i '' "s|<aws_credentials_path>|$HOME/.aws/credentials|g" settings.yaml
sed -i '' "s|<log_path>|$this_dir/log|g" settings.yaml
mkdir -p $this_dir/log


