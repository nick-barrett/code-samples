from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from veloapi.configmodules.module_base import ConfigModuleBase
from veloapi.pydantic_shared import CamelModel


class FirewallData(CamelModel):
    model_config = ConfigDict(extra="allow")


class FirewallMetadata(CamelModel):
    override: bool
    enabled: bool

    model_config = ConfigDict(extra="allow")


class SecurityServiceGroupRef(BaseModel):

    pass


class ProfileFirewallRefs(BaseModel):
    security_service_group: SecurityServiceGroupRef | list[SecurityServiceGroupRef] = (
        Field(alias="firewall:securityServiceGroup")
    )


class ProfileFirewallModule(ConfigModuleBase):
    name: Literal["firewall"]
    data: FirewallData
    metadata: FirewallMetadata
    refs: ProfileFirewallRefs

    model_config = ConfigDict(extra="allow")


"""
{
	"firewall:securityServiceGroup": {
		"id": 103341,
		"enterpriseObjectId": 27512,
		"configurationId": 8702,
		"moduleId": 41379,
		"segmentObjectId": null,
		"ref": "firewall:securityServiceGroup",
		"data": {
			"urlCategoryFiltering": {
				"id": 27509,
				"created": "2024-12-05T04:19:09.000Z",
				"operatorId": null,
				"networkId": null,
				"enterpriseId": 1727,
				"edgeId": null,
				"gatewayId": null,
				"parentGroupId": null,
				"description": "",
				"object": "PROPERTY",
				"name": "monitor-all",
				"type": "urlCategoryFiltering",
				"logicalId": "0c6fd546-e956-49fa-86e3-79bde75ab6cb",
				"alertsEnabled": 1,
				"operatorAlertsEnabled": 1,
				"status": null,
				"statusModified": "0000-00-00 00:00:00",
				"previousData": null,
				"previousCreated": "0000-00-00 00:00:00",
				"draftData": null,
				"draftCreated": "0000-00-00 00:00:00",
				"draftComment": null,
				"data": {
					"allowAndLogCategories": [
						0,
						1,
						2,
						3,
						4,
						5,
						6,
						7,
						8,
						9,
						10,
						11,
						12,
						13,
						14,
						15,
						16,
						17,
						18,
						19,
						20,
						21,
						22,
						23,
						24,
						25,
						26,
						27,
						28,
						29,
						30,
						31,
						32,
						33,
						34,
						35,
						36,
						37,
						38,
						39,
						40,
						41,
						42,
						43,
						44,
						45,
						46,
						47,
						48,
						49,
						50,
						51,
						52,
						53,
						54,
						55,
						56,
						57,
						58,
						59,
						60,
						61,
						62,
						63,
						64,
						65,
						66,
						67,
						68,
						69,
						70,
						71,
						72,
						73,
						74,
						75,
						76,
						77,
						78,
						79,
						80,
						81,
						82,
						83,
						85,
						86,
						87
					],
					"blockedCategories": [],
					"unknownCategoryAction": "allow"
				},
				"lastContact": "0000-00-00 00:00:00",
				"version": "1734155031950",
				"modified": "2024-12-14T05:43:52.000Z"
			},
			"urlReputationFiltering": {
				"id": 27511,
				"created": "2024-12-05T04:20:32.000Z",
				"operatorId": null,
				"networkId": null,
				"enterpriseId": 1727,
				"edgeId": null,
				"gatewayId": null,
				"parentGroupId": null,
				"description": "",
				"object": "PROPERTY",
				"name": "basic-url-rep",
				"type": "urlReputationFiltering",
				"logicalId": "e4cc8041-088a-43a9-b48c-ccdd9cb86ccc",
				"alertsEnabled": 1,
				"operatorAlertsEnabled": 1,
				"status": null,
				"statusModified": "0000-00-00 00:00:00",
				"previousData": null,
				"previousCreated": "0000-00-00 00:00:00",
				"draftData": null,
				"draftCreated": "0000-00-00 00:00:00",
				"draftComment": null,
				"data": {
					"minReputationScore": 1,
					"allowAndLogReputations": [
						1,
						0,
						2,
						3
					],
					"unknownReputationAction": "block"
				},
				"lastContact": "0000-00-00 00:00:00",
				"version": "1733502940957",
				"modified": "2024-12-06T16:35:41.000Z"
			},
			"idps": {
				"id": 27510,
				"created": "2024-12-05T04:19:24.000Z",
				"operatorId": null,
				"networkId": null,
				"enterpriseId": 1727,
				"edgeId": null,
				"gatewayId": null,
				"parentGroupId": null,
				"description": "abcd",
				"object": "PROPERTY",
				"name": "ids-only",
				"type": "idps",
				"logicalId": "994469d0-fbf6-4ca9-a30d-13f24db02d69",
				"alertsEnabled": 1,
				"operatorAlertsEnabled": 1,
				"status": null,
				"statusModified": "0000-00-00 00:00:00",
				"previousData": null,
				"previousCreated": "0000-00-00 00:00:00",
				"draftData": null,
				"draftCreated": "0000-00-00 00:00:00",
				"draftComment": null,
				"data": {
					"idsEnabled": true,
					"ipsEnabled": false,
					"logEnabled": true
				},
				"lastContact": "0000-00-00 00:00:00",
				"version": "1734155438714",
				"modified": "2024-12-14T05:50:39.000Z"
			}
		},
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
