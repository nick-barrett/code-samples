from uuid import UUID

from veloapi.pydantic_shared import (
    CamelModel,
    EnterpriseObjectType,
    OptVcoDatetime,
    VcoDatetime,
)


class ConfigModuleBase(CamelModel):
    id: int
    created: VcoDatetime
    type: str
    description: str | None
    schema_version: str
    version: str
    configuration_id: int
    enterprise_logical_id: UUID | None
    effective: str
    modified: OptVcoDatetime


class RefBase(CamelModel):
    id: int
    enterprise_object_id: int
    configuration_id: int
    module_id: int
    segment_object_id: int | None
    ref: str
    modified: OptVcoDatetime
    version: str
    object: EnterpriseObjectType
    name: str
    type: str
    logical_id: UUID
    parent_group_id: int | None
    status: str | None
    segment_logical_id: UUID | None


"""
{
	"firewall:securityServiceGroup": {
		"id": 103341,
		"enterpriseObjectId": 27512,
		"configurationId": 8702,
		"moduleId": 41379,
		"segmentObjectId": null,
		"ref": "firewall:securityServiceGroup",
        "data": {...}
		"modified": "2024-12-14T05:50:39.000Z",
		"version": "1734155438714",
		"object": "PROPERTY",
		"name": "basic-ssg",
		"type": "securityServiceGroup",
		"logicalId": "a05adbf2-e6ea-4aa3-bf48-9a0ddc3e0f3b",
		"parentGroupId": null,
		"status": null,
		"segmentLogicalId": null
	}
}
"""

"""
{
	"objectGroup:addressGroup": {
		"id": 103342,
		"enterpriseObjectId": 27190,
		"configurationId": 8702,
		"moduleId": 41379,
		"segmentObjectId": null,
		"ref": "objectGroup:addressGroup",
		"data": [
			{
				"ip": "1.2.3.4",
				"rule_type": "exact",
				"mask": "255.255.255.255"
			},
			{
				"ip": "192.2.0.0",
				"rule_type": "prefix",
				"mask": "255.255.255.0"
			},
			{
				"ip": "192.168.0.0",
				"rule_type": "netmask",
				"mask": "255.255.0.0"
			},
			{
				"ip": "10.0.0.0",
				"rule_type": "wildcard",
				"mask": "255.0.0.0"
			},
			{
				"ip": "2001::",
				"rule_type": "exact",
				"mask": "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"
			},
			{
				"ip": "2002::",
				"rule_type": "prefix",
				"mask": "ffff:ffff:ffff:ffff:0000:0000:0000:0000"
			},
			{
				"ip": "2003::",
				"rule_type": "netmask",
				"mask": "ffff::"
			},
			{
				"domain": "foo.org"
			}
		],
		"modified": "2024-12-13T19:47:14.000Z",
		"version": "0",
		"object": "PROPERTY",
		"name": "foo-ag",
		"type": "address_group",
		"logicalId": "10061826-324a-41bb-b363-d090a670ad21",
		"parentGroupId": null,
		"status": null,
		"segmentLogicalId": null
	}
}
"""

"""
{
	"objectGroup:portGroup": [
		{
			"id": 103343,
			"enterpriseObjectId": 26770,
			"configurationId": 8702,
			"moduleId": 41379,
			"segmentObjectId": null,
			"ref": "objectGroup:portGroup",
			"data": [
				{
					"proto": 6,
					"port_low": 9090,
					"port_high": 9090
				},
				{
					"proto": 17,
					"port_low": 1000,
					"port_high": 2000
				},
				{
					"proto": 1,
					"type": 2,
					"code_low": 3,
					"code_high": 3
				},
				{
					"proto": 58,
					"type": 4,
					"code_low": 5,
					"code_high": 5
				}
			],
			"modified": "2024-12-14T05:07:29.000Z",
			"version": "0",
			"object": "PROPERTY",
			"name": "test-sg",
			"type": "port_group",
			"logicalId": "9a257d69-19a8-4523-894c-66879b44fa5f",
			"parentGroupId": null,
			"status": null,
			"segmentLogicalId": null
		},
		{
			"id": 103344,
			"enterpriseObjectId": 27527,
			"configurationId": 8702,
			"moduleId": 41379,
			"segmentObjectId": null,
			"ref": "objectGroup:portGroup",
			"data": [
				{
					"proto": 6,
					"port_low": 80,
					"port_high": 80
				},
				{
					"proto": 6,
					"port_low": 443,
					"port_high": 443
				},
				{
					"proto": 6,
					"port_low": 8080,
					"port_high": 8080
				},
				{
					"proto": 6,
					"port_low": 8443,
					"port_high": 8443
				},
				{
					"proto": 6,
					"port_low": 8888,
					"port_high": 8888
				}
			],
			"modified": "2024-12-09T22:23:14.000Z",
			"version": "0",
			"object": "PROPERTY",
			"name": "web",
			"type": "port_group",
			"logicalId": "75611373-17e7-4ef1-9723-0e401f3af18f",
			"parentGroupId": null,
			"status": null,
			"segmentLogicalId": null
		}
	]
}
"""
