#!/usr/bin/env python

import obfuscator
import argparse
import os
import asyncio
from dateutil.parser import parse
from typing import Dict, List, Tuple, Any
import threading
import botocore
import time
import logging
import traceback
from functools import partial
from session import SessionState, SSM_MODE_IN_TERMINAL
from datetime import datetime, timezone
from prompt_toolkit_extended.custom_dialogs import (
    ssm_port_selector_dialog,
    ssm_session_type_selector_dialog,
)
from prompt_toolkit.shortcuts import (
    radiolist_dialog,
    progress_dialog,
    message_dialog,
    button_dialog,
)

import worker
from aws_model import (
    InstanceFilter,
    Profile,
    Region,
    Profile,
    ProfileCollection,
)
from session import SessionState
from settings import Settings
import constants as const


class TaskResult:
    result_string: str
    result_value: Any
    result_error: Any

    def __init__(
        self, result_string: str, result_value: Any = None, result_error: Any = None
    ):
        self.result_string = result_string
        self.result_value = result_value
        self.result_error = result_error


class DialogResult(TaskResult):

    def __init__(
        self, result_string: str, result_value: Any = None, result_error: Any = None
    ):
        super().__init__(
            result_string=result_string,
            result_value=result_value,
            result_error=result_error,
        )


class Configurator:

    __session_state: SessionState
    __settings: Settings
    __profile_collection: ProfileCollection

    __settings_filename: str
    __credentials_filename: str

    __read_instances_process_complete: bool

    __loglevel: str
    __persist_logfile: bool

    def __init__(
        self,
        settings_file: str,
        aws_profile_credentials_filename: str,
        loglevel: str,
        persist_logfile: bool,
    ):
        self.__settings_filename = settings_file
        self.__credentials_filename = aws_profile_credentials_filename
        self.__current_state = const.STATE_READ_SETTINGS_FILE
        self.__previous_state = const.STATE_READ_SETTINGS_FILE
        self.__read_instances_process_complete = False
        self.__loglevel = loglevel
        self.__persist_logfile = persist_logfile

    def __get_loglevel(self) -> int:
        return const.LOGGING_VALUE_MAP.get(self.__loglevel.upper(), logging.WARN)

    def set_next_state(self, next_state=float):
        logging.getLogger().debug(
            f"[ssm-session-helper] Setting next state to {next_state} (current state: {self.__current_state})"
        )
        self.__previous_state = self.__current_state
        self.__current_state = next_state

    def run(self):
        """The state machine loop for the application"""
        try:
            while self.__current_state != const.STATE_GRACEFUL_EXIT:
                logging.getLogger().debug(f"CURRENT STATE {self.__current_state}")

                if self.__current_state is const.STATE_GRACEFUL_EXIT:
                    exit()

                elif self.__current_state is const.STATE_READ_SETTINGS_FILE:
                    self.__settings = self.read_settings_file(self.__settings_filename)
                    if not os.path.exists(self.__settings.get_log_file_path()):
                        os.makedirs(self.__settings.get_log_file_path())

                    # Timestamped logs
                    if self.__persist_logfile:
                        log_filename = f"{self.__settings.get_log_file_path()}/{datetime.now().strftime('%Y%m%d%H%M%S')}.log"
                    # Latest run log
                    else:
                        log_filename = (
                            f"{self.__settings.get_log_file_path()}/latest.log"
                        )

                    with open(log_filename, "a"):
                        pass

                    logging.basicConfig(
                        filename=log_filename,
                        filemode="w",
                        level=self.__get_loglevel(),
                        format="%(asctime)s - %(levelname)s - %(message)s",
                    )
                    self.set_next_state(const.STATE_VALIDATE_SETTINGS)

                elif self.__current_state is const.STATE_VALIDATE_SETTINGS:
                    self.validate_settings(self.__settings)
                    self.set_next_state(const.STATE_READ_PROFILES_FILE)

                elif self.__current_state is const.STATE_READ_PROFILES_FILE:
                    self.__profile_collection = self.read_profiles_file(
                        profile_filename=self.__credentials_filename,
                        settings=self.__settings,
                    )

                    if len(self.__profile_collection.get_profiles()) == 0:
                        self.set_next_state(const.STATE_SHOW_NO_PROFILES_FOUND)
                    else:
                        self.set_next_state(const.STATE_VALIDATE_PROFILE_CONNECTIVITY)

                elif self.__current_state is const.STATE_SHOW_NO_PROFILES_FOUND:
                    result = self.show_no_profiles_found(
                        self.__settings.get_profile_regex_strings(),
                        credentials_filename=self.__credentials_filename,
                        settings_filename=self.__settings_filename,
                    )
                    if result is const.DIALOG_QUIT:
                        self.set_next_state(const.STATE_GRACEFUL_EXIT)

                elif self.__current_state is const.STATE_VALIDATE_PROFILE_CONNECTIVITY:
                    asyncio.run(
                        self.validate_profile_connectivity(
                            profile_collection=self.__profile_collection
                        )
                    )
                    self.set_next_state(const.STATE_INITIALIZE_SESSION_OBJECT)

                elif self.__current_state is const.STATE_INITIALIZE_SESSION_OBJECT:
                    self.__session_state = self.initialize_session_object(
                        self.__settings, self.__profile_collection
                    )
                    self.set_next_state(const.STATE_SHOW_PROFILE_SELECTOR)

                elif self.__current_state is const.STATE_SHOW_PROFILE_SELECTOR:
                    if self.__previous_state is const.STATE_SHOW_CONFIGURATOR:
                        dialog_result: DialogResult = self.show_profile_selector(
                            back_button_label=const.DIALOG_BACK
                        )
                    else:
                        dialog_result: DialogResult = self.show_profile_selector(
                            back_button_label=const.DIALOG_QUIT
                        )

                    if (
                        dialog_result.result_string is const.DIALOG_BACK
                        or dialog_result.result_string is const.DIALOG_QUIT
                    ):
                        if self.__previous_state is not const.STATE_SHOW_CONFIGURATOR:
                            self.set_next_state(const.STATE_GRACEFUL_EXIT)
                        else:
                            # Don't save the selection, just go back
                            self.set_next_state(self.__previous_state)

                    elif dialog_result.result_string is const.DIALOG_NON_ACTIVE_PROFILE:
                        self.save_profile(dialog_result.result_value)
                    else:
                        self.save_profile(dialog_result.result_value)

                        if (
                            self.__settings.is_use_defaults_at_startup()
                            and not self.__settings.is_startup_complete()
                        ):
                            self.save_region(self.__settings.get_default_region_name())
                            self.save_instance_filter(
                                self.__settings.get_default_instance_filter().get_filter_name()
                            )
                            self.set_next_state(const.STATE_POPULATE_INSTANCE_RESULTS)
                        else:
                            self.set_next_state(const.STATE_POPULATE_INSTANCE_RESULTS)

                        if not self.__settings.is_startup_complete():
                            self.__settings.set_startup_complete()

                elif self.__current_state is const.STATE_SHOW_REGION_SELECTOR:
                    result = self.show_region_selector()
                    result.result_string
                    result.result_value

                    if result.result_string is const.DIALOG_BACK:
                        self.set_next_state(self.__previous_state)
                    else:
                        self.save_region(result.result_value)

                        # If this is in the initialization flow, the previous state will be account selection
                        if self.__previous_state is const.STATE_SHOW_PROFILE_SELECTOR:
                            self.set_next_state(
                                const.STATE_SHOW_INSTANCE_FILTER_SELECTOR
                            )
                        else:
                            # If the region is already cached, proceed, otherwise load the instance results
                            selected_profile = (
                                self.__profile_collection.get_selected_profile()
                            )

                            if selected_profile.is_region_cached(result.result_value):
                                selected_region = selected_profile.get_region(
                                    result.result_value
                                )
                                if selected_region.is_instance_result_cached(
                                    self.get_selected_instance_filter_name()
                                ):
                                    self.set_next_state(self.__previous_state)
                                else:
                                    self.set_next_state(
                                        const.STATE_POPULATE_INSTANCE_RESULTS
                                    )
                            else:
                                self.set_next_state(
                                    const.STATE_POPULATE_INSTANCE_RESULTS
                                )

                elif self.__current_state is const.STATE_SHOW_INSTANCE_FILTER_SELECTOR:
                    result = self.show_instance_filter_selector()
                    result.result_string
                    result.result_value

                    if result.result_string is const.DIALOG_BACK:
                        self.set_next_state(self.__previous_state)
                    else:
                        self.save_instance_filter(result.result_value)
                        self.set_next_state(const.STATE_POPULATE_INSTANCE_RESULTS)

                elif self.__current_state is const.STATE_POPULATE_INSTANCE_RESULTS:
                    result: TaskResult = self.populate_instance_results(
                        settings=self.__settings,
                        profile_collection=self.__profile_collection,
                        session_state=self.__session_state,
                        instance_filter=self.get_selected_instance_filter(),
                    )

                    logging.getLogger().info(
                        f"[ssm-session-helper] populate_instance_results = {str(result.result_string)}"
                    )
                    if result.result_string is const.TASK_SUCCESS:
                        self.set_next_state(const.STATE_SHOW_CONFIGURATOR)
                    else:
                        self.set_next_state(const.STATE_GRACEFUL_EXIT)

                elif self.__current_state is const.STATE_SHOW_CONFIGURATOR:
                    profile_name = self.__session_state.get_selected_profile_name()
                    region_name = self.__session_state.get_selected_region_name()
                    selected_instance_id = (
                        self.__session_state.get_selected_instance_id()
                    )

                    selected_filter = self.get_selected_instance_filter_name()
                    selected_profile = self.__profile_collection.get_profile(
                        profile_name=profile_name
                    )

                    if not selected_profile.is_region_cached(region_name=region_name):
                        region = Region(
                            profile_name=selected_profile.get_profile_name(),
                            region_name=region_name,
                            default_instance_filter=self.__settings.get_default_instance_filter(),
                            create_boto3_session=True,
                        )
                        selected_profile.add_or_update_region(region)

                    instance_result = (
                        self.__profile_collection.get_profile(profile_name=profile_name)
                        .get_region(region_name=region_name)
                        .get_instance_result(selected_filter)
                    )

                    local_port = self.__session_state.get_selected_local_port()
                    remote_port = self.__session_state.get_selected_remote_port()

                    profiles = self.__profile_collection.get_profiles(sorted=True)
                    profile_values = [
                        (i.get_profile_name(), i.get_profile_name()) for i in profiles
                    ]
                    
                    filter_values = [
                        (i.get_filter_name(), i.get_filter_name())
                        for i in self.__settings.get_instance_filters(
                            sort_ascending=True
                        )
                    ]
                    region_values = [
                        (i, i) for i in self.__settings.get_supported_regions()
                    ]
                    instance_values = [
                        (
                            i.get_instance_id(),
                            f"{i.get_instance_id()}: {i.get_instance_name()}",
                        )
                        for i in instance_result.get_instances(sort_ascending=True)
                    ]

                    selection = ssm_session_type_selector_dialog(
                        instance_id=selected_instance_id,
                        local_port=local_port,
                        remote_port=remote_port,
                        profile_values=profile_values,
                        selected_profile=profile_name,
                        filter_values=filter_values,
                        selected_filter=self.__session_state.get_selected_instance_filter_name(),
                        region_values=region_values,
                        selected_region=self.__session_state.get_selected_region_name(),
                        instance_values=instance_values,
                        selected_ssm_mode=self.__session_state.get_selected_ssm_mode(),
                        yes_text=const.DIALOG_SELECT,
                        no_text=const.DIALOG_QUIT,
                    ).run()

                    result = selection["result"]
                    if result is const.DIALOG_PROFILE:
                        self.set_next_state(const.STATE_SHOW_PROFILE_SELECTOR)
                    elif result is const.DIALOG_REGION:
                        self.set_next_state(const.STATE_SHOW_REGION_SELECTOR)
                    elif result is const.DIALOG_FILTER:
                        self.set_next_state(const.STATE_SHOW_INSTANCE_FILTER_SELECTOR)
                    elif result is const.DIALOG_INSTANCE:
                        if not (selection["result_value"] == 0):
                            self.set_next_state(const.STATE_SHOW_INSTANCE_SELECTOR)
                    elif result is const.DIALOG_QUIT:
                        self.set_next_state(const.STATE_GRACEFUL_EXIT)
                    elif result is const.DIALOG_CONNECT:
                        self.__session_state.set_selected_ssm_mode(selection["mode"])
                        if selection["mode"] == const.SSM_MODE_IN_TERMINAL:
                            logging.getLogger().info(
                                "[ssm-session-helper] selected ssm session in terminal"
                            )
                            self.__session_state.log_current_selected_values()
                            worker.start_ssm_terminal_sesion(
                                self.__session_state,
                                self.__settings,
                                in_new_window=True,
                            )
                        else:
                            logging.getLogger().info(
                                "[ssm-session-helper] selected ssm session in port forwarding mode"
                            )
                            self.set_next_state(const.STATE_SHOW_PORT_SELECTOR)

                elif self.__current_state is const.STATE_SHOW_INSTANCE_SELECTOR:
                    dialog_result = self.show_instance_selector(
                        settings=self.__settings,
                        profile_collection=self.__profile_collection,
                        session_state=self.__session_state,
                    )
                    if dialog_result.result_string is const.DIALOG_SELECT:
                        self.save_instance(dialog_result.result_value)
                        self.set_next_state(const.STATE_SHOW_CONFIGURATOR)
                    else:
                        self.set_next_state(self.__previous_state)

                elif self.__current_state is const.STATE_SHOW_PORT_SELECTOR:
                    original_local_port = self.__session_state.get_selected_local_port()
                    original_remote_port = (
                        self.__session_state.get_selected_remote_port()
                    )

                    dialog_result = self.show_port_selector(
                        profiles=self.__profile_collection,
                        session_state=self.__session_state,
                    )
                    if dialog_result["result"] is const.DIALOG_CONNECT:

                        self.__session_state.set_selected_local_port(
                            dialog_result["value"]["local-port"]
                        )
                        self.__session_state.set_selected_remote_port(
                            dialog_result["value"]["remote-port"]
                        )
                        self.__session_state.log_current_selected_values()

                        if not worker.is_port_in_use(
                            dialog_result["value"]["local-port"]
                        ):
                            self.__session_state.set_selected_local_port(
                                dialog_result["value"]["local-port"]
                            )
                            self.__session_state.set_selected_remote_port(
                                dialog_result["value"]["remote-port"]
                            )

                            worker.start_ssm_port_forwarding_sesion(
                                session_state=self.__session_state,
                                settings=self.__settings,
                                in_new_window=True,
                            )
                            self.set_next_state(self.__previous_state)
                        else:
                            logging.getLogger().warning(
                                f"[ssm-session-helper] Port {dialog_result['value']['local-port']} is already in use"
                            )
                            message_dialog(
                                title="Port already in use",
                                text=f"Port {dialog_result['value']['local-port']} is already in use on your machine.\n\nPlease specify a different local port.",
                                ok_text="Back...",
                            ).run()
                    else:
                        self.set_next_state(self.__previous_state)
                        self.__session_state.set_selected_local_port(
                            original_local_port
                        )
                        self.__session_state.set_selected_remote_port(
                            original_remote_port
                        )

        except Exception as e:
            logging.getLogger().error(f"[ssm-session-helper] Exception: {e}")
            logging.getLogger().error(traceback.format_exc())
            raise e

    def read_settings_file(self, settings_filename: str) -> Settings:
        """Read the settings file and return a Settings object

        Args:
            settings_filename (str): The path to the settings file

        Returns:
            Settings: The settings
        """

        settings = Settings(
            settings_filename=settings_filename, read_settings_file=True
        )
        return settings

    def validate_settings(self, settings: Settings):
        """Validate the settings object contents

        Args:
            settings (Settings): the settings object to validate
        """
        pass

    def read_profiles_file(
        self, profile_filename: str, settings: Settings
    ) -> ProfileCollection:
        """Read the profiles file and return a ProfileCollection object

        Args:
            profile_filename (str): The path to the aws credentials profiles file

        Returns:
            ProfileCollection: A representation of the profiles in the file
        """

        profile_collection = ProfileCollection(
            credentials_filename=profile_filename,
            supported_regions=settings.get_supported_regions(),
            default_region_name=settings.get_default_region_name(),
            default_instance_filter=settings.get_default_instance_filter(),
            profile_regex_strings=settings.get_profile_regex_strings(),
        )

        return profile_collection

    async def validate_profile_connectivity(
        self, profile_collection: ProfileCollection
    ) -> dict[str, bool]:
        """Validates each profile in the ProfileCollection to see if it can connect to AWS and if DescribeInstances works

        Args:
            profile_collection (ProfileCollection): The aws profiles that are options to connect to

        Returns:
            dict[str, bool]: A dictionary of results { profile_name: true/false }
        """

        validate_profile_func = partial(
            self.__validate_profile_task, profile_collection=profile_collection
        )

        await progress_dialog(
            title="Validating AWS Profiles",
            text=f"\nTesting ability to call EC2 DescribeInstances...",
            run_callback=self.__validate_profile_task,
        ).run_async()

    def __validate_profile_task(self, set_percentage=None, log_text=None):
        set_percentage(str(0))

        profiles = self.__profile_collection.get_profiles()

        profile_count = len(profiles)
        increment = 100.0 / float(profile_count)
        logging.getLogger().info(
            f"[ssm-session-helper] All profiles: {[i.get_profile_name() for i in profiles]}"
        )
        count = 1.0
        for profile in profiles:
            logging.getLogger().debug(
                f"[ssm-session-helper] validating profile {profile.get_profile_name()}"
            )

            set_percentage(int(float(count) / float(profile_count)))
            profile.test_call_describe_instances()

            result = "OK" if profile.is_describe_instances_working() else "Failed"
            message = f"[{result}]: {profile.get_profile_name()}\n"

            if log_text is not None:
                log_text(message)
            if set_percentage is not None:
                set_percentage(int(float(count) / float(profile_count)))

            count += 1

        if set_percentage is not None:
            set_percentage(str(100))

    async def __load_instances(
        self, profile_name, region_name, instance_filter, show_dialog=True
    ) -> TaskResult:

        partial_func = partial(
            self.__load_instances_fetcher_task,
            profile_name=profile_name,
            region_name=region_name,
            instance_filter_name=instance_filter,
        )
        try:
            t1 = threading.Thread(target=partial_func)
            t1.daemon = True
            t1.start()

            if show_dialog:
                await progress_dialog(
                    title="Retrieving Instances",
                    text="Retrieving instances from "
                    + profile_name
                    + " ("
                    + region_name
                    + ")",
                    run_callback=self.__load_instances_poller_task,
                ).run_async()

            return TaskResult(result_string=const.TASK_SUCCESS, result_value=None)
            # return ProcessResult()
        except botocore.exceptions.ClientError as e:
            logging.getLogger().error(f"[ssm-session-helper] Exception: {e}")
            logging.getLogger().error(traceback.format_exc())
            if "RequestExpired" in e.message:
                if show_dialog:
                    message_dialog(
                        title="Session Timed Out",
                        text="No instances found in "
                        + self.ssm_connection_details.profile
                        + ", "
                        + self.ssm_connection_details.region_name
                        + ".\n\nPlease select another region or account.",
                        ok_text="Back...",
                    ).run()
            else:
                if show_dialog:
                    message_dialog(
                        title="Unexpected Error",
                        text="Message: " + e.message,
                        ok_text="Back...",
                    ).run()
            return TaskResult(result_string=const.TASK_SUCCESS, result_value=e)

    def __load_instances_fetcher_task(
        self, profile_name: str, region_name: str, instance_filter_name: str
    ) -> TaskResult:
        try:
            self.__read_instances_process_complete = False

            profile = self.__profile_collection.get_profile(profile_name=profile_name)
            region = profile.get_region(region_name)
            instance_filter = self.__settings.get_instance_filter(instance_filter_name)

            if not region.is_boto3_session_created():
                region.create_boto3_session()

            instance_result = region.load_instances_from_boto(
                instance_filter=instance_filter
            )

            if region.has_boto_error():
                error = region.get_boto_error()
                logging.getLogger().error(f"[ssm-session-helper] Exception: {e}")
                logging.getLogger().error(traceback.format_exc())

            self.__session_state.set_selected_instance_id(
                instance_result.get_selected_instance_id()
            )

            self.__read_instances_process_complete = True

            return TaskResult(
                result_string=const.TASK_SUCCESS, result_value=instance_result
            )

        except botocore.exceptions.ClientError as e:
            logging.getLogger().error(f"[ssm-session-helper] Exception: {e}")
            logging.getLogger().error(traceback.format_exc())
            self.__read_instances_process_complete = True
            return TaskResult(result_string=const.TASK_ERROR, result_value=e)

    def __load_instances_poller_task(self, set_percentage, log_text):
        percentage = 0
        set_percentage(0)
        for f in range(0, 100):
            time.sleep(0.1)
            percentage += 1

            log_text("Retrieving EC2 Instances...\n")

            if percentage == 98 and not self.__read_instances_process_complete:
                set_percentage(98)
            else:
                set_percentage(percentage)
            if self.__read_instances_process_complete:
                set_percentage(99)
                break

        # Show 100% for a second, before quitting.
        set_percentage(100)
        time.sleep(0.1)

    def initialize_session_object(
        self, settings: Settings, profile_colelction: ProfileCollection
    ) -> SessionState:
        """Creates a session object

        Args:
            settings (Settings): The Settings object as read from the settings.yaml
            profile_colelction (ProfileCollection): Collection of profiles

        Returns:
            SessionState: Session State object
        """
        session = SessionState(settings=settings, profile_collection=profile_colelction)

        return session

    def show_profile_selector(
        self, back_button_label: str = const.DIALOG_QUIT
    ) -> DialogResult:
        """Show the profile selector dialog.

        Returns:
            DialogResult: The result.   DialogResult.result_string[const.DIALOG_SELECT, const.DIALOG_CANCEL]
                                        DialogResult.result_value[str] - the selected profile
        """
        active_profile_menu_items = [
            (i.get_profile_name(), f"[ * Active * ] {i.get_profile_name()}")
            for i in self.__profile_collection.get_active_profiles()
        ]
        expired_profile_menu_items = [
            (i.get_profile_name(), f"[ - Expired - ] {i.get_profile_name()}")
            for i in self.__profile_collection.get_expired_profiles()
        ]
        errored_profile_menu_items = [
            (i.get_profile_name(), f"[ ! Error ! ] {i.get_profile_name()}")
            for i in self.__profile_collection.get_errored_profiles()
        ]

        profile_menu_items = (
            active_profile_menu_items
            + expired_profile_menu_items
            + errored_profile_menu_items
        )

        if self.__session_state.get_selected_profile_name() == "":
            if len(active_profile_menu_items) > 0:
                self.save_profile(active_profile_menu_items[0][0])

            elif len(expired_profile_menu_items) > 0:
                self.save_profile(expired_profile_menu_items[0][0])

        dialog_selected_profile = radiolist_dialog(
            title="AWS Profile Selector",
            text="Select an AWS Profile (expired sessions at the bottom of the list):",
            values=profile_menu_items,
            default=self.__session_state.get_selected_profile_name(),
            cancel_text=back_button_label,
            ok_text=const.DIALOG_SELECT,
        ).run()

        if dialog_selected_profile is None:
            return DialogResult(back_button_label, None)
        else:
            if dialog_selected_profile in [
                i.get_profile_name()
                for i in self.__profile_collection.get_active_profiles()
            ]:
                return DialogResult(const.DIALOG_SELECT, dialog_selected_profile)
            else:
                return DialogResult(
                    const.DIALOG_NON_ACTIVE_PROFILE, dialog_selected_profile
                )

    def save_profile(self, selected_profile_name: str):
        """Saves the selected profile to current state"""
        logging.getLogger().debug(
            f"[ssm-session-helper::save_profile] user selected profile name: {selected_profile_name}"
        )
        self.__session_state.set_selected_profile_name(selected_profile_name)
        self.__profile_collection.set_selected_profile_name(selected_profile_name)

    def show_region_selector(self) -> DialogResult:
        """Show the region selector dialog

        Returns:
            DialogResult:  The result.  DialogResult.result_string[const.DIALOG_SELECT, const.DIALOG_CANCEL]
                                        DialogResult.result_value[str] - the selected region
        """
        region_items = [
            (i, i) for i in self.__profile_collection.get_supported_regions()
        ]

        result = radiolist_dialog(
            title="Region Selector",
            text="Account: "
            + self.__session_state.get_selected_profile_name()
            + "\n\nSelect a region:",
            values=region_items,
            default=self.__session_state.get_selected_region_name(),
            ok_text=const.DIALOG_SELECT,
            cancel_text=const.DIALOG_BACK,
        ).run()

        if result is None:
            return DialogResult(result_string=const.DIALOG_BACK, result_value=None)
        else:
            return DialogResult(result_string=const.DIALOG_CONFIRM, result_value=result)

    def save_region(self, selected_region_name: str):
        """Save the selected region

        Args:
            selected_region_name (str): _description_
        """
        logging.getLogger().info(
            f"[ssm-session-helper::save_region] user selected region: {selected_region_name}"
        )
        self.__session_state.set_selected_region(selected_region_name)

    def show_instance_filter_selector(self) -> DialogResult:
        """Show the instance filter selector

        Returns:
            DialogResult: The result.  DialogResult.result_string[const.DIALOG_SELECT, const.DIALOG_CANCEL]
                                       DialogResult.result_value[str] - the selected instance filter
        """
        sorted_filter_names = self.__settings.get_instance_filters(sort_ascending=True)
        filter_items = [
            (i.get_filter_name(), i.get_filter_name()) for i in sorted_filter_names
        ]

        result = radiolist_dialog(
            title="Instance Filter Selector",
            text="Account: "
            + self.__session_state.get_selected_profile_name()
            + "\n\nSelect a filter:",
            values=filter_items,
            default=self.__session_state.get_selected_instance_filter_name(),
            cancel_text=const.DIALOG_BACK,
            ok_text=const.DIALOG_SELECT,
        ).run()

        if result is None:
            return DialogResult(const.DIALOG_BACK, None)
        else:
            return DialogResult(const.DIALOG_SELECT, result)

    def get_selected_instance_filter_name(self):
        """Get the selected instance filter

        Args:
            instance_filter_name (str): The name of the instance filter to save
        """
        return self.__session_state.get_selected_instance_filter_name()

    def get_selected_instance_filter(self):
        """Get the selected instance filter

        Args:
            instance_filter_name (str): The name of the instance filter to save
        """
        filter_name = self.__session_state.get_selected_instance_filter_name()
        return self.__settings.get_instance_filter(filter_name)

    def save_instance_filter(self, instance_filter_name: str):
        """Save the selected instance filter

        Args:
            instance_filter_name (str): The name of the instance filter to save
        """
        logging.getLogger().debug(
            f"[ssm-session-helper::save_instance_filter] user selected filter name: {instance_filter_name}"
        )
        self.__session_state.set_selected_instance_filter_name(instance_filter_name)

    def show_port_occupied_error(self, port_number: str):
        """Shows the port occupied error

        Args:
            port_number (str): Port number
        """
        pass

    def populate_instance_results(
        self,
        settings: Settings,
        profile_collection: ProfileCollection,
        session_state: SessionState,
        instance_filter: InstanceFilter,
    ) -> TaskResult:
        """Creates an EC2InstanceResult object based on the current seleection

        Args:
            settings (Settings): _description_
            profiles (ProfileCollection): _description_

        Returns:
            EC2InstanceResult: The instances in the Profile/Region/Instance Filter combination
        """
        profile_name = session_state.get_selected_profile_name()
        region_name = session_state.get_selected_region_name()
        instance_filter_name = instance_filter.get_filter_name()

        profile: Profile = profile_collection.get_profile(profile_name)
        logging.getLogger().debug(
            f"[ssm-session-helper::populate_instance_results] is_region_cached for region({region_name}) : {profile.is_region_cached(region_name)}"
        )

        if not profile.is_region_cached(region_name):
            profile.add_or_update_region(
                Region(
                    profile.get_profile_name(),
                    region_name=region_name,
                    default_instance_filter=instance_filter,
                    create_boto3_session=False,
                )
            )

        region = profile.get_region(region_name)

        logging.getLogger().debug(
            f"[ssm-session-helper::populate_instance_results] is_instance_result_cached for filter({instance_filter_name}) : {region.is_instance_result_cached(instance_filter_name)}"
        )
        if not region.is_instance_result_cached(instance_filter_name):
            result: TaskResult = asyncio.run(
                self.__load_instances(profile_name, region_name, instance_filter_name)
            )

            return result

        else:

            return TaskResult(result_string=const.TASK_SUCCESS, result_value=None)

    def show_instance_selector(
        self,
        settings: Settings,
        profile_collection: ProfileCollection,
        session_state: SessionState,
    ) -> DialogResult:
        """Allows user to select the instance to connect to

        Args:
            settings (Settings): Settings
            profiles (ProfileCollection): Collection of Profiles
            session_state (SessionState): The app session data

        Returns:
            DialogResult: The result.  DialogResult.result_string[const.DIALOG_SELECT, const.DIALOG_CANCEL]
                                       DialogResult.result_value[str] - the selected instance
        """
        region_name = session_state.get_selected_region_name()
        selected_instance_id = session_state.get_selected_instance_id()
        profile_name = session_state.get_selected_profile_name()
        instance_filter_name = session_state.get_selected_instance_filter_name()

        region = profile_collection.get_profile(profile_name=profile_name).get_region(
            region_name=region_name
        )

        if region is not None:
            instance_result = region.get_instance_result(instance_filter_name)
            sorted_instances = sorted(
                instance_result.get_instances(), key=lambda x: x.get_instance_name()
            )
            instance_menu_items = [
                (i.get_instance_id(), f"{i.get_instance_id()}: {i.get_instance_name()}")
                for i in sorted_instances
            ]

            selected_instance = radiolist_dialog(
                title="Instance Selector",
                text="Account: "
                + self.__session_state.get_selected_profile_name()
                + "\nRegion: "
                + self.__session_state.get_selected_region_name()
                + "\n\nSelect an EC2 instance to connect to:",
                values=instance_menu_items,
                default=self.__session_state.get_selected_instance_id(),
                ok_text=const.DIALOG_SELECT,
                cancel_text=const.DIALOG_CANCEL,
            ).run()

            if selected_instance is not None:
                return DialogResult(
                    result_string=const.DIALOG_SELECT, result_value=selected_instance
                )
            else:
                return DialogResult(result_string=const.DIALOG_CANCEL)

    def save_instance(self, instance_id: str):
        """Save the instance_id to session state

        Args:
            instance_id (str): the EC2 instance id
        """
        logging.getLogger().debug(
            f"[ssm-session-helper::save_instance] user selected instance id: {instance_id}"
        )
        self.__session_state.set_selected_instance_id(instance_id)

    def show_port_selector(
        self, profiles: ProfileCollection, session_state: SessionState
    ) -> DialogResult:
        """Allow the user to select remote and local port for port forwarding connections

        Args:
            profiles (ProfileCollection): Collection of AWS Profiles
            session_state (SessionState): Current session state

        Returns:
            DialogResult: The user selection
        """

        selected_instance_name = session_state.get_selected_instance_id()
        instance = (
            profiles.get_profile(session_state.get_selected_profile_name())
            .get_region(session_state.get_selected_region_name())
            .get_instance_result(session_state.get_selected_instance_filter_name())
            .get_instance(selected_instance_name)
        )

        result = ssm_port_selector_dialog(
            instance_name=instance.get_instance_name(),
            instance_id=session_state.get_selected_instance_id(),
            local_port=session_state.get_selected_local_port(),
            remote_port=session_state.get_selected_remote_port(),
            selected_profile=session_state.get_selected_profile_name(),
            selected_region=session_state.get_selected_region_name(),
        ).run()
        return result

    def show_configurator(
        self,
        settings: Settings,
        profiles: ProfileCollection,
        session_state: SessionState,
    ) -> DialogResult:
        """Allows users to select the profile, region, instance filter, instance,

        Args:
            settings (Settings): Settings
            profiles (ProfileCollection): Collection of Profiles
            session_state (SessionState): The app session data

        Returns:
            DialogResult:  DialogResult.result_string[const.DIALOG_SELECT, const.DIALOG_QUIT, const.DIALOG_INSTANCE_SELECT, const.DIALOG_REGION_SELECT, const.DIALOG_INSTANCE_FILTER_SELECT, const.DIALOG_INSTANCE_SELECT]
                           DialogResult.result_value[dict[str, Any]] - all values in the dialog
        """
        pass

    def show_no_profiles_found(
        self,
        profile_regex_strings: List[str],
        credentials_filename: str,
        settings_filename: str,
    ):
        """Show a dialog that no profiles were found in the credentials file

        Args:
            profile_regex_strings (List[str]): List of regex strings as defined in settings.yaml
            credentials_filename [str]: Filename of the credentials file with profiles
        """
        result = button_dialog(
            title="No AWS Profiles Found",
            text=f"""No AWS profiles were found in {credentials_filename} that matched the pattern(s) {str(profile_regex_strings)}.
        

Please check the contents of {credentials_filename}, 
    or specify another path for aws credentials with the --credentials argument, 
    or modify the value for 'profile-regex-matches' in the {settings_filename} file.

""",
            buttons=[(const.DIALOG_QUIT, const.DIALOG_QUIT)],
        ).run()

        return result

    def start_ssm_terminal_session(self, session_state: SessionState):
        """Start an AWS SSM session manager session in terminal

        Args:
            session_state (SessionState): Session settings
        """
        pass

    def validate_local_port_availability(self, port_number: str) -> bool:
        """Validate that the provided port number is available on the local machine

        Args:
            port_number (str): The port number to connect over
        """
        return worker.is_port_in_use(port_number)

    def start_ssm_port_forwarding_session(self, session_state: SessionState):
        """Start and AWS SSM session manager session in port forwarding mode

        Args:
            session_state (SessionState): Session settings
        """
        pass

    def show_error_message(self, message: str):
        """Show an error message

        Args:
            message (str): The message to show
        """
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="""Establishes an SSM Session

"""
    )
    default_settings_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "settings.yaml"
    )

    parser.add_argument(
        "-s", "--settings", required=False, type=str, default=default_settings_file
    )
    parser.add_argument(
        "-a",
        "--credentials_file",
        required=False,
        type=str,
        default="~/.aws/credentials",
    )
    parser.add_argument(
        "--loglevel",
        required=False,
        type=str,
        default="info",
        choices=["debug", "info", "error"],
        help="Log level [debug, info, error]",
    )
    parser.add_argument(
        "--persist_logfile",
        action="store_true",
        default=False,
        help="Persists the logfile with a timestamped name",
    )

    args = parser.parse_args()

    settings_file = worker.parse_filepath(args.settings)
    credentials_file = worker.parse_filepath(args.credentials_file)

    configurator = Configurator(
        settings_file=settings_file,
        aws_profile_credentials_filename=credentials_file,
        loglevel=args.loglevel,
        persist_logfile=args.persist_logfile,
    )

    configurator.run()
