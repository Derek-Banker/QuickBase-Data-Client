# src/quickbase_sdk/typed_structs/base_structs.py

from typing import TypedDict, List, Literal, Dict, Any

class MemoryInfoStruct(TypedDict):
    estMemory: float
    estMemoryInclDependentApps: float

class SecurityPropertiesStruct(TypedDict, total=False):
    allowClone: bool
    allowExport: bool
    hideFromPublic: bool
    enableAppTokens: bool
    useIPFilter: bool
    mustBeRealmApproved: bool

class VariableStruct(TypedDict):
    name: str
    value: str

class AppStruct(TypedDict, total=False):
    """Matches GET /v1/apps/{appId} response"""
    id: str
    name: str
    description: str
    created: str                # ISO 8601 timestamp
    updated: str                # ISO 8601 timestamp
    dateFormat: str
    timeZone: str
    memoryInfo: MemoryInfoStruct
    hasEveryoneOnTheInternet: bool
    ancestorId: str
    variables: List[VariableStruct]
    dataClassification: str
    securityProperties: SecurityPropertiesStruct

class TableStruct(TypedDict, total=False):
    """Matches GET /v1/tables?appId=… (and POST /v1/tables) response"""
    id: str
    name: str
    alias: str
    description: str
    created: str                # ISO 8601 timestamp
    updated: str                # ISO 8601 timestamp
    nextRecordId: int
    nextFieldId: int
    defaultSortFieldId: int
    defaultSortOrder: Literal["ASC","DESC"]
    keyFieldId: int
    singleRecordName: str
    pluralRecordName: str
    sizeLimit: str
    spaceUsed: str
    spaceRemaining: str

# ========================================================================
# Field Properties
# ========================================================================

class BaseProperties(TypedDict, total=False):
    primaryKey: bool
    foreignKey: bool
    numLines: int
    maxLength: int
    appendOnly: bool
    allowHTML: bool
    allowMentions: bool
    sortAsGiven: bool
    carryChoices: bool
    allowNewChoices: bool
    formula: str
    defaultValue: str

class PicklistProperties(BaseProperties, total=False):
    choices: List[str]
    masterChoiceFieldId: int
    masterChoiceTableId: str

class DblinkProperties(PicklistProperties, total=False):
    sourceFieldId: int
    targetFieldId: int
    targetTableId: str
    useNewWindow: bool
    exact: bool
    linkText: str

class NumericProperties(BaseProperties, total=False):
    numberFormat: int
    decimalPlaces: int
    doesAverage: bool
    doesTotal: bool
    blankIsZero: bool

class PhoneNumberProperties(BaseProperties, total=False):
    useI18NFormat: bool
    defaultCountryCode: str
    hasExtension: bool

class FileAttachmentProperties(BaseProperties, total=False):
    maxVersions: int
    seeVersions: bool
    versionMode: Literal["keepallversions", "keeplastversions"]

class URLProperties(BaseProperties, total=False):
    abbreviate: bool
    appearsAs: str
    openTargetIn: Literal["sameWindow", "newWindow", "popup"]
    width: int

class DateProperties(BaseProperties, total=False):
    defaultToday: bool
    displayTime: bool
    hours24: bool
    displayRelative: bool

class LookupProperties(BaseProperties, total=False):
    lookupTargetFieldId: int

class SummaryProperties(BaseProperties, total=False):
    summaryFunction: Literal[
      "AVG", "SUM", "MAX", "MIN", "STD-DEV", "COUNT",
      "COMBINED-TEXT", "COMBINED-USER", "DISTINCT-COUNT"
    ]
    summaryTargetFieldId: int

# ========================================================================
# Field Definitions
# ========================================================================

class FieldStruct(TypedDict, total=False):
    """Matches GET /v1/fields?tableId=… response items"""
    id: int
    label: str
    fieldType: str
    mode: str
    noWrap: bool
    bold: bool
    required: bool
    appearsByDefault: bool
    findEnabled: bool
    unique: bool
    doesDataCopy: bool
    fieldHelp: str
    audited: bool
    properties: (
        BaseProperties
        | PicklistProperties
        | DblinkProperties
        | NumericProperties
        | PhoneNumberProperties
        | FileAttachmentProperties
        | URLProperties
        | DateProperties
        | LookupProperties
        | SummaryProperties
    )
    permissions: List[dict]