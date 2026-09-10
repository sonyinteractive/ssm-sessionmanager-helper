# How It Works

The Configurator builds a string, based on user selections, which represents the command to the [AWS SSM Session Manager Plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html). 

When the user confirms their selection, the Configurator calls the command string that it built to establish the ssm session.

![connect](img/start-session.png "AWS SSM CLI")

## What It's Built On

The Configurator is written in Python and leverages the following libraries

    * boto3 - to connect to the AWS cli
    * prompt_toolkit - to build the ui
    * pytz - to regionalize times to UTC (which the aws cli reports with)

The Configurator is basically a state machine that displays dialogs written with `prompt_toolkit` to get user input in order to construct a command to call `aws ssm start-session`.

## UI Flow

1. Read AWS profile data from profiles stored in `~/.aws/credentials`
1. Display the profile selector dialog
1. Attempt to load the instances in `us-west-2` when the user selects a profile
1. Display the Configurator dialog
1. Display the Profile, Region or Instance dialogs based on user selection
1. Display the Confirmation dialog based on user selection
1. Close the UI and run the `aws ssm start-session` command on user confirmation
