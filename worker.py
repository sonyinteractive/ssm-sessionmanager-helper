"""
worker.py

Contains utility functions used to establsh ssm connections
"""

import os
import logging
import subprocess
import platform
import yaml

from settings import Settings
from session import SessionState, SSM_MODE_IN_TERMINAL, SSM_MODE_PORT_FORWARDING
import socket


def is_port_in_use(port: str) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", int(port)))
            return False
        except OSError:
            return True


def parse_filepath(filepath: str) -> str:
    if filepath.startswith("~/"):
        cleanpath = filepath.replace("~/", "")
        return os.path.join(os.path.expanduser("~"), cleanpath)
    else:
        return filepath


def start_ssm_port_forwarding_sesion(
    session_state: SessionState, settings: Settings, in_new_window: bool = False
):
    selected_instance = session_state.get_selected_instance_id()
    command = f'aws ssm start-session --profile {session_state.get_selected_profile_name()} --region {session_state.get_selected_region_name()} --target {session_state.get_selected_instance_id()} --document-name {settings.get_ssm_document(SSM_MODE_PORT_FORWARDING)} --parameters portNumber=\\"{str(session_state.get_selected_remote_port())}\\",localPortNumber=\\"{str(session_state.get_selected_local_port())}\\"'
    windows_command = f'aws ssm start-session --profile {session_state.get_selected_profile_name()} --region {session_state.get_selected_region_name()} --target {session_state.get_selected_instance_id()} --document-name {settings.get_ssm_document(SSM_MODE_PORT_FORWARDING)} --parameters portNumber="{str(session_state.get_selected_remote_port())}",localPortNumber="{str(session_state.get_selected_local_port())}"'
    if in_new_window:
        os_system = platform.system()
        if os_system == "Darwin":
            logging.getLogger().info(
                f"[ssm-session-helper] Starting port-forwarding session with command: {command}"
            )
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'tell application "Terminal" to do script "{command}"',
                ]
            )
        elif os_system == "Windows":
            logging.getLogger().info(
                f"[ssm-session-helper] Starting port-forwarding session with command: {windows_command}"
            )
            subprocess.run(["cmd", "/c", "start", "cmd", "/k", windows_command])
    else:
        os.system(command)


def start_ssm_terminal_sesion(
    session_state: SessionState, settings: Settings, in_new_window: bool = False
):
    document_name = settings.get_ssm_document(SSM_MODE_IN_TERMINAL)

    if document_name is None or document_name == "":
        command = f"aws ssm start-session --profile {session_state.get_selected_profile_name()} --region {session_state.get_selected_region_name()} --target {session_state.get_selected_instance_id()}"
        win_command = f"aws ssm start-session --profile {session_state.get_selected_profile_name()} --region {session_state.get_selected_region_name()} --target {session_state.get_selected_instance_id()}"
    else:
        command = f"aws ssm start-session --profile {session_state.get_selected_profile_name()} --region {session_state.get_selected_region_name()} --target {session_state.get_selected_instance_id()} --document-name {document_name} "
        win_command = f"aws ssm start-session --profile {session_state.get_selected_profile_name()} --region {session_state.get_selected_region_name()} --target {session_state.get_selected_instance_id()} --document-name {document_name} "
    if in_new_window:
        os_system = platform.system()
        if os_system == "Darwin":
            logging.getLogger().info(
                f"[ssm-session-helper] Starting terminal session with command: {command}"
            )
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'tell application "Terminal" to do script "{command}"',
                ]
            )
        elif os_system == "Windows":
            logging.getLogger().info(
                f"[ssm-session-helper] Starting terminal session with command: {win_command}"
            )
            subprocess.run(["cmd", "/c", "start", "cmd", "/k", win_command])
    else:
        os.system(command)


# ---- Raw testing
# Load settings
# settings = Settings()
# filters = settings.get_instance_filters()

# # Select filter
# filter = settings.get_instance_filter('ab-initio')
# # filter = settings.get_instance_filter('ab-initio')
# filter_value = filter.get_filter_value()

# Retrieve aws session profiles from credentials file
# profiles = AWSSessionProfiles(os.path.expanduser('~/.aws/credentials'), supported_regions=settings.get_supported_regions(), default_region=settings.get_default_region())
# profiles.read_session_profiles()
# profiles.validate_profile_expiry()

# # Load instances
# region = "eu-west-2"
# for profile_name, profile_details in profiles.aws_profiles.items():
#     if 'sie-cloud-bis-nonprod-zz-mlu' in profile_name:
#         filter2 = settings.get_instance_filter('ab-initio')
#         profile_details.load_instances_from_boto(region, filter2)

#     # print(profile_details)
#     result1 = profile_details.get_cached_instances(region, filter)
#     result2 = profile_details.get_cached_instances(region, filter2)
#     print(result1.get_instance_filter().get_filter_name())
#     for instance in result1.get_instances_sorted(EC2InstanceResults.SORT_NAME_ASCENDING):
#         print(instance)
