"""
Zuora API Client with OAuth authentication.
Handles product catalog queries and updates via v1 Catalog API.
"""

import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, Dict, Any, List
from .config import (
    ZUORA_CLIENT_ID,
    ZUORA_CLIENT_SECRET,
    ZUORA_ENV,
    ZUORA_API_CACHE_ENABLED,
    ZUORA_API_RETRY_ATTEMPTS,
    ZUORA_API_RETRY_BACKOFF_FACTOR,
    ZUORA_API_CONNECTION_POOL_SIZE,
    ZUORA_API_REQUEST_TIMEOUT,
    ZUORA_OAUTH_TIMEOUT,
)
from .cache import get_cache
from .observability import get_tracer, get_metrics_collector, trace_function


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

        # Observability and caching
        self.cache = get_cache() if ZUORA_API_CACHE_ENABLED else None
        self.tracer = get_tracer()
        self.metrics = get_metrics_collector()

        # HTTP session with connection pooling and retry logic
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create HTTP session with connection pooling and retry logic."""
        session = requests.Session()

        # Retry strategy: exponential backoff for transient failures
        retry_strategy = Retry(
            total=ZUORA_API_RETRY_ATTEMPTS,
            backoff_factor=ZUORA_API_RETRY_BACKOFF_FACTOR,  # type: ignore[arg-type]
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT"],
            raise_on_status=False,
        )

        # Mount adapter with connection pooling
        adapter = HTTPAdapter(
            pool_connections=ZUORA_API_CONNECTION_POOL_SIZE,
            pool_maxsize=ZUORA_API_CONNECTION_POOL_SIZE,
            max_retries=retry_strategy,
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    @property
    def is_configured(self) -> bool:
        """Check if credentials are configured."""
        return bool(self.client_id and self.client_secret)

    @property
    def is_authenticated(self) -> bool:
        """Check if we have a valid token."""
        return self._access_token is not None and time.time() < self._token_expires_at

    @trace_function(
        span_name="zuora.oauth.authenticate", attributes={"component": "oauth"}
    )
    def authenticate(self) -> Dict[str, Any]:
        """
        Authenticate with Zuora OAuth and obtain access token.

        Returns:
            dict with 'success', 'message', and optionally 'tenant' info
        """
        if not self.is_configured:
            return {
                "success": False,
                "message": "Zuora credentials not configured. Please set ZUORA_CLIENT_ID and ZUORA_CLIENT_SECRET.",
            }

        # Check cache for existing token
        if self.cache:
            cached_token_data = self.cache.get("oauth", "/token")
            if cached_token_data:
                self._access_token = cached_token_data.get("access_token")
                self._token_expires_at = cached_token_data.get("expires_at", 0)
                self.metrics.record_cache_hit("oauth")
                return {
                    "success": True,
                    "message": f"Connected to Zuora {self.env.upper()} environment (cached).",
                    "environment": self.env,
                    "base_url": self.base_url,
                }
            self.metrics.record_cache_miss("oauth")

        start_time = time.time()
        try:
            response = self.session.post(
                f"{self.base_url}/oauth/token",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
                timeout=ZUORA_OAUTH_TIMEOUT,
            )

            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                data = response.json()
                self._access_token = data.get("access_token")
                # Token expires in ~1 hour, refresh 5 minutes early
                expires_in = data.get("expires_in", 3600)
                self._token_expires_at = time.time() + expires_in - 300

                # Cache the token
                if self.cache:
                    token_data = {
                        "access_token": self._access_token,
                        "expires_at": self._token_expires_at,
                    }
                    # Cache with TTL matching token expiry
                    self.cache.set("oauth", "/token", token_data, ttl=expires_in - 300)

                self.metrics.record_api_call("POST", "/oauth/token", duration_ms, True)

                return {
                    "success": True,
                    "message": f"Connected to Zuora {self.env.upper()} environment.",
                    "environment": self.env,
                    "base_url": self.base_url,
                }
            else:
                error_msg = (
                    response.json().get("message", response.text)
                    if response.text
                    else f"HTTP {response.status_code}"
                )
                self.metrics.record_api_call("POST", "/oauth/token", duration_ms, False)
                self.metrics.record_api_error(
                    "POST", "/oauth/token", f"http_{response.status_code}"
                )
                return {
                    "success": False,
                    "message": f"Authentication failed: {error_msg}",
                }

        except requests.RequestException as e:
            duration_ms = (time.time() - start_time) * 1000
            self.metrics.record_api_call("POST", "/oauth/token", duration_ms, False)
            self.metrics.record_api_error("POST", "/oauth/token", type(e).__name__)
            return {"success": False, "message": f"Connection error: {str(e)}"}

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
        params: Optional[Dict] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Make an authenticated request to Zuora API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., "/v1/catalog/products")
            data: Request body for POST/PUT
            params: Query parameters
            use_cache: Whether to use caching for this request (default: True)

        Returns:
            API response as dict, or error dict
        """
        with self.tracer.start_as_current_span("zuora.api.request") as span:
            span.set_attribute("http.method", method)
            span.set_attribute("http.url", endpoint)
            span.set_attribute("zuora.env", self.env)

            # Try cache for GET requests
            if use_cache and self.cache and method == "GET":
                cached_response = self.cache.get(method, endpoint, params, data)
                if cached_response:
                    span.set_attribute("cache.hit", True)
                    self.metrics.record_cache_hit(f"api:{method}")
                    return cached_response
                span.set_attribute("cache.hit", False)
                self.metrics.record_cache_miss(f"api:{method}")

            if not self._ensure_authenticated():
                span.set_attribute("error", True)
                return {"success": False, "error": "Not authenticated"}

            url = f"{self.base_url}{endpoint}"
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            start_time = time.time()
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data,
                    params=params,
                    timeout=ZUORA_API_REQUEST_TIMEOUT,
                )

                duration_ms = (time.time() - start_time) * 1000
                span.set_attribute("http.status_code", response.status_code)
                span.set_attribute("duration_ms", duration_ms)

                if response.status_code in (200, 201):
                    result = {"success": True, "data": response.json()}

                    # Cache successful GET responses
                    if use_cache and self.cache and method == "GET":
                        self.cache.set(method, endpoint, result, params, data)

                    self.metrics.record_api_call(method, endpoint, duration_ms, True)
                    return result
                else:
                    error_data = response.json() if response.text else {}
                    result = {
                        "success": False,
                        "error": error_data.get(
                            "message", f"HTTP {response.status_code}"
                        ),
                        "details": error_data,
                    }

                    span.set_attribute("error", True)
                    self.metrics.record_api_call(method, endpoint, duration_ms, False)
                    self.metrics.record_api_error(
                        method, endpoint, f"http_{response.status_code}"
                    )

                    return result

            except requests.RequestException as e:
                duration_ms = (time.time() - start_time) * 1000
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.record_exception(e)

                self.metrics.record_api_call(method, endpoint, duration_ms, False)
                self.metrics.record_api_error(method, endpoint, type(e).__name__)

                return {"success": False, "error": str(e)}

    # =========================================================================
    # Product Operations
    # =========================================================================

    @trace_function(span_name="zuora.products.query", attributes={"operation": "query"})
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

    @trace_function(span_name="zuora.products.list", attributes={"operation": "list"})
    def list_all_products(self, page_size: int = 50) -> Dict[str, Any]:
        """
        List all products in the catalog.

        Args:
            page_size: Number of products per page

        Returns:
            List of products with pagination info
        """
        return self._request(
            "GET", "/v1/catalog/products", params={"pageSize": page_size}
        )

    @trace_function(span_name="zuora.products.get", attributes={"operation": "get"})
    def get_product(self, product_key: str) -> Dict[str, Any]:
        """
        Get a product by ID or key.

        Args:
            product_key: Product ID or unique key

        Returns:
            Product details or error
        """
        return self._request("GET", f"/v1/catalog/products/{product_key}")

    @trace_function(
        span_name="zuora.products.get_by_name", attributes={"operation": "search"}
    )
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
            "POST", "/v1/catalog/query/products", data={"name": name}
        )
        return result

    @trace_function(
        span_name="zuora.products.update", attributes={"operation": "update"}
    )
    def update_product(
        self, product_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update a product's attributes.

        Args:
            product_id: Product ID
            updates: Fields to update (name, sku, description, effectiveStartDate, effectiveEndDate)

        Returns:
            Updated product or error
        """
        result = self._request(
            "PUT", f"/v1/object/product/{product_id}", data=updates, use_cache=False
        )

        # Invalidate cache for this product and list
        if result.get("success") and self.cache:
            self.cache.invalidate("GET", f"/v1/catalog/products/{product_id}")
            self.cache.invalidate("GET", "/v1/catalog/products")

        return result

    # =========================================================================
    # Rate Plan Operations
    # =========================================================================

    @trace_function(span_name="zuora.rate_plans.list", attributes={"operation": "list"})
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
            return {"success": True, "data": product.get("productRatePlans", [])}
        return product_result

    @trace_function(span_name="zuora.rate_plans.get", attributes={"operation": "get"})
    def get_rate_plan(self, rate_plan_id: str) -> Dict[str, Any]:
        """
        Get a specific rate plan by ID.

        Args:
            rate_plan_id: Rate plan ID

        Returns:
            Rate plan details or error
        """
        return self._request("GET", f"/v1/catalog/product-rate-plans/{rate_plan_id}")

    @trace_function(
        span_name="zuora.rate_plans.update", attributes={"operation": "update"}
    )
    def update_rate_plan(
        self, rate_plan_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update a rate plan's attributes.

        Args:
            rate_plan_id: Rate plan ID
            updates: Fields to update (name, description, effectiveStartDate, effectiveEndDate)

        Returns:
            Updated rate plan or error
        """
        result = self._request(
            "PUT",
            f"/v1/object/product-rate-plan/{rate_plan_id}",
            data=updates,
            use_cache=False,
        )

        # Invalidate cache for this rate plan
        if result.get("success") and self.cache:
            self.cache.invalidate(
                "GET", f"/v1/catalog/product-rate-plans/{rate_plan_id}"
            )

        return result

    # =========================================================================
    # Charge Operations
    # =========================================================================

    @trace_function(span_name="zuora.charges.list", attributes={"operation": "list"})
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
                "data": rate_plan.get("productRatePlanCharges", []),
            }
        return rate_plan_result

    @trace_function(span_name="zuora.charges.get", attributes={"operation": "get"})
    def get_charge(self, charge_id: str) -> Dict[str, Any]:
        """
        Get a specific charge by ID.

        Args:
            charge_id: Charge ID

        Returns:
            Charge details or error
        """
        return self._request(
            "GET", f"/v1/catalog/product-rate-plan-charges/{charge_id}"
        )

    @trace_function(
        span_name="zuora.charges.update", attributes={"operation": "update"}
    )
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
        result = self._request(
            "PUT",
            f"/v1/object/product-rate-plan-charge/{charge_id}",
            data=updates,
            use_cache=False,
        )

        # Invalidate cache for this charge
        if result.get("success") and self.cache:
            self.cache.invalidate(
                "GET", f"/v1/catalog/product-rate-plan-charges/{charge_id}"
            )

        return result

    # =========================================================================
    # Utility Methods
    # =========================================================================

    @trace_function(
        span_name="zuora.connection.check", attributes={"operation": "check"}
    )
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
                "message": f"Connected to Zuora {self.env.upper()}",
            }

        auth_result = self.authenticate()
        return {
            "connected": auth_result.get("success", False),
            "environment": self.env,
            "base_url": self.base_url,
            "message": auth_result.get("message", "Unknown error"),
        }

    @trace_function(
        span_name="zuora.settings.batch", attributes={"operation": "settings"}
    )
    def get_settings_batch(
        self, requests: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Fetch multiple settings in a single batch request.

        Args:
            requests: List of settings requests, each with 'id', 'method', 'url'.
                      If None, fetches default environment settings.

        Returns:
            Batch response with all settings
        """
        if requests is None:
            requests = [
                {"id": "1", "method": "GET", "url": "/billing-rules"},
                {"id": "2", "method": "GET", "url": "/accounting-rules"},
                {"id": "3", "method": "GET", "url": "/currencies"},
                {"id": "4", "method": "GET", "url": "/chart-of-accounts"},
                {"id": "5", "method": "GET", "url": "/product-attributes"},
                {"id": "6", "method": "GET", "url": "/charge-models"},
                {"id": "7", "method": "GET", "url": "/billing-cycle-types"},
                {"id": "8", "method": "GET", "url": "/billing-list-price-bases"},
                {"id": "9", "method": "GET", "url": "/billing-period-starts"},
                {"id": "10", "method": "GET", "url": "/billing-periods"},
                {"id": "11", "method": "GET", "url": "/custom-object-namespaces"},
                {"id": "12", "method": "GET", "url": "/discount-settings"},
                {"id": "13", "method": "GET", "url": "/numbers-and-skus"},
                {"id": "14", "method": "GET", "url": "/security-policies"},
                {"id": "15", "method": "GET", "url": "/subscription-settings"},
                {"id": "16", "method": "GET", "url": "/units-of-measure"},
            ]

        return self._request(
            "POST", "/settings/batch-requests", data={"requests": requests}
        )


# Global client instance
_client: Optional[ZuoraClient] = None


def get_zuora_client() -> ZuoraClient:
    """Get or create the global Zuora client instance."""
    global _client
    if _client is None:
        _client = ZuoraClient()
    return _client
