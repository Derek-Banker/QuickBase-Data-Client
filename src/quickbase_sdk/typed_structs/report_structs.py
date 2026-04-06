# src/quickbase_sdk/typed_structs/report_structs.py

from typing import TypedDict, Literal, Dict, Any, List, Union

# —————————————————————————————————————————————————————
# All supported report‐type literals
# —————————————————————————————————————————————————————
ReportType = Literal[
    "table",
    "summary",
    "calendar",
    "waterfall",
    "pie",
    "line",
    "stackedBar",
    "bar",
    "horizontalBar",
    "horizontalStackedBar",
    "gauge",
]

# —————————————————————————————————————————————————————
# Base report keys (common to every report)              :contentReference[oaicite:0]{index=0}:contentReference[oaicite:1]{index=1}
# —————————————————————————————————————————————————————
class BaseReport(TypedDict):
    """Common required keys on every report object."""
    id: str
    name: str
    type: ReportType
    query: Dict[str, Any]

# —————————————————————————————————————————————————————
# Table report                                                   :contentReference[oaicite:2]{index=2}:contentReference[oaicite:3]{index=3}
# —————————————————————————————————————————————————————
class TableColumnProps(TypedDict, total=False):
    fieldId: int
    labelOverride: str

class TableReportProps(TypedDict, total=False):
    displayOnlyNewOrChangedRecords: bool
    columnProperties: List[TableColumnProps]

class TableReport(BaseReport, total=False):
    type: Literal["table"]
    description: str
    ownerId: int
    properties: TableReportProps
    usedLast: str
    usedCount: int

# —————————————————————————————————————————————————————
# Summary report                                                :contentReference[oaicite:4]{index=4}:contentReference[oaicite:5]{index=5}
# —————————————————————————————————————————————————————
class SummaryGroupProps(TypedDict, total=False):
    fieldId: int
    grouping: Literal["equal-values", "case-insensitive", "case-sensitive"]

class SummarySortProps(TypedDict, total=False):
    fieldId: int
    order: Literal["ASC", "DESC", "equal-values"]

class SummaryReportProps(TypedDict, total=False):
    groupBy: List[SummaryGroupProps]
    sortBy: List[SummarySortProps]

class SummaryReport(BaseReport, total=False):
    type: Literal["summary"]
    description: str
    ownerId: int
    properties: SummaryReportProps
    usedLast: str
    usedCount: int

# —————————————————————————————————————————————————————
# Calendar report
# —————————————————————————————————————————————————————
class CalendarReportProps(TypedDict, total=False):
    dateField: int
    titleField: int

class CalendarReport(BaseReport, total=False):
    type: Literal["calendar"]
    description: str
    ownerId: int
    properties: CalendarReportProps
    usedLast: str
    usedCount: int

# —————————————————————————————————————————————————————
# Waterfall report (no known unique props yet)
# —————————————————————————————————————————————————————
class WaterfallReportProps(TypedDict, total=False):
    # (add waterfall‐specific keys here once documented)
    pass

class WaterfallReport(BaseReport, total=False):
    type: Literal["waterfall"]
    description: str
    ownerId: int
    properties: WaterfallReportProps
    usedLast: str
    usedCount: int

# —————————————————————————————————————————————————————
# Pie chart report
# —————————————————————————————————————————————————————
class PieReportProps(TypedDict, total=False):
    sliceField: int
    valueField: int

class PieReport(BaseReport, total=False):
    type: Literal["pie"]
    description: str
    ownerId: int
    properties: PieReportProps
    usedLast: str
    usedCount: int

# —————————————————————————————————————————————————————
# Line chart report
# —————————————————————————————————————————————————————
class LineReportProps(TypedDict, total=False):
    xField: int
    yField: int

class LineReport(BaseReport, total=False):
    type: Literal["line"]
    description: str
    ownerId: int
    properties: LineReportProps
    usedLast: str
    usedCount: int

# —————————————————————————————————————————————————————
# Bar chart report
# —————————————————————————————————————————————————————
class BarReportProps(TypedDict, total=False):
    xField: int
    yField: int

class BarReport(BaseReport, total=False):
    type: Literal["bar"]
    description: str
    ownerId: int
    properties: BarReportProps
    usedLast: str
    usedCount: int

# —————————————————————————————————————————————————————
# Horizontal bar chart report
# —————————————————————————————————————————————————————
class HorizontalBarReportProps(TypedDict, total=False):
    xField: int
    yField: int

class HorizontalBarReport(BaseReport, total=False):
    type: Literal["horizontalBar"]
    description: str
    ownerId: int
    properties: HorizontalBarReportProps
    usedLast: str
    usedCount: int

# —————————————————————————————————————————————————————
# Horizontal stacked bar report
# —————————————————————————————————————————————————————
class HorizontalStackedBarReportProps(TypedDict, total=False):
    xField: int
    stackByField: int

class HorizontalStackedBarReport(BaseReport, total=False):
    type: Literal["horizontalStackedBar"]
    description: str
    ownerId: int
    properties: HorizontalStackedBarReportProps
    usedLast: str
    usedCount: int

# —————————————————————————————————————————————————————
# Gauge chart report
# —————————————————————————————————————————————————————
class GaugeReportProps(TypedDict, total=False):
    gaugeField: int

class GaugeReport(BaseReport, total=False):
    type: Literal["gauge"]
    description: str
    ownerId: int
    properties: GaugeReportProps
    usedLast: str
    usedCount: int

# —————————————————————————————————————————————————————
# Union of every specific report struct
# —————————————————————————————————————————————————————
ReportStruct = Union[
    TableReport,
    SummaryReport,
    CalendarReport,
    WaterfallReport,
    PieReport,
    LineReport,
    BarReport,
    HorizontalBarReport,
    HorizontalStackedBarReport,
    GaugeReport,
]
