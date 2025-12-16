from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from enum import Enum


class Tier(BaseModel):
    """Pricing tier for tiered/volume pricing models.

    Fields match Zuora v1 API ProductRatePlanChargeTier object.
    See: https://developer.zuora.com/v1-api-reference/api/operation/Object_POSTProductRatePlanCharge/
    """

    Currency: str = "USD"
    Price: float
    StartingUnit: Optional[float] = None
    EndingUnit: Optional[float] = None
    PriceFormat: Literal["Per Unit", "Flat Fee"] = "Per Unit"
    Tier: Optional[int] = (
        None  # Tier number (1, 2, 3, etc.) - auto-assigned if not provided
    )


# ============ Zuora v1 API Enum Types ============

# ChargeModel enum values (exact strings from API)
ZUORA_CHARGE_MODELS = Literal[
    "Flat Fee Pricing",
    "Per Unit Pricing",
    "Volume Pricing",
    "Tiered Pricing",
    "Overage Pricing",
    "Tiered with Overage Pricing",
    "Discount-Fixed Amount",
    "Discount-Percentage",
    "Delivery Pricing",
    "MultiAttributePricing",
    "PreratedPerUnit",
    "PreratedPricing",
    "HighWatermarkVolumePricing",
    "HighWatermarkTieredPricing",
]

# ChargeType enum values
ZUORA_CHARGE_TYPES = Literal["OneTime", "Recurring", "Usage"]

# BillingPeriod enum values
ZUORA_BILLING_PERIODS = Literal[
    "Month",
    "Quarter",
    "Annual",
    "Semi-Annual",
    "Specific Months",
    "Subscription Term",
    "Week",
    "Specific Weeks",
    "Specific Days",
]

# BillCycleType enum values
ZUORA_BILL_CYCLE_TYPES = Literal[
    "DefaultFromCustomer",
    "SpecificDayofMonth",
    "SubscriptionStartDay",
    "ChargeTriggerDay",
    "SpecificDayofWeek",
    "TermStartDay",
    "TermEndDay",
]

# TriggerEvent enum values
ZUORA_TRIGGER_EVENTS = Literal[
    "ContractEffective",
    "ServiceActivation",
    "CustomerAcceptance",
]

# BillingTiming enum values
ZUORA_BILLING_TIMING = Literal["In Advance", "In Arrears"]

# RatingGroup enum values
ZUORA_RATING_GROUP = Literal[
    "ByBillingPeriod",
    "ByUsageStartDate",
    "ByUsageRecord",
    "ByUsageUpload",
    "ByGroupId",
]

# Product Category enum values
ZUORA_PRODUCT_CATEGORY = Literal[
    "Base Products",
    "Add On Services",
    "Miscellaneous Products",
]

# BillingPeriodAlignment enum values
ZUORA_BILLING_PERIOD_ALIGNMENT = Literal[
    "AlignToCharge",
    "AlignToSubscriptionStart",
    "AlignToTermStart",
    "AlignToTermEnd",
]

# EndDateCondition enum values
ZUORA_END_DATE_CONDITION = Literal["SubscriptionEnd", "FixedPeriod"]

# ListPriceBase enum values
ZUORA_LIST_PRICE_BASE = Literal[
    "Per Billing Period",
    "Per Month",
    "Per Week",
    "Per Year",
    "Per Specific Months",
]

# PriceChangeOption enum values
ZUORA_PRICE_CHANGE_OPTION = Literal[
    "NoChange",
    "SpecificPercentageValue",
    "UseLatestProductCatalogPricing",
]

# PriceIncreaseOption enum values
ZUORA_PRICE_INCREASE_OPTION = Literal[
    "FromTenantPercentageValue",
    "SpecificPercentageValue",
]

# DiscountLevel enum values
ZUORA_DISCOUNT_LEVEL = Literal["rateplan", "subscription", "account"]

# ApplyDiscountTo enum values
ZUORA_APPLY_DISCOUNT_TO = Literal[
    "ONETIME",
    "RECURRING",
    "USAGE",
    "ONETIMERECURRING",
    "ONETIMEUSAGE",
    "RECURRINGUSAGE",
    "ONETIMERECURRINGUSAGE",
]

# UpToPeriodsType enum values
ZUORA_UP_TO_PERIODS_TYPE = Literal[
    "Billing Periods",
    "Days",
    "Weeks",
    "Months",
    "Years",
]

# ChargeFunction enum values (Prepaid with Drawdown)
ZUORA_CHARGE_FUNCTION = Literal[
    "Standard",
    "Prepayment",
    "CommitmentTrueUp",
    "Drawdown",
    "CreditCommitment",
    "DrawdownAndCreditCommitment",
]

# CommitmentType enum values
ZUORA_COMMITMENT_TYPE = Literal["UNIT", "CURRENCY"]

# CreditOption enum values
ZUORA_CREDIT_OPTION = Literal["TimeBased", "ConsumptionBased", "FullCreditBack"]

# ValidityPeriodType enum values
ZUORA_VALIDITY_PERIOD_TYPE = Literal[
    "SUBSCRIPTION_TERM",
    "ANNUAL",
    "SEMI_ANNUAL",
    "QUARTER",
    "MONTH",
]

# RolloverApply enum values
ZUORA_ROLLOVER_APPLY = Literal["ApplyFirst", "ApplyLast"]

# PrepaidOperationType enum values
ZUORA_PREPAID_OPERATION_TYPE = Literal["topup", "drawdown"]

# ProrationOption enum values
ZUORA_PRORATION_OPTION = Literal[
    "NoProration",
    "TimeBasedProration",
    "DefaultFromTenantSetting",
    "ChargeFullPeriod",
]

# WeeklyBillCycleDay enum values
ZUORA_WEEKLY_BILL_CYCLE_DAY = Literal[
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
]

# OverageCalculationOption enum values
ZUORA_OVERAGE_CALCULATION_OPTION = Literal["EndOfSmoothingPeriod", "PerBillingPeriod"]

# OverageUnusedUnitsCreditOption enum values
ZUORA_OVERAGE_UNUSED_UNITS_CREDIT_OPTION = Literal["NoCredit", "CreditBySpecificRate"]

# SmoothingModel enum values
ZUORA_SMOOTHING_MODEL = Literal["RollingWindow", "Rollover"]

# UsageRecordRatingOption enum values
ZUORA_USAGE_RECORD_RATING_OPTION = Literal["EndOfBillingPeriod", "OnDemand"]

# RevenueRecognitionRuleName enum values
ZUORA_REVENUE_RECOGNITION_RULE_NAME = Literal[
    "Recognize upon invoicing",
    "Recognize daily over time",
]

# RevRecTriggerCondition enum values
ZUORA_REV_REC_TRIGGER_CONDITION = Literal[
    "ContractEffectiveDate",
    "ServiceActivationDate",
    "CustomerAcceptanceDate",
]

# TaxMode enum values
ZUORA_TAX_MODE = Literal["TaxExclusive", "TaxInclusive"]


# ============ Product Catalog Models ============


class Charge(BaseModel):
    """Product Rate Plan Charge model matching Zuora v1 API schema.

    See: https://developer.zuora.com/v1-api-reference/api/operation/Object_POSTProductRatePlanCharge/
    """

    # ============ Core Required Fields ============
    name: str = Field(..., description="Charge name (max 100 chars)")
    chargeType: ZUORA_CHARGE_TYPES = Field(
        ..., alias="type", description="Charge type: 'OneTime', 'Recurring', or 'Usage'"
    )
    chargeModel: ZUORA_CHARGE_MODELS = Field(
        ..., alias="model", description="Pricing model per Zuora API"
    )
    billCycleType: ZUORA_BILL_CYCLE_TYPES = Field(
        "DefaultFromCustomer", description="How to determine billing day"
    )
    billingPeriod: Optional[ZUORA_BILLING_PERIODS] = Field(
        None, description="Billing period for recurring charges"
    )
    triggerEvent: ZUORA_TRIGGER_EVENTS = Field(
        "ContractEffective", description="When to start billing"
    )

    # ============ Pricing Fields ============
    price: Optional[float] = Field(
        None, description="Price for flat fee or per unit models"
    )
    currency: str = Field("USD", description="Currency code")
    defaultQuantity: Optional[float] = Field(
        None,
        description="Default quantity of units. Required for Per Unit/Volume/Tiered Pricing.",
    )
    minQuantity: Optional[float] = Field(
        None, description="Minimum units allowed (max 16 chars)"
    )
    maxQuantity: Optional[float] = Field(
        None, description="Maximum units allowed (max 16 chars)"
    )
    includedUnits: Optional[float] = Field(
        None, description="Units included before overage pricing (for Overage models)"
    )
    tiers: Optional[List[Tier]] = Field(
        None, description="Pricing tiers for tiered/volume models"
    )

    # ============ Billing Configuration ============
    billingTiming: Optional[ZUORA_BILLING_TIMING] = Field(
        "In Advance", description="'In Advance' or 'In Arrears'. Not for Usage charges."
    )
    billingPeriodAlignment: Optional[ZUORA_BILLING_PERIOD_ALIGNMENT] = Field(
        None,
        description="Align charges within subscription: 'AlignToCharge', 'AlignToSubscriptionStart', 'AlignToTermStart', 'AlignToTermEnd'",
    )
    billCycleDay: Optional[int] = Field(
        None, description="Bill cycle day (1-31). Account BCD can override."
    )
    weeklyBillCycleDay: Optional[ZUORA_WEEKLY_BILL_CYCLE_DAY] = Field(
        None,
        description="Weekly bill cycle day. Required when BillCycleType='SpecificDayofWeek'",
    )
    specificBillingPeriod: Optional[int] = Field(
        None,
        description="Custom months/weeks when BillingPeriod='Specific Months/Weeks'",
    )
    listPriceBase: Optional[ZUORA_LIST_PRICE_BASE] = Field(
        None, description="List price base. Defaults to BillingPeriod if not set."
    )
    specificListPriceBase: Optional[int] = Field(
        None,
        description="Months for list price base (1-120). Required when ListPriceBase='Per Specific Months'",
    )

    # ============ Charge Duration ============
    endDateCondition: Optional[ZUORA_END_DATE_CONDITION] = Field(
        "SubscriptionEnd", description="'SubscriptionEnd' or 'FixedPeriod'"
    )
    upToPeriods: Optional[int] = Field(
        None,
        description="Charge duration (0-65535). Required when EndDateCondition='FixedPeriod'",
    )
    upToPeriodsType: Optional[ZUORA_UP_TO_PERIODS_TYPE] = Field(
        "Billing Periods", description="Period type for upToPeriods"
    )

    # ============ Price Change on Renewal ============
    priceChangeOption: Optional[ZUORA_PRICE_CHANGE_OPTION] = Field(
        "NoChange",
        description="Automatic price change on renewal: 'NoChange', 'SpecificPercentageValue', 'UseLatestProductCatalogPricing'",
    )
    priceIncreaseOption: Optional[ZUORA_PRICE_INCREASE_OPTION] = Field(
        None,
        description="Price increase on renewal: 'FromTenantPercentageValue' or 'SpecificPercentageValue'",
    )
    priceIncreasePercentage: Optional[float] = Field(
        None, description="Percentage increase/decrease on renewal (-100 to 100)"
    )
    useTenantDefaultForPriceChange: Optional[bool] = Field(
        None,
        description="Use tenant-level percentage uplift. Set false when using specific percentage.",
    )

    # ============ Usage Charge Fields ============
    uom: Optional[str] = Field(
        None,
        description="Unit of measure (max 25 chars). Required for Per Unit/Volume/Overage/Tiered models.",
    )
    ratingGroup: Optional[ZUORA_RATING_GROUP] = Field(
        None, description="How to aggregate usage for rating"
    )
    usageRecordRatingOption: Optional[ZUORA_USAGE_RECORD_RATING_OPTION] = Field(
        "EndOfBillingPeriod",
        description="When to rate usage records: 'EndOfBillingPeriod' or 'OnDemand'",
    )

    # ============ Overage Fields ============
    overagePrice: Optional[float] = Field(
        None, description="Price per unit after included units consumed"
    )
    overageCalculationOption: Optional[ZUORA_OVERAGE_CALCULATION_OPTION] = Field(
        None,
        description="When to calculate overage: 'EndOfSmoothingPeriod' or 'PerBillingPeriod'",
    )
    overageUnusedUnitsCreditOption: Optional[
        ZUORA_OVERAGE_UNUSED_UNITS_CREDIT_OPTION
    ] = Field(
        None, description="Credit unused units: 'NoCredit' or 'CreditBySpecificRate'"
    )
    numberOfPeriod: Optional[int] = Field(
        None, description="Periods for overage smoothing (positive integer)"
    )
    smoothingModel: Optional[ZUORA_SMOOTHING_MODEL] = Field(
        None, description="Overage smoothing model: 'RollingWindow' or 'Rollover'"
    )

    # ============ Discount Fields ============
    applyDiscountTo: Optional[ZUORA_APPLY_DISCOUNT_TO] = Field(
        None, description="Charge types discount applies to (for discount models)"
    )
    discountLevel: Optional[ZUORA_DISCOUNT_LEVEL] = Field(
        None, description="Discount scope: 'rateplan', 'subscription', or 'account'"
    )
    isStackedDiscount: Optional[bool] = Field(
        None, description="Calculate as stacked discount (Discount-Percentage only)"
    )
    applyToBillingPeriodPartially: Optional[bool] = Field(
        None,
        description="Allow discount duration aligned with billing period partially",
    )
    reflectDiscountInNetAmount: Optional[bool] = Field(
        False, description="Reflect discount in net amount for Zuora Revenue"
    )
    useDiscountSpecificAccountingCode: Optional[bool] = Field(
        None, description="Use specific accounting code for discount charge"
    )

    # ============ Accounting Fields ============
    accountingCode: Optional[str] = Field(
        None, description="Accounting code (max 100 chars)"
    )
    deferredRevenueAccount: Optional[str] = Field(
        None, description="Deferred revenue account name (max 100 chars)"
    )
    recognizedRevenueAccount: Optional[str] = Field(
        None, description="Recognized revenue account name (max 100 chars)"
    )

    # ============ Revenue Recognition Fields ============
    revenueRecognitionRuleName: Optional[ZUORA_REVENUE_RECOGNITION_RULE_NAME] = Field(
        None, description="'Recognize upon invoicing' or 'Recognize daily over time'"
    )
    revRecCode: Optional[str] = Field(
        None, description="Revenue recognition code (max 70 chars)"
    )
    revRecTriggerCondition: Optional[ZUORA_REV_REC_TRIGGER_CONDITION] = Field(
        None, description="When revenue recognition begins"
    )
    excludeItemBillingFromRevenueAccounting: Optional[bool] = Field(
        False,
        description="Exclude billing items from revenue accounting (Order to Revenue)",
    )
    excludeItemBookingFromRevenueAccounting: Optional[bool] = Field(
        False,
        description="Exclude booking items from revenue accounting (Order to Revenue)",
    )
    isAllocationEligible: Optional[bool] = Field(
        False,
        description="Allocation eligible for revenue recognition (Order to Revenue)",
    )
    isUnbilled: Optional[bool] = Field(
        False, description="Unbilled accounting (Order to Revenue)"
    )
    legacyRevenueReporting: Optional[bool] = Field(
        None, description="Legacy revenue reporting"
    )
    revenueRecognitionTiming: Optional[str] = Field(
        None, description="Revenue recognition timing (Order to Revenue)"
    )
    revenueAmortizationMethod: Optional[str] = Field(
        None, description="Revenue amortization method (Order to Revenue)"
    )
    productCategory: Optional[str] = Field(
        None, description="Product category for Zuora Revenue integration"
    )
    productClass: Optional[str] = Field(
        None, description="Product class for Zuora Revenue integration"
    )
    productFamily: Optional[str] = Field(
        None, description="Product family for Zuora Revenue integration"
    )
    productLine: Optional[str] = Field(
        None, description="Product line for Zuora Revenue integration"
    )

    # ============ Tax Fields ============
    taxable: Optional[bool] = Field(
        None,
        description="Whether charge is taxable. Requires TaxMode and TaxCode if true.",
    )
    taxCode: Optional[str] = Field(
        None, description="Tax code (max 64 chars). Required when Taxable=true."
    )
    taxMode: Optional[ZUORA_TAX_MODE] = Field(
        None,
        description="'TaxExclusive' or 'TaxInclusive'. Required when Taxable=true.",
    )

    # ============ Proration Fields ============
    prorationOption: Optional[ZUORA_PRORATION_OPTION] = Field(
        None, description="Charge-level proration option"
    )

    # ============ Prepaid with Drawdown Fields ============
    chargeFunction: Optional[ZUORA_CHARGE_FUNCTION] = Field(
        None, description="Charge function type (Prepaid with Drawdown feature)"
    )
    commitmentType: Optional[ZUORA_COMMITMENT_TYPE] = Field(
        None,
        description="Commitment type: 'UNIT' or 'CURRENCY' (Prepaid with Drawdown)",
    )
    creditOption: Optional[ZUORA_CREDIT_OPTION] = Field(
        None,
        description="Credit calculation: 'TimeBased', 'ConsumptionBased', 'FullCreditBack'",
    )
    drawdownRate: Optional[float] = Field(
        None, description="Conversion rate between Usage UOM and Drawdown UOM"
    )
    drawdownUom: Optional[str] = Field(None, description="Drawdown unit of measure")
    isPrepaid: Optional[bool] = Field(
        None, description="Whether this is a prepayment (topup) or drawdown charge"
    )
    prepaidOperationType: Optional[ZUORA_PREPAID_OPERATION_TYPE] = Field(
        None, description="'topup' or 'drawdown'"
    )
    prepaidQuantity: Optional[float] = Field(
        None, description="Units included in prepayment charge"
    )
    prepaidTotalQuantity: Optional[float] = Field(
        None, description="Total units available during validity period"
    )
    prepaidUom: Optional[str] = Field(
        None, description="Unit of measure for prepayment"
    )
    validityPeriodType: Optional[ZUORA_VALIDITY_PERIOD_TYPE] = Field(
        None,
        description="Prepaid validity period: 'SUBSCRIPTION_TERM', 'ANNUAL', 'SEMI_ANNUAL', 'QUARTER', 'MONTH'",
    )
    isRollover: Optional[bool] = Field(None, description="Enable rollover for prepaid")
    rolloverApply: Optional[ZUORA_ROLLOVER_APPLY] = Field(
        None, description="Rollover priority: 'ApplyFirst' or 'ApplyLast'"
    )
    rolloverPeriods: Optional[int] = Field(
        None, description="Number of rollover periods (max 3)"
    )
    rolloverPeriodLength: Optional[int] = Field(
        None, description="Rollover fund period length (shorter than validity period)"
    )

    # ============ Identification Fields ============
    description: Optional[str] = Field(
        None, description="Charge description (max 500 chars)"
    )
    productRatePlanChargeNumber: Optional[str] = Field(
        None, description="Natural key (max 100 chars). Auto-generated if null."
    )

    # ============ Attribute-based Pricing ============
    formula: Optional[str] = Field(
        None, description="Price lookup formula for Attribute-based Pricing"
    )
    chargeModelConfiguration: Optional[Dict[str, Any]] = Field(
        None,
        description="Container for charge model configuration (Multi-Attribute/Pre-Rated Pricing)",
    )
    deliverySchedule: Optional[Dict[str, Any]] = Field(
        None, description="Delivery schedule configuration (Delivery Pricing)"
    )

    # ============ Legacy fields for backward compatibility ============
    prepaidLoadAmount: Optional[float] = Field(
        None, description="Deprecated: use prepaidQuantity"
    )
    autoTopupThreshold: Optional[float] = None
    rolloverPct: Optional[float] = None
    rolloverCap: Optional[float] = None

    class Config:
        populate_by_name = True  # Allow both alias and field name


class RatePlan(BaseModel):
    """Product Rate Plan model matching Zuora v1 API schema.

    See: https://developer.zuora.com/v1-api-reference/api/operation/Object_POSTProductRatePlan/
    """

    # Required fields
    name: str = Field(..., description="Rate plan name (max 255 chars)")
    productId: Optional[str] = Field(
        None,
        description="Product ID (required for API, use @{Product.Id} for batch creation)",
    )

    # Optional fields
    description: Optional[str] = Field(
        None, description="Rate plan description (max 500 chars)"
    )
    activeCurrencies: Optional[List[str]] = Field(
        None,
        description="List of 3-letter currency codes (e.g., ['USD', 'EUR']). Max 5 currencies.",
    )
    effectiveStartDate: Optional[str] = Field(
        None, description="Date when rate plan becomes available (yyyy-mm-dd)"
    )
    effectiveEndDate: Optional[str] = Field(
        None, description="Date when rate plan expires (yyyy-mm-dd)"
    )
    externalIdSourceSystem: Optional[str] = Field(
        None, description="ID of external source system (requires WSDL version 130+)"
    )
    externalRatePlanIds: Optional[str] = Field(
        None,
        description="Comma-separated external IDs for imported rate plans (requires WSDL version 130+)",
    )
    grade: Optional[float] = Field(
        None,
        description="Grade for Grading catalog groups. Must be positive integer. Higher = higher grade.",
    )
    productRatePlanNumber: Optional[str] = Field(
        None,
        description="Natural key (max 100 chars). Auto-generated if null. Requires WSDL version 133+",
    )

    # Nested objects
    charges: List[Charge] = Field(
        default_factory=list, description="Charges for this rate plan"
    )


class Product(BaseModel):
    """Product model matching Zuora v1 API schema.

    See: https://developer.zuora.com/v1-api-reference/api/operation/Object_POSTProduct/
    """

    # Required fields
    name: str = Field(..., description="Product name (max 100 chars)")
    effectiveStartDate: str = Field(
        ..., description="Date when product becomes available (yyyy-mm-dd)"
    )
    effectiveEndDate: str = Field(
        ..., description="Date when product expires (yyyy-mm-dd)"
    )

    # Optional fields
    sku: Optional[str] = Field(None, description="Unique SKU (max 50 chars)")
    description: Optional[str] = Field(
        None, description="Product description (max 500 chars)"
    )
    allowFeatureChanges: Optional[bool] = Field(
        None,
        description="Allow users to add/remove features during subscription creation/amendment. Default: false",
    )
    category: Optional[ZUORA_PRODUCT_CATEGORY] = Field(
        None,
        description="Category for Zuora Quotes: 'Base Products', 'Add On Services', 'Miscellaneous Products'",
    )
    productNumber: Optional[str] = Field(
        None,
        description="Natural key of the product (max 100 chars). Auto-generated if null",
    )

    # Nested objects
    ratePlans: List[RatePlan] = Field(
        default_factory=list, description="Rate plans for this product"
    )


class ProductSpec(BaseModel):
    """
    The complete specification for creating a Product in Zuora.
    """

    product: Product
    comment: Optional[str] = "Generated by Zuora Seed Agent"


# ============ Chat API Models ============


class ZuoraApiType(str, Enum):
    """Zuora API types for v1 Catalog API."""

    # v1 Catalog API types
    PRODUCT = "product"
    PRODUCT_CREATE = "product_create"
    PRODUCT_RATE_PLAN = "product_rate_plan"
    RATE_PLAN_CREATE = "rate_plan_create"
    PRODUCT_RATE_PLAN_CHARGE = "product_rate_plan_charge"
    CHARGE_CREATE = "charge_create"
    PRODUCT_RATE_PLAN_CHARGE_TIER = "product_rate_plan_charge_tier"
    PRODUCT_UPDATE = "product_update"
    RATE_PLAN_UPDATE = "rate_plan_update"
    CHARGE_UPDATE = "charge_update"


class ZuoraApiPayload(BaseModel):
    """A single Zuora API payload with its type."""

    payload: Dict[str, Any] = Field(..., description="The actual payload data")
    zuora_api_type: ZuoraApiType = Field(
        ..., description="Type of Zuora API this payload is for"
    )
    payload_id: Optional[str] = Field(
        None, description="Optional ID to track this payload across requests"
    )


class Citation(BaseModel):
    """Citation from knowledge base (mocked for now)."""

    id: str = Field(..., description="Unique identifier for this citation")
    title: str = Field(..., description="Title of the source document")
    uri: Optional[str] = Field(None, description="S3 URI of the source")
    url: Optional[str] = Field(None, description="HTTPS URL for the source")


class ChatRequest(BaseModel):
    """Request model for POST /chat endpoint."""

    persona: str = Field(
        ..., description="User persona making the request (e.g., 'ProductManager')"
    )
    message: str = Field(..., description="User's message/question")
    conversation_id: Optional[str] = Field(
        None, description="Conversation ID for session continuity"
    )
    zuora_api_payloads: List[ZuoraApiPayload] = Field(
        default_factory=list,
        description="List of Zuora API payloads for the agent to work with",
    )


class ChatResponse(BaseModel):
    """Response model for POST /chat endpoint."""

    conversation_id: str = Field(..., description="Conversation ID (new or existing)")
    answer: str = Field(..., description="Agent's response message")
    citations: List[Citation] = Field(
        default_factory=list, description="Citations from knowledge base (mocked)"
    )
    zuora_api_payloads: List[ZuoraApiPayload] = Field(
        default_factory=list, description="Modified/created Zuora API payloads"
    )


# ============ Billing Architect Models ============


class PersonaType(str, Enum):
    """Available persona types."""

    PROJECT_MANAGER = "ProductManager"
    BILLING_ARCHITECT = "BillingArchitect"


class BillingArchitectApiType(str, Enum):
    """API types for Billing Architect persona (advisory payloads)."""

    WORKFLOW = "workflow"
    NOTIFICATION_RULE = "notification_rule"
    ORDER = "order"
    ACCOUNT_CUSTOM_FIELD = "account_custom_field"
    PREPAID_BALANCE_CONFIG = "prepaid_balance_config"
    PRODUCT_RATE_PLAN_CHARGE = "product_rate_plan_charge"


# ============ Workflow Models ============


class WorkflowTrigger(BaseModel):
    """Workflow trigger configuration."""

    type: Literal["Scheduled", "Callout", "Event"]
    schedule: Optional[str] = Field(
        None, description="Cron expression for scheduled triggers"
    )
    event_type: Optional[str] = Field(
        None, description="Event type for event triggers (e.g., UsageRecordCreation)"
    )


class WorkflowCondition(BaseModel):
    """Workflow condition for conditional execution."""

    field: str
    operator: Literal["equals", "notEquals", "greaterThan", "lessThan", "contains"]
    value: Any


class WorkflowTask(BaseModel):
    """Individual workflow task."""

    name: str
    type: Literal["API", "Condition", "Delay", "Iterate", "Custom"]
    api_endpoint: Optional[str] = None
    api_method: Optional[Literal["GET", "POST", "PUT", "DELETE"]] = None
    api_payload: Optional[Dict[str, Any]] = None
    delay_duration: Optional[str] = Field(
        None, description="ISO 8601 duration, e.g., P1D for 1 day"
    )
    condition: Optional[WorkflowCondition] = None


class WorkflowConfig(BaseModel):
    """Complete workflow configuration for advisory purposes."""

    name: str
    description: Optional[str] = None
    trigger: WorkflowTrigger
    tasks: List[WorkflowTask] = []
    active: bool = True
    timezone: str = "UTC"


# ============ Notification Models ============


class NotificationEventType(str, Enum):
    """Zuora notification event types."""

    USAGE_RECORD_CREATION = "UsageRecordCreation"
    PAYMENT_SUCCESS = "PaymentSuccess"
    PAYMENT_FAILURE = "PaymentFailure"
    INVOICE_POSTED = "InvoicePosted"
    SUBSCRIPTION_CREATED = "SubscriptionCreated"
    PREPAID_BALANCE_LOW = "PrepaidBalanceLow"
    PREPAID_BALANCE_DEPLETED = "PrepaidBalanceDepleted"
    ACCOUNT_CREATED = "AccountCreated"
    SUBSCRIPTION_CANCELLED = "SubscriptionCancelled"


class NotificationChannel(BaseModel):
    """Notification delivery channel."""

    type: Literal["Email", "Callout", "Webhook"]
    endpoint: Optional[str] = Field(None, description="URL for callout/webhook")
    email_template_id: Optional[str] = None
    recipients: Optional[List[str]] = None


class NotificationRule(BaseModel):
    """Notification rule configuration."""

    name: str
    description: Optional[str] = None
    event_type: str = Field(
        ..., description="Event type that triggers this notification"
    )
    active: bool = True
    channels: List[NotificationChannel] = []
    filter_conditions: Optional[Dict[str, Any]] = None


# ============ Orders API Models ============


class OrderActionType(str, Enum):
    """Zuora Orders API action types."""

    ADD_PRODUCT = "AddProduct"
    REMOVE_PRODUCT = "RemoveProduct"
    UPDATE_PRODUCT = "UpdateProduct"
    SUSPEND = "Suspend"
    RESUME = "Resume"
    OWNER_TRANSFER = "OwnerTransfer"


class OrderChargeOverride(BaseModel):
    """Charge override in an order action."""

    product_rate_plan_charge_id: Optional[str] = None
    price: Optional[float] = None
    quantity: Optional[float] = None
    effective_date: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None


class OrderAction(BaseModel):
    """Individual order action."""

    type: OrderActionType
    trigger_dates: Optional[Dict[str, str]] = Field(
        None, description="Trigger dates like contractEffective, serviceActivation"
    )
    add_product: Optional[Dict[str, Any]] = Field(None, description="Rate plan to add")
    remove_product: Optional[Dict[str, Any]] = Field(
        None, description="Rate plan to remove"
    )
    charge_overrides: Optional[List[OrderChargeOverride]] = None


class OrderConfig(BaseModel):
    """Complete order configuration for advisory purposes."""

    subscription_number: Optional[str] = Field(
        None, description="Existing subscription to modify"
    )
    account_id: Optional[str] = None
    order_date: str
    description: Optional[str] = None
    actions: List[OrderAction] = []
    processing_options: Optional[Dict[str, Any]] = None


# ============ Prepaid Balance Models ============


class PrepaidDrawdownConfig(BaseModel):
    """Prepaid with Drawdown charge configuration."""

    charge_name: str
    prepaid_uom: str = Field(
        ..., description="Unit of measure, e.g., API_CALL, SMS, Storage_GB"
    )
    prepaid_quantity: float
    prepaid_amount: float = Field(
        ..., description="Dollar amount for the prepaid charge"
    )
    validity_period_type: Literal[
        "SUBSCRIPTION_TERM", "ANNUAL", "MONTHLY", "CUSTOM"
    ] = "SUBSCRIPTION_TERM"
    custom_validity_days: Optional[int] = None
    rollover_enabled: bool = False
    rollover_percentage: Optional[float] = None
    rollover_cap: Optional[float] = None


class TopUpConfig(BaseModel):
    """Auto top-up configuration."""

    enabled: bool = True
    threshold_type: Literal["Percentage", "Absolute"] = "Percentage"
    threshold_value: float = Field(
        ..., description="e.g., 20 for 20% or 1000 for absolute units"
    )
    top_up_amount: Optional[float] = Field(None, description="If None, use fieldLookup")
    use_field_lookup: bool = False
    field_lookup_expression: Optional[str] = Field(
        None, description="e.g., fieldLookup('Account.TopUpAmount__c')"
    )


class PrepaidBalanceConfig(BaseModel):
    """Complete prepaid balance configuration."""

    product_name: str
    rate_plan_name: str
    drawdown_charge: PrepaidDrawdownConfig
    top_up_config: Optional[TopUpConfig] = None
    overage_handling: Literal["Block", "AllowOverage", "TopUp"] = "AllowOverage"
    overage_price_per_unit: Optional[float] = None


# ============ Account Custom Field Models ============


class CustomFieldDefinition(BaseModel):
    """Account custom field definition."""

    name: str = Field(..., description="API name, e.g., TopUpAmount__c")
    label: str = Field(..., description="Display label")
    type: Literal["Text", "Number", "Date", "Picklist", "Checkbox"]
    object_type: Literal["Account", "Subscription", "RatePlan", "Charge"] = "Account"
    description: Optional[str] = None
    required: bool = False
    default_value: Optional[Any] = None
    picklist_values: Optional[List[str]] = None


# ============ Multi-Attribute Pricing Models ============


class PriceAttribute(BaseModel):
    """Attribute for multi-attribute pricing."""

    name: str
    values: List[str]


class MultiAttributePricingConfig(BaseModel):
    """Multi-Attribute Pricing configuration."""

    charge_name: str
    pricing_attributes: List[PriceAttribute]
    price_matrix: Dict[str, float] = Field(
        ..., description="Key format: 'attr1:value1|attr2:value2' -> price"
    )
    use_field_lookup: bool = False
    field_lookup_attribute: Optional[str] = None


# ============ Advisory Payload Container ============


class AdvisoryPayload(BaseModel):
    """Container for advisory payloads (not executed)."""

    payload: Dict[str, Any]
    api_type: BillingArchitectApiType
    api_endpoint: str = Field(..., description="Zuora API endpoint this would target")
    http_method: Literal["GET", "POST", "PUT", "DELETE"] = "POST"
    payload_id: Optional[str] = None
    notes: Optional[str] = Field(None, description="Implementation notes for the user")
    prerequisites: Optional[List[str]] = Field(
        None, description="Steps to complete before this"
    )
