// ===============================
// index.mjs – SIMPLIFIED PASSTHROUGH VERSION
// Supports:
// 1) Legacy body.product / ratePlan / ratePlanCharge (passthrough)
// 2) Generic zuora_api_payloads[] executor
// ===============================

// ===============================
// ZUORA AUTH
// ===============================
async function getZuoraToken(clientId, clientSecret) {
  console.log("Getting Zuora OAuth token...");

  const oauthUrl = process.env.ZUORA_OAUTH_URL;

  const res = await fetch(oauthUrl, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "client_credentials",
      client_id: clientId,
      client_secret: clientSecret,
    }),
  });

  const text = await res.text();

  if (!res.ok) {
    throw {
      statusCode: res.status === 401 ? 401 : 400,
      message: `Zuora OAuth failed: ${text}`,
    };
  }

  return JSON.parse(text).access_token;
}

// ===============================
// ZUORA HELPERS
// ===============================

// Legacy POST helper for /v1/object/* calls
async function zuoraPost(baseUrl, token, path, body) {
  console.log(`\n=== Calling Zuora (POST): ${path} ===`);
  console.log("Payload:", JSON.stringify(body, null, 2));

  const res = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      "X-Zuora-WSDL-Version": "141",
    },
    body: JSON.stringify(body),
  });

  const text = await res.text();
  console.log(`Zuora Response for ${path}:`, text);

  let json;
  try {
    json = JSON.parse(text);
  } catch {
    throw {
      statusCode: 500,
      message: `Non-JSON response from Zuora: ${text}`,
    };
  }

  // Zuora errors return success=false & 'reasons'
  if (!res.ok || json.Success === false) {
    const reason =
      json.reasons?.[0]?.message ||
      json.reasons?.[0]?.details ||
      text ||
      "Zuora operation failed";

    let statusCode = res.status || 500;

    if (reason.toLowerCase().includes("not found")) statusCode = 404;
    if (reason.toLowerCase().includes("invalid")) statusCode = 422;
    if (reason.toLowerCase().includes("authentication")) statusCode = 401;

    throw {
      statusCode,
      message: `Zuora Error: ${reason}`,
    };
  }

  return json;
}

// Generic request helper for zuora_api_payloads
async function zuoraRequest(baseUrl, token, method, endpoint, body) {
  const m = (method || "GET").toUpperCase();
  const path = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;

  console.log(`\n=== Calling Zuora [${m}] ${path} ===`);
  if (body) {
    console.log("Payload:", JSON.stringify(body, null, 2));
  }

  const fetchOptions = {
    method: m,
    headers: {
      Authorization: `Bearer ${token}`,
      "X-Zuora-WSDL-Version": "141",
    },
  };

  if (body && m !== "GET" && m !== "DELETE") {
    fetchOptions.headers["Content-Type"] = "application/json";
    fetchOptions.body = JSON.stringify(body);
  }

  const res = await fetch(`${baseUrl}${path}`, fetchOptions);

  const text = await res.text();
  console.log(`Zuora Response for [${m}] ${path}:`, text);

  if (!text) {
    // 204 or empty response
    if (!res.ok) {
      throw {
        statusCode: res.status || 500,
        message: `Zuora Error (empty response), status=${res.status}`,
      };
    }
    return { Success: true, status: res.status };
  }

  let json;
  try {
    json = JSON.parse(text);
  } catch {
    // Non-JSON but maybe still meaningful error
    if (!res.ok) {
      throw {
        statusCode: res.status || 500,
        message: `Non-JSON response from Zuora: ${text}`,
      };
    }
    return { raw: text, status: res.status, Success: res.ok };
  }

  const successFlag =
    json.success === true ||
    json.Success === true ||
    (res.ok && json.reasons == null);

  if (!res.ok || !successFlag) {
    const reason =
      json.reasons?.[0]?.message ||
      json.reasons?.[0]?.details ||
      json.message ||
      text ||
      "Zuora operation failed";

    let statusCode = res.status || 500;

    if (reason.toLowerCase().includes("not found")) statusCode = 404;
    if (reason.toLowerCase().includes("invalid")) statusCode = 422;
    if (reason.toLowerCase().includes("authentication")) statusCode = 401;

    throw {
      statusCode,
      message: `Zuora Error: ${reason}`,
      raw: json,
    };
  }

  return json;
}

// ===============================
// DELETE HELPER FOR ROLLBACK
// ===============================
async function zuoraDelete(baseUrl, token, objectType, id) {
  const path = `/v1/object/${objectType}/${id}`;
  console.log(`\n=== Deleting Zuora object: ${path} ===`);

  const res = await fetch(`${baseUrl}${path}`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`,
      "X-Zuora-WSDL-Version": "141",
    },
  });

  const text = await res.text();
  console.log(`Zuora Delete Response for ${path}:`, text);

  if (!res.ok) {
    console.error(`Failed to delete ${objectType}/${id}: ${text}`);
    return { success: false, error: text };
  }

  let json = {};
  try {
    json = JSON.parse(text);
  } catch {
    // Empty or non-JSON response is fine for DELETE
  }

  return { success: true, response: json };
}

// ===============================
// ROLLBACK HELPER
// ===============================
async function rollbackCreatedResources(baseUrl, token, createdResources) {
  console.log("\n=== ROLLBACK: Cleaning up created resources ===");
  const rollbackResults = [];

  // Delete in reverse order (last created first: charges → rate plan → product)
  const reversed = [...createdResources].reverse();

  for (const resource of reversed) {
    const result = await zuoraDelete(baseUrl, token, resource.type, resource.id);
    rollbackResults.push({
      type: resource.type,
      id: resource.id,
      name: resource.name || null,
      deleted: result.success,
      error: result.error || null,
    });
  }

  console.log("Rollback results:", JSON.stringify(rollbackResults, null, 2));
  return rollbackResults;
}

// ===============================
// MAIN HANDLER
// ===============================
export const handler = async (event) => {
  console.log("Event received:", event);

  try {
    const req =
      typeof event.body === "string" ? JSON.parse(event.body) : event.body || {};

    const { clientId, clientSecret, body, zuora_api_payloads } = req;

    // ==========================
    // BASIC VALIDATION
    // ==========================
    if (!clientId || !clientSecret) {
      return {
        statusCode: 400,
        body: JSON.stringify({
          error: "clientId and clientSecret are required",
        }),
      };
    }

    const baseUrl = process.env.ZUORA_BASE_URL;
    const token = await getZuoraToken(clientId, clientSecret);

    const hasZuoraPayloads =
      Array.isArray(zuora_api_payloads) && zuora_api_payloads.length > 0;

    // ======================================================
    // MODE 1: GENERIC EXECUTOR FOR zuora_api_payloads[]
    // ======================================================
    if (hasZuoraPayloads) {
      const results = [];

      for (const item of zuora_api_payloads) {
        const { payload, zuora_api_type, payload_id } = item || {};
        const safeName = payload?.name || zuora_api_type || payload_id;

        if (!payload || !payload.method || !payload.endpoint) {
          results.push({
            payload_id,
            zuora_api_type,
            success: false,
            error: "payload.method and payload.endpoint are required",
            statusCode: 400,
          });
          continue;
        }

        try {
          const zuoraResp = await zuoraRequest(
            baseUrl,
            token,
            payload.method,
            payload.endpoint,
            payload.body || null
          );

          results.push({
            payload_id,
            zuora_api_type,
            name: safeName,
            success: true,
            response: zuoraResp,
          });
        } catch (err) {
          console.error(
            `Error executing payload_id=${payload_id}, type=${zuora_api_type}`,
            err
          );
          results.push({
            payload_id,
            zuora_api_type,
            name: safeName,
            success: false,
            error: err.message || "Zuora execution error",
            statusCode: err.statusCode || 500,
            raw: err.raw || null,
          });
        }
      }

      const allFailed = results.every((r) => r.success === false);
      const overallStatus = allFailed ? 500 : 200;

      return {
        statusCode: overallStatus,
        body: JSON.stringify({
          mode: "zuora_api_payloads",
          results,
        }),
      };
    }

    // ======================================================
    // MODE 2: LEGACY PRODUCT + RATE PLAN + CHARGES CREATION
    // (Passthrough approach - minimal transformation)
    // With rollback support: if any step fails, delete created resources
    // ======================================================

    if (!body || !body.product) {
      return {
        statusCode: 400,
        body: JSON.stringify({
          error: "body.product is required when zuora_api_payloads is not used",
        }),
      };
    }

    // Track all created resources for potential rollback
    const createdResources = [];

    // 1) PRODUCT - Passthrough with minimal defaults
    const p = body.product;

    if (!p.Name) {
      return {
        statusCode: 400,
        body: JSON.stringify({
          error: "Product Name is required (body.product.Name)",
        }),
      };
    }

    const defaultSku = p.Name.replace(/\s+/g, "-").toUpperCase();

    const productPayload = {
      ...p,
      SKU: p.SKU || defaultSku,
      ProductCode: p.ProductCode || p.SKU || defaultSku,
      EffectiveEndDate: p.EffectiveEndDate || "2099-12-31",
    };

    let productId = null;
    let ratePlanId = null;
    let ratePlanChargeIds = [];

    try {
      // Create Product
      const productRes = await zuoraPost(
        baseUrl,
        token,
        "/v1/object/product",
        productPayload
      );

      productId = productRes.Id;
      createdResources.push({
        type: "product",
        id: productId,
        name: productPayload.Name,
      });

      // 2) RATE PLAN - Passthrough with ProductId injected
      if (body.ratePlan) {
        const rp = body.ratePlan;

        if (!rp.Name) {
          // Rollback product before returning error
          const rollbackResults = await rollbackCreatedResources(
            baseUrl,
            token,
            createdResources
          );
          return {
            statusCode: 400,
            body: JSON.stringify({
              error: "ratePlan.Name is required when ratePlan payload is provided",
              rollbackAttempted: true,
              rollbackResults,
            }),
          };
        }

        const ratePlanPayload = {
          ...rp,
          ProductId: productId,
          EffectiveStartDate: rp.EffectiveStartDate || productPayload.EffectiveStartDate,
          EffectiveEndDate: rp.EffectiveEndDate || productPayload.EffectiveEndDate,
        };

        const ratePlanRes = await zuoraPost(
          baseUrl,
          token,
          "/v1/object/product-rate-plan",
          ratePlanPayload
        );

        ratePlanId = ratePlanRes.Id;
        createdResources.push({
          type: "product-rate-plan",
          id: ratePlanId,
          name: ratePlanPayload.Name,
        });
      }

      // 3) RATE PLAN CHARGES - Passthrough with ProductRatePlanId injected
      if (body.ratePlanCharge) {
        if (!ratePlanId) {
          // Rollback product before returning error
          const rollbackResults = await rollbackCreatedResources(
            baseUrl,
            token,
            createdResources
          );
          return {
            statusCode: 400,
            body: JSON.stringify({
              error:
                "Cannot create ratePlanCharge without a ratePlan. Provide ratePlan payload as well.",
              rollbackAttempted: true,
              rollbackResults,
            }),
          };
        }

        // Support both array and single charge
        const charges = Array.isArray(body.ratePlanCharge)
          ? body.ratePlanCharge
          : [body.ratePlanCharge];

        for (const c of charges) {
          // Passthrough: spread entire charge object, inject ProductRatePlanId
          const chargePayload = {
            ...c,
            ProductRatePlanId: ratePlanId,
          };

          const chargeRes = await zuoraPost(
            baseUrl,
            token,
            "/v1/object/product-rate-plan-charge",
            chargePayload
          );

          ratePlanChargeIds.push(chargeRes.Id);
          createdResources.push({
            type: "product-rate-plan-charge",
            id: chargeRes.Id,
            name: c.Name || null,
          });
        }
      }

      // Build response message
      let message = "Product created successfully!";
      if (ratePlanId && ratePlanChargeIds.length > 0) {
        message = "Product + RatePlan + Charges created successfully!";
      } else if (ratePlanId) {
        message = "Product + RatePlan created successfully!";
      }

      return {
        statusCode: 200,
        body: JSON.stringify({
          mode: "product_create",
          message,
          productId,
          ...(ratePlanId && { ratePlanId }),
          ...(ratePlanChargeIds.length > 0 && { ratePlanChargeIds }),
        }),
      };
    } catch (err) {
      // ERROR OCCURRED - rollback all created resources
      console.error("Error during product creation, initiating rollback:", err);

      let rollbackResults = [];
      if (createdResources.length > 0) {
        rollbackResults = await rollbackCreatedResources(
          baseUrl,
          token,
          createdResources
        );
      }

      return {
        statusCode: err.statusCode || 500,
        body: JSON.stringify({
          error: err.message || "Unexpected server error",
          rollbackAttempted: createdResources.length > 0,
          ...(rollbackResults.length > 0 && { rollbackResults }),
        }),
      };
    }
  } catch (err) {
    // Top-level error handler (e.g., auth errors, network issues before product creation)
    console.error("Lambda Error:", err);

    return {
      statusCode: err.statusCode || 500,
      body: JSON.stringify({
        error: err.message || "Unexpected server error",
      }),
    };
  }
};
