from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal, Union
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


# Zuora v1 API ChargeModel enum values (exact strings from API)
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

# Zuora v1 API ChargeType enum values
ZUORA_CHARGE_TYPES = Literal["OneTime", "Recurring", "Usage"]

# Zuora v1 API BillingPeriod enum values
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

# Zuora v1 API BillCycleType enum values
ZUORA_BILL_CYCLE_TYPES = Literal[
    "DefaultFromCustomer",
    "SpecificDayofMonth",
    "SubscriptionStartDay",
    "ChargeTriggerDay",
    "SpecificDayofWeek",
    "TermStartDay",
    "TermEndDay",
]

# Zuora v1 API TriggerEvent enum values
ZUORA_TRIGGER_EVENTS = Literal[
    "ContractEffective",
    "ServiceActivation",
    "CustomerAcceptance",
]

# Zuora v1 API BillingTiming enum values
ZUORA_BILLING_TIMING = Literal["In Advance", "In Arrears"]

# Zuora v1 API RatingGroup enum values
# Specifies how usage records are aggregated for rating in tiered/volume pricing
ZUORA_RATING_GROUP = Literal[
    "ByBillingPeriod",  # Rating based on all usages in a billing period (default)
    "ByUsageStartDate",  # Rating based on all usages on the same usage start date
    "ByUsageRecord",  # Rating based on each individual usage record
    "ByUsageUpload",  # Rating based on all usages in an uploaded file
    "ByGroupId",  # Rating based on custom group (requires Active Rating feature)
]


class Charge(BaseModel):
    """Product Rate Plan Charge model matching Zuora v1 API schema."""

    name: str
    type: ZUORA_CHARGE_TYPES = Field(
        ..., alias="chargeType", description="Charge type: OneTime, Recurring, or Usage"
    )
    model: ZUORA_CHARGE_MODELS = Field(
        ..., alias="chargeModel", description="Pricing model per Zuora API"
    )
    billingPeriod: Optional[ZUORA_BILLING_PERIODS] = Field(
        None, description="Billing period for recurring charges"
    )
    billingTiming: Optional[ZUORA_BILLING_TIMING] = Field(
        "In Advance", description="Bill in advance or arrears"
    )
    billCycleType: ZUORA_BILL_CYCLE_TYPES = Field(
        "DefaultFromCustomer", description="How to determine billing day"
    )
    triggerEvent: ZUORA_TRIGGER_EVENTS = Field(
        "ContractEffective", description="When to start billing"
    )
    uom: Optional[str] = Field(
        None, description="Unit of measure for usage/per-unit charges"
    )
    price: Optional[float] = Field(
        None, description="Price for flat fee or per unit models"
    )
    currency: str = Field("USD", description="Currency code")
    includedUnits: Optional[float] = Field(
        None,
        description="Units included before overage pricing kicks in (for Overage/Tiered with Overage)",
    )
    overagePrice: Optional[float] = Field(
        None,
        description="Price per unit after included units are consumed (for Overage/Tiered with Overage)",
    )
    tiers: Optional[List[Tier]] = Field(
        None, description="Pricing tiers for tiered/volume models"
    )
    defaultQuantity: Optional[float] = Field(
        None, description="Default quantity of units"
    )
    # PWD (Prepaid with Drawdown) specific fields
    prepaidQuantity: Optional[float] = Field(
        None, description="Units included in prepaid"
    )
    prepaidUom: Optional[str] = Field(
        None, description="Unit of measure for prepaid balance"
    )
    validityPeriodType: Optional[str] = Field(
        None, description="SUBSCRIPTION_TERM, ANNUAL, SEMI_ANNUAL, QUARTER, MONTH"
    )
    # Rollover fields
    isRollover: Optional[bool] = Field(None, description="Enable rollover for prepaid")
    rolloverPeriods: Optional[int] = Field(
        None, description="Number of rollover periods (max 3)"
    )
    # Legacy fields for backward compatibility
    prepaidLoadAmount: Optional[float] = Field(
        None, description="Deprecated: use prepaidQuantity"
    )
    autoTopupThreshold: Optional[float] = None
    rolloverPct: Optional[float] = None
    rolloverCap: Optional[float] = None

    class Config:
        populate_by_name = True  # Allow both alias and field name


class RatePlan(BaseModel):
    name: str
    description: Optional[str] = None
    charges: List[Charge] = []


class Product(BaseModel):
    name: str
    sku: str
    description: Optional[str] = None
    effectiveStartDate: str
    effectiveEndDate: Optional[str] = None
    ratePlans: List[RatePlan] = []


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
