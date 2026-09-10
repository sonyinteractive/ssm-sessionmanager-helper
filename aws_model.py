"""
aws_model.py

Contains classes that model AWS resources relevant to SSM

"""
import obfuscator
import boto3.exceptions
import boto3.session
from dateutil.parser import parse
from typing import List, Any
from functools import singledispatchmethod
import boto3
import logging
import datetime
from datetime import datetime, timezone
import re
import botocore
import json


class InstanceFilter:
    __filter_name: str
    __filter_value: dict[str, List[dict[str, str]]]
    __exclude_regex: List[str]
    __default: bool

    def __init__(
        self,
        filter_name: str,
        filter_value: dict[str, List[dict[str, str]]] = None,
        exclude_regex: List[str] = None,
        default: bool = False,
    ):
        self.set_filter(filter_name, filter_value, exclude_regex, default)

    def set_filter(
        self,
        filter_name: str,
        filter_value: dict[str, List[dict[str, str]]] = None,
        exclude_regex: List[str] = None,
        default: bool = False,
    ):
        self.set_filter_name(filter_name)
        self.set_filter_value(filter_value)
        self.set_exclude_regex(exclude_regex)
        self.set_default(default)

    def set_filter_name(self, filter_name: str):
        self.__filter_name = filter_name

    def set_filter_value(self, filter_value: dict[str, List[dict[str, str]]] = None):
        self.__filter_value = filter_value

    def set_exclude_regex(self, exclude_regex: List[str]):
        self.__exclude_regex = exclude_regex

    def set_default(self, default: bool):
        self.__default = default

    def get_filter_name(self) -> str:
        return self.__filter_name

    def get_filter_value(self) -> List[dict[str, Any]] | None:
        return self.__filter_value

    def get_exclude_regex(self) -> List[str] | None:
        return self.__exclude_regex

    def is_default(self) -> bool:
        return self.__default


class EC2Instance:
    __instance_data: dict[str, Any]
    __instance_id: str | None
    __instance_name: str

    def __init__(self, boto_response: dict[str, Any]):
        self.set_instance_data(boto_response)

    def set_instance_data(self, boto_instance_dict: dict[str, Any]):
        self.__instance_id = boto_instance_dict["InstanceId"]
        self.__instance_name = None
        self.__instance_data = boto_instance_dict

        tags: dict[str, str] = boto_instance_dict.get("Tags")
        logging.getLogger().debug(
            f"[ssm-session-helper] Instance ID: {self.__instance_id} tags"
        )
        for tag in tags:
            if tag.get("Key") == "Name":
                self.__instance_name = tag.get("Value")

        if self.__instance_name is None:
            self.__instance_name = boto_instance_dict["InstanceId"]

        logging.getLogger().debug(
            f"[ssm-session-helper] {self.__instance_id} = {self.__instance_name}"
        )

    def get_instance_data(self) -> dict[str, Any] | None:
        return self.__instance_data

    def get_instance_id(self) -> str:
        return self.__instance_id

    def get_instance_name(self) -> str | None:
        return self.__instance_name


class EC2InstanceResult:

    __instances: dict[str, EC2Instance]
    __instance_filter: InstanceFilter

    __selected_instance_id: str

    dummy_instance_filter = [{"Name": "tag:not-a-tag1321654", "Values": ["dud"]}]

    def __init__(
        self,
        instance_filter: InstanceFilter,
        instances: List[EC2Instance] | None = None,
    ):
        self.set_instances(instances)
        self.set_instance_filter(instance_filter)
        if len(instances) > 0:
            self.set_selected_instance_id(instances[0].get_instance_id())

    def set_instances(self, instances: List[EC2Instance]):
        self.__instances = {i.get_instance_id(): i for i in instances}
        if len(instances) > 0:
            self.__selected_instance_id = instances[0]

    def set_instance_filter(self, instance_filter: InstanceFilter):
        self.__instance_filter = instance_filter

    def set_selected_instance_id(self, instance_id: str):
        self.__selected_instance_id = instance_id

    def get_selected_instance_id(self) -> str:
        return self.__selected_instance_id

    def get_instances(self, sort_ascending=False) -> List[EC2Instance] | None:
        if self.__instances is None:
            return []
        elif sort_ascending:
            return sorted(
                list(self.__instances.values()), key=lambda x: x.get_instance_name()
            )
        else:
            return list(self.__instances.values())

    def get_instance(self, instance_id: str) -> EC2Instance:
        return self.__instances[instance_id]

    def get_instance_filter(self) -> InstanceFilter:
        return self.__instance_filter


class Region:
    __boto3_session: boto3.Session
    __ec2_client: Any
    __sts_client: Any
    __profile_name: str  # Needed for boto3 session
    __region_name: str
    __boto_error: Exception
    __instance_results: dict[str, EC2InstanceResult]
    __describe_instances_works: bool
    __describe_instances_tested: bool
    __running_instance_filter: dict[str, Any] = {
        "Name": "instance-state-name",
        "Values": ["running"],
    }

    def __init__(
        self,
        profile_name: str,
        region_name: str,
        default_instance_filter: str,
        create_boto3_session: bool = False,
    ):
        self.__instance_results = {}
        self.__region_name = region_name
        self.__profile_name = profile_name
        self.__boto_error = None
        self.__describe_instances_works = False
        self.__boto3_session = None
        self.__describe_instances_tested = False
        if create_boto3_session:
            self.create_boto3_session()

    def is_boto3_session_created(self):
        return self.__boto3_session is not None

    def create_boto3_session(self):
        self.__boto3_session = boto3.Session(
            profile_name=self.__profile_name, region_name=self.__region_name
        )
        self.__ec2_client = self.__boto3_session.client(
            "ec2", region_name=self.__region_name
        )
        self.__sts_client = self.__boto3_session.client(
            "sts", region_name=self.__region_name
        )

    def is_describe_instances_working(self):
        if not self.__describe_instances_tested:
            self.__describe_instances_works = self.test_call_describe_instances()
        return self.__describe_instances_works

    def test_call_describe_instances(self) -> bool:

        try:
            if self.__boto3_session is None:
                self.create_boto3_session()

            logging.getLogger().debug(
                f"[ssm-session-helper] test_call_describe_instances called on profile {self.__profile_name} in region {self.__region_name}"
            )
            self.__describe_instances_tested = True
            self.__ec2_client.describe_instances(DryRun=True)
            self.__describe_instances_works = True
            logging.getLogger().debug(
                f"[ssm-session-helper] test_call_describe_instances called on profile {self.__profile_name} in region {self.__region_name} succeeded"
            )
        except Exception as e:
            if "Request would have succeeded, but DryRun flag is set." in str(e):
                self.__describe_instances_works = True
            else:
                logging.getLogger().error(
                    f"[ssm-session-helper] Token for profile '{self.__profile_name}' in region {self.__region_name} has error: {str(e)}"
                )
                self.__boto_error = e
                self.__describe_instances_works = False

        return self.__describe_instances_works

    def get_boto_error(self) -> botocore.exceptions.ClientError:
        return self.__boto_error

    def has_boto_error(self) -> bool:
        return self.__boto_error is not None

    def __set_instance_result(self, instance_result: EC2InstanceResult):
        self.__instance_results[
            instance_result.get_instance_filter().get_filter_name()
        ] = instance_result

    def is_instance_result_cached(self, instance_filter: str) -> bool:
        return self.get_instance_result(instance_filter) != None

    def get_instance_result(self, instance_filter: str) -> EC2InstanceResult | None:
        return self.__instance_results.get(instance_filter, None)

    def get_region_name(self) -> str:
        return self.__region_name

    def __load_instances_helper(
        self, instance_filter: dict[str, Any], next_token: str | None = None
    ) -> List[dict[str, Any]]:
        instances: List[dict[str, Any]] = []

        if next_token is None:
            response = self.__ec2_client.describe_instances(Filters=instance_filter)
        else:
            response = self.__ec2_client.describe_instances(
                Filters=instance_filter, next_token=next_token
            )

        if "NextToken" in response:
            next_token = response["NextToken"]
            instances.extend(self.__load_instances_helper(instance_filter, next_token))
            return instances
        else:
            result = []
            for reservation in response["Reservations"]:
                result.extend(reservation["Instances"])

            return result

    def load_instances_from_boto(
        self, instance_filter: InstanceFilter
    ) -> EC2InstanceResult:

        logging.getLogger().debug(
            f"[ssm-session-helper] load_instances_from_boto called for '{self.__profile_name}' in region {self.__region_name} with instance filter {instance_filter.get_filter_value()} and exclude {instance_filter.get_exclude_regex()}"
        )

        try:
            instances: List[EC2Instance] = []

            for filter_dict in instance_filter.get_filter_value():
                filter_dict.append(self.__running_instance_filter)
                result_instances = self.__load_instances_helper(filter_dict)
                for i in result_instances:
                    instances.append(EC2Instance(i))

            self.__describe_instances_works = True

            exclude_regex = instance_filter.get_exclude_regex()

            if exclude_regex is None:
                filtered_instances = instances
            else:
                filtered_instances = []
                for j in instances:
                    match_found = False
                    for i in exclude_regex:
                        if re.search(i, j.get_instance_name()) is not None:
                            match_found = True

                    if not match_found:
                        filtered_instances.append(j)

            if len(filtered_instances) > 0:
                filtered_instances = sorted(
                    filtered_instances, key=lambda x: x.get_instance_name()
                )

            instance_result = EC2InstanceResult(
                instance_filter=instance_filter, instances=filtered_instances
            )
            if len(filtered_instances) > 0:
                instance_result.set_selected_instance_id(
                    filtered_instances[0].get_instance_id()
                )
            else:
                instance_result.set_selected_instance_id("")
            self.__set_instance_result(instance_result)

            if instance_result.get_instances() is not None:
                logging.getLogger().debug(
                    f"[ssm-session-helper] load_instances_from_boto instances {[x.get_instance_name() for x in instance_result.get_instances() ]}"
                )
            else:
                logging.getLogger().debug(
                    f"[ssm-session-helper] load_instances_from_boto instances returned is null"
                )

            return instance_result

        except Exception as e:
            logging.getLogger().error(
                f"[ssm-session-helper] load_instances_from_boto Error for profile '{self.__profile_name}' has error: {str(e)}"
            )
            self.__boto_error = e
            self.__describe_instances_works = False
            raise e


class Profile:
    PROFILE_TOKEN_ACTIVE = "PROFILE_TOKEN_ACTIVE"
    PROFILE_TOKEN_EXPIRED = "PROFILE_TOKEN_EXPIRED"
    PROFILE_TOKEN_NOT_FOUND = "PROFILE_TOKEN_NOT_FOUND"

    __profile_name: str
    __regions: dict[str, Region]
    __default_region_name: str
    __token_expiry: datetime
    __describe_instances_tested: bool
    __profile_error: Exception
    __describe_instances_working: bool

    def __init__(
        self,
        profile_name: str,
        default_region_name: str,
        default_instance_filter: InstanceFilter,
    ):
        self.__regions = {}
        self.__describe_instances_tested = False
        self.set_profile_name(profile_name)
        self.__token_expiry = None
        self.__default_region_name = default_region_name
        default_region = Region(
            profile_name=profile_name,
            default_instance_filter=default_instance_filter,
            region_name=default_region_name,
        )
        self.add_or_update_region(default_region)
        self.set_default_region_name(default_region_name)
        self.__profile_error = None
        self.__describe_instances_working = True

    def set_default_region_name(self, default_region_name: str):
        self.__default_region_name = default_region_name

    def set_profile_name(self, profile_name: str):
        self.__profile_name = profile_name

    def add_or_update_region(self, region: Region):
        self.__regions[region.get_region_name()] = region

    def set_token_expiry_datetime(self, expiry: datetime | None):
        self.__token_expiry = expiry

    def has_expiry_token(self) -> bool:
        return self.__token_expiry is not None

    def evaluate_token_expiry(self) -> str:
        local_now = datetime.now()
        local_now = local_now.astimezone(timezone.utc)

        if self.__token_expiry is None:
            logging.getLogger().warning(
                f"[ssm-session-helper] No profile token found for {self.__profile_name}"
            )
            return Profile.PROFILE_TOKEN_NOT_FOUND
        elif self.__token_expiry > local_now:
            logging.getLogger().debug(
                f"[ssm-session-helper] evaluate_token_expiry for {self.__profile_name}: {Profile.PROFILE_TOKEN_ACTIVE}"
            )
            return Profile.PROFILE_TOKEN_ACTIVE
        else:
            logging.getLogger().debug(
                f"[ssm-session-helper] evaluate_token_expiry for {self.__profile_name}: {Profile.PROFILE_TOKEN_EXPIRED}"
            )
            return Profile.PROFILE_TOKEN_EXPIRED

    def region_exists(self, region_name: str) -> bool:
        return self.get_region(region_name, None) is not None

    def get_profile_name(self, obfuscated=False) -> str:
        if obfuscated:
            return obfuscator.obfuscate(self.__profile_name)
        else:
            return self.__profile_name

    def get_default_region(self) -> Region:
        return self.get_region(self.__default_region_name)

    def get_default_region_name(self) -> str:
        return self.__default_region_name

    def get_error(self) -> Exception:
        return self.__profile_error

    def get_region(self, region_name: str) -> Region:
        return self.__regions.get(region_name, None)

    def is_region_cached(self, region_name: str):
        return self.get_region(region_name) is not None

    def test_call_describe_instances(self):
        self.__describe_instances_tested = True
        region = self.get_default_region()
        region.test_call_describe_instances()
        it_worked = region.is_describe_instances_working()
        self.__describe_instances_working = it_worked
        if not it_worked:
            self.__profile_error = region.get_boto_error()
            self.has_boto_error

    def is_describe_instances_tested(self) -> bool:
        return self.__describe_instances_tested

    def is_describe_instances_working(self) -> bool:
        return self.__describe_instances_working

    def has_boto_error(self) -> bool:
        return self.__profile_error is not None


class ProfileCollection:

    __aws_profiles: dict[str, Profile]
    __credentials_filename: str
    __supported_regions: List[str]
    __default_region: str
    __profile_regex_strings: List[str]
    __selected_profile_name: str
    __default_instance_filter: InstanceFilter

    def __init__(
        self,
        credentials_filename: str,
        supported_regions: List[str],
        default_region_name: str,
        default_instance_filter: InstanceFilter,
        profile_regex_strings: List[str] = None,
    ):

        self.__aws_profiles = {}
        self.__credentials_filename = credentials_filename
        self.__profile_regex_strings = profile_regex_strings
        self.__default_region = default_region_name
        self.__supported_regions = supported_regions
        self.__selected_profile_name = ""
        self.__default_instance_filter = (default_instance_filter,)
        self.__read_session_profiles(profile_regex_strings)

    def get_profiles(self, sorted=False) -> List[Profile]:
        return list(self.__aws_profiles.values())

    def get_active_profiles(self) -> List[Profile]:
        return [
            i
            for i in self.get_profiles()
            if i.is_describe_instances_tested() and i.is_describe_instances_working()
        ]

    def get_expired_profiles(self) -> List[Profile]:
        return [
            i
            for i in self.get_profiles()
            if i.is_describe_instances_tested()
            and i.has_boto_error()
            and "expired" in str(i.get_error()).lower()
        ]

    def get_errored_profiles(self) -> List[Profile]:
        return [
            i
            for i in self.get_profiles()
            if i.is_describe_instances_tested()
            and i.has_boto_error()
            and not ("expired" in str(i.get_error()).lower())
        ]

    def get_profile(self, profile_name: str) -> Profile:
        return self.__aws_profiles.get(profile_name, None)

    def get_supported_regions(self) -> List[str]:
        return self.__supported_regions

    def get_profile_regex_strings(self) -> List[str]:
        return self.__profile_regex_strings

    def get_selected_profile_name(self) -> str:
        return self.__selected_profile_name

    def get_selected_profile(self) -> Profile:
        return self.get_profile(profile_name=self.get_selected_profile_name())

    def set_profile_regex_strings(self, matches: List[str]):
        self.__profile_regex_strings = matches

    def set_selected_profile_name(self, profile_name: str):
        self.__selected_profile_name = profile_name

    def __is_regex_in_profile_name(self, profile_name):
        match_found = False
        for regex in self.__profile_regex_strings:
            if re.search(regex, profile_name) is not None:
                match_found = True
                break

        return match_found

    def __read_session_profiles(self, regex_list: List[str] = None):
        self.set_profile_regex_strings(regex_list)

        with open(self.__credentials_filename, "r") as f:
            contents = f
            profile_to_decode = ""
            skip = False
            for line in contents:

                if line.startswith("[") and line.endswith("]\n"):
                    profile_name = line.strip("]\n").lstrip("[")

                    if self.__is_regex_in_profile_name(profile_name):
                        profile_to_decode = profile_name
                        skip = False
                        self.__aws_profiles[profile_to_decode] = Profile(
                            profile_name=profile_name,
                            default_region_name=self.__default_region,
                            default_instance_filter=self.__default_instance_filter,
                        )
                    else:
                        skip = True
                elif not skip:
                    line_contents = [
                        i.lstrip(" ").strip(" \n") for i in line.split("=")
                    ]

                    if len(line_contents) > 1:
                        line_key = line_contents[0]
                        line_value = line_contents[1]
                        if not line_key.startswith("aws_"):
                            if line_key.startswith("x_security_token_expires"):
                                datetime_object = parse(line_value)
                                self.__aws_profiles[
                                    profile_to_decode
                                ].set_token_expiry_datetime(datetime_object)


# region = Region(profile_name='sie-cloud-bis-nonprod-zz-mlu-admin', region_name='us-west-2')

# can_call = region.test_call_describe_instances()

# result = region.load_instances_from_boto(DEFAULT_ALL_FILTER)
