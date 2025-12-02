"""
Zuora API Client with OAuth authentication.
Handles product catalog queries and updates via Commerce APIs.
"""
import time
import requests
from typing import Optional, Dict, Any, List
from .config import ZUORA_CLIENT_ID, ZUORA_CLIENT_SECRET, ZUORA_ENV


# Base URLs by environment
ZUORA_BASE_URLS = {
    "sandbox": "https://rest.apisandbox.zuora.com",
    "apisandbox": "https://rest.apisandbox.zuora.com",  # alias for sandbox
    "test": "https://rest.test.zuora.com",
    "production": "https://rest.na.zuora.com",
    "eu-sandbox": "https://rest.sandbox.eu.zuora.com",
    "eu-production": "https://rest.eu.zuora.com",
}


class ZuoraClient:
    """
    Zuora API client with OAuth 2.0 authentication.

    Handles:
    - OAuth token acquisition and automatic refresh
    - Product catalog queries
    - Product, rate plan, and charge updates
    """

    def __init__(self):
        self.client_id = ZUORA_CLIENT_ID
        self.client_secret = ZUORA_CLIENT_SECRET
        self.env = ZUORA_ENV or "sandbox"
        self.base_url = ZUORA_BASE_URLS.get(self.env, ZUORA_BASE_URLS["sandbox"])

        # Token management
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

    @property
    def is_configured(self) -> bool:
        """Check if credentials are configured."""
        return bool(self.client_id and self.client_secret)

    @property
    def is_authenticated(self) -> bool:
        """Check if we have a valid token."""
        return self._access_token is not None and time.time() < self._token_expires_at

    def authenticate(self) -> Dict[str, Any]:
        """
        Authenticate with Zuora OAuth and obtain access token.

        Returns:
            dict with 'success', 'message', and optionally 'tenant' info
        """
        if not self.is_configured:
            return {
                "success": False,
                "message": "Zuora credentials not configured. Please set ZUORA_CLIENT_ID and ZUORA_CLIENT_SECRET."
            }

        try:
            response = requests.post(
                f"{self.base_url}/oauth/token",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json"
                },
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials"
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                self._access_token = data.get("access_token")
                # Token expires in ~1 hour, refresh 5 minutes early
                expires_in = data.get("expires_in", 3600)
                self._token_expires_at = time.time() + expires_in - 300

                return {
                    "success": True,
                    "message": f"Connected to Zuora {self.env.upper()} environment.",
                    "environment": self.env,
                    "base_url": self.base_url
                }
            else:
                error_msg = response.json().get("message", response.text)
                return {
                    "success": False,
                    "message": f"Authentication failed: {error_msg}"
                }

        except requests.RequestException as e:
            return {
                "success": False,
                "message": f"Connection error: {str(e)}"
            }

    def _ensure_authenticated(self) -> bool:
        """Ensure we have a valid token, refreshing if needed."""
        if not self.is_authenticated:
            result = self.authenticate()
            return result.get("success", False)
        return True

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make an authenticated request to Zuora API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., "/v1/catalog/products")
            data: Request body for POST/PUT
            params: Query parameters

        Returns:
            API response as dict, or error dict
        """
        if not self._ensure_authenticated():
            return {"success": False, "error": "Not authenticated"}

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params,
                timeout=60
            )

            if response.status_code in (200, 201):
                return {"success": True, "data": response.json()}
            else:
                error_data = response.json() if response.text else {}
                return {
                    "success": False,
                    "error": error_data.get("message", f"HTTP {response.status_code}"),
                    "details": error_data
                }

        except requests.RequestException as e:
            return {"success": False, "error": str(e)}

    # =========================================================================
    # Product Operations
    # =========================================================================

    def query_products(self, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Query products from the product catalog.

        Args:
            filters: Optional filter criteria

        Returns:
            List of products or error
        """
        query_data = filters or {}
        return self._request("POST", "/v1/catalog/query/products", data=query_data)

    def list_all_products(self, page_size: int = 50) -> Dict[str, Any]:
        """
        List all products in the catalog.

        Args:
            page_size: Number of products per page

        Returns:
            List of products with pagination info
        """
        return self._request("GET", "/v1/catalog/products", params={"pageSize": page_size})

    def get_product(self, product_key: str) -> Dict[str, Any]:
        """
        Get a product by ID or key.

        Args:
            product_key: Product ID or unique key

        Returns:
            Product details or error
        """
        return self._request("GET", f"/v1/catalog/products/{product_key}")

    def get_product_by_name(self, name: str) -> Dict[str, Any]:
        """
        Search for a product by name.

        Args:
            name: Product name to search for

        Returns:
            Matching products or error
        """
        # Use query endpoint with name filter
        result = self._request(
            "POST",
            "/v1/catalog/query/products",
            data={"name": name}
        )
        return result

    def update_product(self, product_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update a product's attributes.

        Args:
            product_id: Product ID
            updates: Fields to update (name, sku, description, effectiveStartDate, effectiveEndDate)

        Returns:
            Updated product or error
        """
        return self._request("PUT", f"/v1/catalog/products/{product_id}", data=updates)

    # =========================================================================
    # Rate Plan Operations
    # =========================================================================

    def get_rate_plans(self, product_id: str) -> Dict[str, Any]:
        """
        Get rate plans for a product.

        Args:
            product_id: Product ID

        Returns:
            List of rate plans or error
        """
        # Rate plans are typically included in product response
        product_result = self.get_product(product_id)
        if product_result.get("success"):
            product = product_result.get("data", {})
            return {
                "success": True,
                "data": product.get("productRatePlans", [])
            }
        return product_result

    def get_rate_plan(self, rate_plan_id: str) -> Dict[str, Any]:
        """
        Get a specific rate plan by ID.

        Args:
            rate_plan_id: Rate plan ID

        Returns:
            Rate plan details or error
        """
        return self._request("GET", f"/v1/catalog/product-rate-plans/{rate_plan_id}")

    def update_rate_plan(self, rate_plan_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update a rate plan's attributes.

        Args:
            rate_plan_id: Rate plan ID
            updates: Fields to update (name, description, effectiveStartDate, effectiveEndDate)

        Returns:
            Updated rate plan or error
        """
        return self._request("PUT", f"/v1/catalog/product-rate-plans/{rate_plan_id}", data=updates)

    # =========================================================================
    # Charge Operations
    # =========================================================================

    def get_charges(self, rate_plan_id: str) -> Dict[str, Any]:
        """
        Get charges for a rate plan.

        Args:
            rate_plan_id: Rate plan ID

        Returns:
            List of charges or error
        """
        rate_plan_result = self.get_rate_plan(rate_plan_id)
        if rate_plan_result.get("success"):
            rate_plan = rate_plan_result.get("data", {})
            return {
                "success": True,
                "data": rate_plan.get("productRatePlanCharges", [])
            }
        return rate_plan_result

    def get_charge(self, charge_id: str) -> Dict[str, Any]:
        """
        Get a specific charge by ID.

        Args:
            charge_id: Charge ID

        Returns:
            Charge details or error
        """
        return self._request("GET", f"/v1/catalog/product-rate-plan-charges/{charge_id}")

    def update_charge(self, charge_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update a charge's attributes.

        Note: Charge model/type cannot be changed if used in existing subscriptions.

        Args:
            charge_id: Charge ID
            updates: Fields to update (name, description, pricing, triggerEvent, etc.)

        Returns:
            Updated charge or error
        """
        return self._request("PUT", f"/v1/catalog/product-rate-plan-charges/{charge_id}", data=updates)

    # =========================================================================
    # Commerce API - Product Operations (Nested Creation Support)
    # =========================================================================

    def commerce_create_product(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create product with nested rate plans and charges via Commerce API.

        POST /commerce/products

        Supports nested structure with @{Reference.Id} placeholders:
        {
            "name": "Product Name",
            "sku": "SKU-001",
            "productRatePlans": [
                {
                    "name": "Plan 1",
                    "productRatePlanCharges": [
                        {"name": "Charge 1", "type": "Recurring", ...}
                    ]
                }
            ]
        }

        Args:
            product_data: Complete product structure with nested rate plans and charges

        Returns:
            Created product with IDs for all nested objects or error
        """
        return self._request("POST", "/commerce/products", data=product_data)

    def commerce_update_product(self, product_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update product via Commerce API.

        Args:
            product_id: Product ID
            updates: Fields to update

        Returns:
            Updated product or error
        """
        return self._request("PUT", f"/commerce/products/{product_id}", data=updates)

    def commerce_query_products(self, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Query products via Commerce API.

        Args:
            filters: Optional filter criteria

        Returns:
            List of products or error
        """
        return self._request("POST", "/commerce/products/query", data=filters or {})

    # =========================================================================
    # Commerce API - Rate Plan Operations
    # =========================================================================

    def commerce_create_rate_plan(
        self,
        product_id: str,
        rate_plan_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create rate plan via Commerce API.

        Args:
            product_id: Parent product ID
            rate_plan_data: Rate plan configuration

        Returns:
            Created rate plan or error
        """
        rate_plan_data["productId"] = product_id
        return self._request("POST", "/commerce/product-rate-plans", data=rate_plan_data)

    def commerce_update_rate_plan(
        self,
        rate_plan_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update rate plan via Commerce API.

        Args:
            rate_plan_id: Rate plan ID
            updates: Fields to update

        Returns:
            Updated rate plan or error
        """
        return self._request("PUT", f"/commerce/product-rate-plans/{rate_plan_id}", data=updates)

    def commerce_query_rate_plans(
        self,
        product_id: Optional[str] = None,
        filters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Query rate plans via Commerce API.

        Args:
            product_id: Optional product ID to filter by
            filters: Optional additional filter criteria

        Returns:
            List of rate plans or error
        """
        query_data = filters or {}
        if product_id:
            query_data["productId"] = product_id
        return self._request("POST", "/commerce/product-rate-plans/query", data=query_data)

    # =========================================================================
    # Commerce API - Charge Operations with Dynamic Pricing
    # =========================================================================

    def commerce_create_charge(
        self,
        rate_plan_id: str,
        charge_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create charge via Commerce API.

        Args:
            rate_plan_id: Parent rate plan ID
            charge_data: Charge configuration

        Returns:
            Created charge or error
        """
        charge_data["productRatePlanId"] = rate_plan_id
        return self._request("POST", "/commerce/product-rate-plan-charges", data=charge_data)

    def commerce_create_charge_with_dynamic_pricing(
        self,
        rate_plan_id: str,
        charge_data: Dict[str, Any],
        dynamic_pricing_config: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Create charge with Dynamic Pricing via Commerce API.

        Dynamic Pricing supports:
        - fieldLookup() expressions for customer-specific pricing
        - Attribute-based pricing matrices
        - Formula-based pricing

        Args:
            rate_plan_id: Parent rate plan ID
            charge_data: Base charge configuration
            dynamic_pricing_config: Dynamic pricing configuration with:
                - pricingType: "Static", "Dynamic", or "Formula"
                - formula: fieldLookup expression, e.g., "fieldLookup('Account.Price__c')"
                - defaultPrice: Fallback price when dynamic lookup fails
                - attributes: Attribute-based pricing matrix

        Returns:
            Created charge with dynamic pricing or error
        """
        charge_data["productRatePlanId"] = rate_plan_id
        if dynamic_pricing_config:
            charge_data["dynamicPricing"] = dynamic_pricing_config
        return self._request("POST", "/commerce/product-rate-plan-charges", data=charge_data)

    def commerce_update_charge(
        self,
        charge_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update charge via Commerce API.

        Args:
            charge_id: Charge ID
            updates: Fields to update

        Returns:
            Updated charge or error
        """
        return self._request("PUT", f"/commerce/product-rate-plan-charges/{charge_id}", data=updates)

    def commerce_query_charges(
        self,
        rate_plan_id: Optional[str] = None,
        filters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Query charges via Commerce API.

        Args:
            rate_plan_id: Optional rate plan ID to filter by
            filters: Optional additional filter criteria

        Returns:
            List of charges or error
        """
        query_data = filters or {}
        if rate_plan_id:
            query_data["productRatePlanId"] = rate_plan_id
        return self._request("POST", "/commerce/product-rate-plan-charges/query", data=query_data)

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def check_connection(self) -> Dict[str, Any]:
        """
        Check connection status and authenticate if needed.

        Returns:
            Connection status with environment info
        """
        if self.is_authenticated:
            return {
                "connected": True,
                "environment": self.env,
                "base_url": self.base_url,
                "message": f"Connected to Zuora {self.env.upper()}"
            }

        auth_result = self.authenticate()
        return {
            "connected": auth_result.get("success", False),
            "environment": self.env,
            "base_url": self.base_url,
            "message": auth_result.get("message", "Unknown error")
        }


# Global client instance
_client: Optional[ZuoraClient] = None


def get_zuora_client() -> ZuoraClient:
    """Get or create the global Zuora client instance."""
    global _client
    if _client is None:
        _client = ZuoraClient()
    return _client
