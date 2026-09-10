"""
session.py

Contains SessionState class used to model the state of the current session
"""

import logging
from aws_model import (
    InstanceFilter,
    Profile,
    ProfileCollection,
)
from settings import Settings
import constants as const

SSM_MODE_IN_TERMINAL = "terminal"
SSM_MODE_PORT_FORWARDING = "port-forwarding"


class SessionState:
    """Representation of the current selected values in the UI."""

    __settings: Settings

    __selected_profile_name: str
    __selected_region_name: str
    __selected_instance_filter_name: str

    __selected_instance_id: str
    __selected_local_port: str
    __selected_remote_port: str
    __selected_ssm_mode: str

    def __init__(self, settings: Settings, profile_collection: ProfileCollection):
        self.__settings: Settings

        active_profiles = profile_collection.get_active_profiles()
        inactive_profiles = (
            profile_collection.get_expired_profiles()
            + profile_collection.get_errored_profiles()
        )

        selected_profile = (
            active_profiles[0]
            if len(active_profiles) > 0
            else inactive_profiles[0] if len(inactive_profiles) > 0 else None
        )
        self.__selected_profile_name = (
            selected_profile.get_profile_name() if selected_profile is not None else ""
        )
        self.__selected_region_name = settings.get_default_region_name()
        self.__selected_instance_filter_name = (
            settings.get_default_instance_filter().get_filter_name()
        )
        self.__selected_local_port = const.DEFAULT_LOCAL_PORT
        self.__selected_remote_port = const.DEFAULT_REMOTE_PORT
        self.__selected_instance_id = ""
        self.__selected_ssm_mode = const.SSM_MODE_IN_TERMINAL

        self.log_current_selected_values()

    def log_current_selected_values(self):
        logging.getLogger().info(
            f"""
[ssm-session-helper] Session selected values:
    Profile name: {self.__selected_profile_name}
    Region name: {self.__selected_region_name}
    Instance filter: {self.__selected_instance_filter_name}
    Local port: {self.__selected_local_port}
    Remote port: {self.__selected_remote_port}
    Selected instance: {self.__selected_instance_id}
    Selected ssm mode: {self.__selected_ssm_mode}
"""
        )

    def set_settings(self, settings: Settings):
        self.__settings = settings

    def set_selected_profile_name(self, selected_profile_name: str):
        self.__selected_profile_name = selected_profile_name

    def set_selected_region(self, selected_region_name: str):
        self.__selected_region_name = selected_region_name

    def set_selected_instance_filter_name(self, selected_instance_filter_name: str):
        self.__selected_instance_filter_name = selected_instance_filter_name

    def set_selected_instance_id(self, instance_id: str):
        self.__selected_instance_id = instance_id

    def set_selected_local_port(self, selected_local_port: str):
        self.__selected_local_port = selected_local_port

    def set_selected_remote_port(self, selected_remote_port: str):
        self.__selected_remote_port = selected_remote_port

    def set_selected_ssm_mode(self, selected_ssm_mode: str):
        self.__selected_ssm_mode = selected_ssm_mode

    def get_settings(self):
        return self.__settings

    def get_selected_profile_name(self) -> Profile:
        return self.__selected_profile_name

    def get_selected_region_name(self) -> str:
        return self.__selected_region_name

    def get_selected_instance_filter_name(self) -> InstanceFilter:
        return self.__selected_instance_filter_name

    def get_selected_instance_id(self) -> str:
        return self.__selected_instance_id

    def get_selected_local_port(self) -> str:
        return self.__selected_local_port

    def get_selected_remote_port(self) -> str:
        return self.__selected_remote_port

    def get_selected_ssm_mode(self) -> str:
        return self.__selected_ssm_mode
