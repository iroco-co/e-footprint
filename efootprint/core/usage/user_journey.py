from efootprint.constants.units import u
from efootprint.abstract_modeling_classes.modeling_object import ModelingObject
from efootprint.constants.sources import SourceValue
from efootprint.core.service import Service
from efootprint.core.hardware.servers.server_base_class import Server
from efootprint.core.hardware.storage import Storage
from efootprint.logger import logger

from typing import List, Set, Type, Optional


class UserJourneyStep(ModelingObject):
    def __init__(self, name: str, service: Optional[Service], data_upload: SourceValue, data_download: SourceValue,
                 user_time_spent: SourceValue, request_duration: SourceValue = None,
                 cpu_needed: SourceValue = None, ram_needed: SourceValue = None):
        super().__init__(name)
        self.ram_needed = None
        self.service = service
        if not data_upload.value.check("[]/[user_journey]"):
            raise ValueError("Variable 'data_upload' does not have the appropriate '[]/[user_journey]' dimensionality")
        if not data_download.value.check("[]/[user_journey]"):
            raise ValueError("Variable 'data_upload' does not have the appropriate '[]/[user_journey]' dimensionality")
        self.data_upload = data_upload
        self.data_upload.set_name(f"Data upload of request {self.name}")
        self.data_download = data_download
        self.data_download.set_name(f"Data download of request {self.name}")

        if not user_time_spent.value.check("[time]/[user_journey]"):
            raise ValueError(
                "Variable 'user_time_spent' does not have the appropriate '[time]/[user_journey]' dimensionality")
        self.user_time_spent = user_time_spent
        self.user_time_spent.set_name(f"Time spent on step {self.name}")

        if self.service is None:
            if (self.data_download.magnitude > 0 or self.data_upload.magnitude > 0 or request_duration
                    or ram_needed or cpu_needed):
                raise ValueError(
                    f"When creating a user journey without service there should be no data transfer and no request"
                    f" duration or resource need")
        else:
            if request_duration is None:
                request_duration = SourceValue(1 * u.s)
            if not request_duration.value.check("[time]"):
                raise ValueError("Variable 'request_duration' does not have the appropriate '[time]' dimensionality")
            self.request_duration = request_duration
            self.request_duration.set_name(f"Request duration to {self.service.name} in {self.name}")
            if request_duration.value > user_time_spent.value * u.uj:
                # TODO: define a setter method to make this check also when the attribute is updated
                logger.warning("Variable 'request_duration' is greater than variable 'user_time_spent'")

            if ram_needed is None:
                ram_needed = SourceValue(100 * u.MB / u.uj)
            if not ram_needed.value.check("[] / [user_journey]"):
                raise ValueError(
                    "Variable 'ram_needed' does not have the appropriate '[] / [user_journey]' dimensionality")
            self.ram_needed = ram_needed
            self.ram_needed.set_name(f"RAM needed on server {self.service.server.name} to process {self.name}")

            if cpu_needed is None:
                cpu_needed = SourceValue(1 * u.core / u.uj)
            if not cpu_needed.value.check("[cpu] / [user_journey]"):
                raise ValueError(
                    "Variable 'cpu_needed' does not have the appropriate '[cpu] / [user_journey]' dimensionality")
            self.cpu_needed = cpu_needed
            self.cpu_needed.set_name(f"CPU needed on server {self.service.server.name} to process {self.name}")

    @property
    def user_journeys(self):
        return self.modeling_obj_containers

    @property
    def usage_patterns(self):
        return list(set(sum([uj.usage_patterns for uj in self.user_journeys], start=[])))

    @property
    def modeling_objects_whose_attributes_depend_directly_on_me(self) -> List:
        if len(self.user_journeys) > 0:
            return self.user_journeys
        elif self.service is not None:
            return [self.service]
        else:
            return []

    def self_delete(self):
        logger.warning(f"Deleting {self.name} and removing backward link in its service")
        if self.user_journeys:
            raise PermissionError(f"You can’t delete {self.name} because it has a user_journey pointing to it")
        self.service.modeling_obj_containers = [elt for elt in self.service.modeling_obj_containers if elt != self]
        self.service.launch_attributes_computation_chain()

    def after_init(self):
        self.init_has_passed = True
        self.compute_calculated_attributes()

    def __mul__(self, other):
        if type(other) not in [int, float]:
            raise ValueError(f"Can only multiply UserJourneyStep with int or float, not {type(other)}")
        raise NotImplementedError


class UserJourney(ModelingObject):
    def __init__(self, name: str, uj_steps: List[UserJourneyStep]):
        super().__init__(name)
        self.data_upload = None
        self.data_download = None
        self.duration = None
        self.calculated_attributes = ["duration", "data_download", "data_upload"]

        self._uj_steps = []
        # Triggers computation of calculated attributes
        self.uj_steps = uj_steps

    @property
    def uj_steps(self):
        return self._uj_steps

    @uj_steps.setter
    def uj_steps(self, new_uj_steps: List[UserJourneyStep]):
        # Here the observer pattern is implemented manually because uj_steps is a list and hence not handled by
        # ModelingObject’s __setattr__ logic
        removed_steps = [step for step in self.uj_steps if step not in new_uj_steps]
        for step in self._uj_steps:
            step.remove_obj_from_modeling_obj_containers(self)
        self._uj_steps = new_uj_steps
        for step in self._uj_steps:
            step.add_obj_to_modeling_obj_containers(self)
        for step in removed_steps:
            if len(step.user_journeys) == 0:
                step.launch_attributes_computation_chain()
        self.launch_attributes_computation_chain()

    @property
    def servers(self) -> Set[Server]:
        servers = set()
        for uj_step in self.uj_steps:
            if uj_step.service is not None:
                servers = servers | {uj_step.service.server}

        return servers

    @property
    def storages(self) -> Set[Storage]:
        storages = set()
        for uj_step in self.uj_steps:
            if uj_step.service is not None:
                storages = storages | {uj_step.service.storage}

        return storages

    @property
    def services(self) -> List[Service]:
        services = set()
        for uj_step in self.uj_steps:
            if uj_step.service is not None:
                services = services | {uj_step.service}

        return list(services)

    @property
    def usage_patterns(self):
        return self.modeling_obj_containers

    @property
    def modeling_objects_whose_attributes_depend_directly_on_me(self) -> List[Type["UsagePattern"]]:
        return self.usage_patterns

    def add_step(self, step: UserJourneyStep) -> None:
        step.add_obj_to_modeling_obj_containers(self)
        self.uj_steps = self.uj_steps + [step]

    def update_duration(self):
        user_time_spent_sum = sum([uj_step.user_time_spent for uj_step in self.uj_steps])

        self.duration = user_time_spent_sum.define_as_intermediate_calculation(f"Duration of {self.name}")

    def update_data_download(self):
        all_data_download = 0
        for uj_step in self.uj_steps:
            all_data_download += uj_step.data_download

        self.data_download = all_data_download.define_as_intermediate_calculation(f"Data download of {self.name}")

    def update_data_upload(self):
        all_data_upload = 0
        for uj_step in self.uj_steps:
            all_data_upload += uj_step.data_upload

        self.data_upload = all_data_upload.define_as_intermediate_calculation(f"Data upload of {self.name}")
