"""
settings.py

Contains Settings class used to model the contents of a settings.yaml file
"""

import os
import re
import logging
from dateutil.parser import parse
from typing import List, Any
import yaml
from aws_model import InstanceFilter
from constants import DEFAULT_ALL_FILTER
import traceback


SSM_CONNECTION_MODE_TERMINAL: str = "terminal"
SSM_CONNECTION_MODE_PORT_FORWARDING: str = "port-forwarding"
DEFAULT_REGION: str


class Settings:
    """Object representation of the contents of the settings.yaml file"""

    __aws_credentials_filename: str
    __use_defaults_at_startup: bool
    __profile_regex: List[str]
    __invalid_profile_regex: List[str]
    __valid_profile_regex: List[str]
    __ssm_documents: dict[str, str]
    __ssm_reason_text: str
    __default_region: str
    __supported_regions: List[str]
    __include_all_instance_filter: bool
    __instance_filters: dict[str, InstanceFilter]
    __settings_filename: str
    __log_file_path: str
    __startup_complete: bool

    def __init__(self, settings_filename: str, read_settings_file=False):
        self.__aws_credentials_filename = ""
        self.__log_file_path = os.path.join(os.path.expanduser("~"))
        self.__profile_regex = ""
        self.__ssm_documents = {}
        self.ssm_reason_text = ""
        self.__default_region = ""
        self.__supported_regions = []
        self.__include_all_instance_filter = False
        self.__instance_filters = {}
        self.__invalid_profile_regex = []
        self.__valid_profile_regex = []
        self.__startup_complete = False
        self.__settings_filename = settings_filename
        if read_settings_file:
            self.read_settings_file()

    def read_settings_file(self):
        data = {}
        logging.getLogger().info(
            f"[ssm-session-helper] Loaded settings from {self.__settings_filename}"
        )
        with open(self.__settings_filename, "r") as file:
            data: dict[str, Any] = yaml.safe_load(file)

        self.__aws_credentials_filename = data.get("aws-credentials-file", None)
        self.__log_file_path = data.get("log-file-path")
        self.__use_defaults_at_startup = data.get("use-defaults-at-startup", False)
        self.__profile_regex = data.get("profile-regex-matches", [""])
        self.__validate_profile_regex_list()

        raw_ssm_documents: dict[str, Any] = data.get("ssm-documents", {})
        self.__ssm_documents[SSM_CONNECTION_MODE_PORT_FORWARDING] = (
            raw_ssm_documents.get(
                SSM_CONNECTION_MODE_PORT_FORWARDING, "AWS-StartPortForwardingSession"
            )
        )
        self.__ssm_documents[SSM_CONNECTION_MODE_TERMINAL] = raw_ssm_documents.get(
            SSM_CONNECTION_MODE_TERMINAL, ""
        )

        self.ssm_reason_text = data.get(
            "ssm-reason-text", "Session started by ssmhelper"
        )
        self.__default_region = data.get("default-region", "us-west-2")

        global DEFAULT_REGION
        DEFAULT_REGION = self.__default_region

        self.__supported_regions = data.get("supported-regions", ["us-west-2"])

        self.__include_all_instance_filter = data.get(
            "instance-filter-include-all-instance-option", False
        )

        raw_instance_filters: List[dict[str, Any]] = data.get("instance-filters", [])

        for i in raw_instance_filters:
            if len(raw_instance_filters) == 1:
                this_is_default = True
            else:
                this_is_default = i.get("default", False)

            filter = i.get("filter", [[]])
            excludes = i.get("exclude", [])
            self.__instance_filters.update(
                {
                    i.get("filter-name"): InstanceFilter(
                        filter_name=i.get("filter-name"),
                        filter_value=filter,
                        exclude_regex=excludes,
                        default=this_is_default,
                    )
                }
            )

        if (
            self.__include_all_instance_filter
            or len(self.__instance_filters.values()) == 0
        ):
            self.__instance_filters[DEFAULT_ALL_FILTER.get_filter_name()] = (
                DEFAULT_ALL_FILTER
            )

    def get_default_instance_filter(self) -> InstanceFilter:
        return [i for i in list(self.__instance_filters.values()) if i.is_default()][0]

    def is_use_defaults_at_startup(self) -> bool:
        return self.__use_defaults_at_startup

    def get_settings_filename(self) -> str:
        return self.__settings_filename

    def get_aws_credentials_filename(self) -> str:
        return self.__aws_credentials_filename

    def get_log_file_path(self) -> str:
        return self.__log_file_path

    def get_profile_regex_strings(self) -> List[str]:
        return self.__profile_regex

    def get_ssm_document(self, connection_mode: str) -> str:
        return self.__ssm_documents[connection_mode]

    def get_ssm_reason_text(self) -> str:
        return self.ssm_reason_text

    def get_default_region_name(self) -> str:
        return self.__default_region

    def get_supported_regions(self) -> List[str]:
        return self.__supported_regions

    def is_all_instance_filter_included(self) -> bool:
        return self.__include_all_instance_filter

    def get_instance_filters(self, sort_ascending=False) -> List[InstanceFilter]:
        if sort_ascending:
            return sorted(
                list(self.__instance_filters.values()),
                key=lambda x: x.get_filter_name(),
            )
        else:
            return list(self.__instance_filters.values())

    def get_instance_filter(self, filter_name: str) -> InstanceFilter:
        return self.__instance_filters[filter_name]

    def is_profile_regex_list_valid(self) -> bool:
        return len(self.__invalid_profile_regex) > 0

    def __validate_profile_regex_list(self) -> dict[str, bool]:
        result: dict[str, bool] = {}

        for regex_string in self.__profile_regex:
            try:
                re.compile(regex_string)
                result[regex_string] = True
                self.__valid_profile_regex.append(regex_string)

            except Exception as e:
                logging.getLogger().error(f"[ssm-session-helper] Exception: {e}")
                logging.getLogger().error(traceback.format_exc())
                result[regex_string] = False
                self.__invalid_profile_regex.append(regex_string)

        return result

    def is_startup_complete(self):
        return self.__startup_complete

    def set_startup_complete(self):
        self.__startup_complete = True

    def get_invalid_profile_regex_stings(self) -> List[str]:
        return self.__invalid_profile_regex

    def get_valid_profile_regex_strings(self) -> List[str]:
        return self.__valid_profile_regex

    def set_profile_regex_to_show_all(self):
        self.__profile_regex = ["*"]
        self.__validate_profile_regex_list()
