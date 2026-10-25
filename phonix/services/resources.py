# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""The entities the REST API and MCP expose with list/get/create/update/delete."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from phonix.services import dialplan as dp
from phonix.services import hours as hours_svc
from phonix.services import ivr as ivr_svc
from phonix.services import manager as ami_svc
from phonix.services import phones as phone_svc
from phonix.services import providers as provider_svc
from phonix.services.common import parse


@dataclass(frozen=True)
class Resource:
    path: str  # REST collection path below /api/v1
    tag: str  # plural, human readable
    name: str  # singular identifier for MCP tool names
    schema: type[BaseModel]
    list_fn: Callable[..., Any]
    get_fn: Callable[..., Any]
    create_fn: Callable[..., Any]
    update_fn: Callable[..., Any]
    delete_fn: Callable[..., Any]
    to_dict: Callable[..., dict[str, Any]]
    search_fields: Callable[[Any], Iterable[object]]
    parse_fn: Callable[[dict[str, Any]], Any] | None = None
    enable_fn: Callable[..., Any] | None = None
    # PINs: left out for read-only tokens (a token that may write could change them anyway)
    pins: tuple[str, ...] = ()
    # plural for MCP tool names (list_<plural>); default: name + "s"
    plural: str = ""

    @property
    def plural_name(self) -> str:
        return self.plural or self.name + "s"

    def parse(self, data: dict[str, Any]) -> Any:
        return self.parse_fn(data) if self.parse_fn else parse(self.schema, data)

    def public(self, obj: Any, read_only: bool) -> dict[str, Any]:
        data = self.to_dict(obj)
        if read_only:
            for key in self.pins:
                data.pop(key, None)
        return data


RESOURCES = (
    Resource(
        "/phones",
        "phones",
        "phone",
        phone_svc.PhoneIn,
        phone_svc.list_phones,
        phone_svc.get_phone,
        phone_svc.create_phone,
        phone_svc.update_phone,
        phone_svc.delete_phone,
        phone_svc.to_dict,
        phone_svc.search_fields,
        phone_svc.parse_phone,
        phone_svc.set_enabled,
        pins=("vm_pin",),
    ),
    Resource(
        "/providers",
        "providers",
        "provider",
        provider_svc.ProviderIn,
        provider_svc.list_providers,
        provider_svc.get_provider,
        provider_svc.create_provider,
        provider_svc.update_provider,
        provider_svc.delete_provider,
        provider_svc.to_dict,
        provider_svc.search_fields,
        provider_svc.parse_provider,
        provider_svc.set_enabled,
    ),
    Resource(
        "/callgroups",
        "call groups",
        "callgroup",
        dp.CallGroupIn,
        dp.list_callgroups,
        dp.get_callgroup,
        dp.create_callgroup,
        dp.update_callgroup,
        dp.delete_callgroup,
        dp.callgroup_to_dict,
        dp.callgroup_search_fields,
    ),
    Resource(
        "/conferences",
        "conference rooms",
        "conference",
        dp.ConferenceRoomIn,
        dp.list_rooms,
        dp.get_room,
        dp.create_room,
        dp.update_room,
        dp.delete_room,
        dp.room_to_dict,
        dp.room_search_fields,
        pins=("pin", "admin_pin"),
    ),
    Resource(
        "/applications",
        "applications",
        "application",
        dp.ApplicationIn,
        dp.list_applications,
        dp.get_application,
        dp.create_application,
        dp.update_application,
        dp.delete_application,
        dp.application_to_dict,
        dp.application_search_fields,
    ),
    Resource(
        "/ivr-menus",
        "IVR menus",
        "ivr_menu",
        ivr_svc.IvrMenuIn,
        ivr_svc.list_menus,
        ivr_svc.get_menu,
        ivr_svc.create_menu,
        ivr_svc.update_menu,
        ivr_svc.delete_menu,
        ivr_svc.to_dict,
        ivr_svc.search_fields,
        enable_fn=ivr_svc.set_enabled,
    ),
    Resource(
        "/business-hours",
        "business hours",
        "business_hours",
        hours_svc.BusinessHoursIn,
        hours_svc.list_hours,
        hours_svc.get_hours,
        hours_svc.create_hours,
        hours_svc.update_hours,
        hours_svc.delete_hours,
        hours_svc.to_dict,
        hours_svc.search_fields,
        plural="business_hours",
    ),
    Resource(
        "/ami-users",
        "manager users",
        "ami_user",
        ami_svc.AmiUserIn,
        ami_svc.list_ami_users,
        ami_svc.get_ami_user,
        ami_svc.create_ami_user,
        ami_svc.update_ami_user,
        ami_svc.delete_ami_user,
        ami_svc.to_dict,
        ami_svc.search_fields,
    ),
)
