"""
HTML Formatter for Agent Responses.
Converts markdown-formatted text to HTML while preserving code blocks and JSON.
"""

import re
from typing import List, Dict, Any, Tuple


def html_escape(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _extract_code_blocks(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """
    Extract code blocks and replace with placeholders.
    Returns modified text and list of extracted blocks (lang, code) tuples.
    """
    code_blocks: List[Tuple[str, str]] = []

    def replace_block(match):
        lang = match.group(1) or ""
        code = match.group(2)
        placeholder = f"__CODE_BLOCK_{len(code_blocks)}__"
        code_blocks.append((lang, code))
        return placeholder

    # Match ```lang\ncode\n``` or ```\ncode\n```
    pattern = r"```(\w*)\n?([\s\S]*?)```"
    modified_text = re.sub(pattern, replace_block, text)

    return modified_text, code_blocks


def _restore_code_blocks(text: str, code_blocks: List[Tuple[str, str]]) -> str:
    """Restore code blocks with HTML formatting."""
    for i, (lang, code) in enumerate(code_blocks):
        placeholder = f"__CODE_BLOCK_{i}__"
        escaped_code = html_escape(code.strip())
        if lang:
            html_block = (
                f'<pre><code class="language-{lang}">{escaped_code}</code></pre>'
            )
        else:
            html_block = f"<pre><code>{escaped_code}</code></pre>"
        text = text.replace(placeholder, html_block)
    return text


def _extract_inline_code(text: str) -> Tuple[str, List[str]]:
    """Extract inline code and replace with placeholders."""
    inline_codes = []

    def replace_inline(match):
        code = match.group(1)
        placeholder = f"__INLINE_CODE_{len(inline_codes)}__"
        inline_codes.append(code)
        return placeholder

    # Match `code` but not inside code blocks
    pattern = r"`([^`]+)`"
    modified_text = re.sub(pattern, replace_inline, text)

    return modified_text, inline_codes


def _restore_inline_code(text: str, inline_codes: List[str]) -> str:
    """Restore inline code with HTML formatting."""
    for i, code in enumerate(inline_codes):
        placeholder = f"__INLINE_CODE_{i}__"
        escaped_code = html_escape(code)
        text = text.replace(placeholder, f"<code>{escaped_code}</code>")
    return text


def _convert_headers(text: str) -> str:
    """Convert markdown headers to HTML."""
    # Process headers from h6 to h1 to avoid conflicts
    for level in range(6, 0, -1):
        pattern = r"^" + "#" * level + r"\s+(.+)$"
        replacement = f"<h{level}>\\1</h{level}>"
        text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
    return text


def _convert_bold(text: str) -> str:
    """Convert **bold** to <strong>."""
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)


def _convert_italic(text: str) -> str:
    """Convert *italic* to <em>."""
    return re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)


def _convert_horizontal_rule(text: str) -> str:
    """Convert --- to <hr>."""
    return re.sub(r"^---+$", "<hr>", text, flags=re.MULTILINE)


def _convert_unordered_lists(text: str) -> str:
    """Convert markdown unordered lists to HTML <ul>."""
    lines = text.split("\n")
    result = []
    in_list = False

    for line in lines:
        # Check for list item (-, *, or bullet point)
        match = re.match(r"^(\s*)([-*\u2022])\s+(.+)$", line)

        if match:
            content = match.group(3)

            if not in_list:
                result.append("<ul>")
                in_list = True

            result.append(f"<li>{content}</li>")
        else:
            if in_list:
                result.append("</ul>")
                in_list = False
            result.append(line)

    if in_list:
        result.append("</ul>")

    return "\n".join(result)


def _convert_ordered_lists(text: str) -> str:
    """Convert markdown ordered lists to HTML <ol>."""
    lines = text.split("\n")
    result = []
    in_list = False

    for line in lines:
        # Check for numbered list item (1., 2., etc.)
        match = re.match(r"^(\s*)(\d+)\.\s+(.+)$", line)

        if match:
            content = match.group(3)

            if not in_list:
                result.append("<ol>")
                in_list = True

            result.append(f"<li>{content}</li>")
        else:
            if in_list:
                result.append("</ol>")
                in_list = False
            result.append(line)

    if in_list:
        result.append("</ol>")

    return "\n".join(result)


def _convert_tables(text: str) -> str:
    """Convert markdown tables to HTML <table>."""
    lines = text.split("\n")
    result = []
    in_table = False
    header_done = False

    for i, line in enumerate(lines):
        # Check if line is a table row
        if "|" in line and line.strip().startswith("|") and line.strip().endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]

            # Skip separator row (|---|---|)
            if all(re.match(r"^[-:]+$", c) for c in cells):
                continue

            if not in_table:
                result.append(
                    '<div style="overflow-x: auto;"><table style="border: 1px solid black; border-collapse: collapse;">'
                )
                in_table = True
                header_done = False

            if not header_done:
                # This is the header row
                result.append("<thead><tr>")
                for cell in cells:
                    result.append(
                        f'<th style="border: 1px solid black; padding: 5px;">{cell}</th>'
                    )
                result.append("</tr></thead>")
                result.append("<tbody>")
                header_done = True
            else:
                # Data row
                result.append("<tr>")
                for cell in cells:
                    result.append(
                        f'<td style="border: 1px solid black; padding: 5px;">{cell}</td>'
                    )
                result.append("</tr>")
        else:
            if in_table:
                result.append("</tbody></table></div>")
                in_table = False
                header_done = False
            result.append(line)

    if in_table:
        result.append("</tbody></table></div>")

    return "\n".join(result)


def _convert_checkboxes(text: str) -> str:
    """Convert markdown checkboxes to HTML."""
    # Convert checked items
    text = re.sub(
        r"^\s*-\s*\[x\]\s*(.+)$",
        r'<label><input type="checkbox" checked disabled> \1</label>',
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    # Convert unchecked items
    text = re.sub(
        r"^\s*-\s*\[\s?\]\s*(.+)$",
        r'<label><input type="checkbox" disabled> \1</label>',
        text,
        flags=re.MULTILINE,
    )
    return text


def _wrap_paragraphs(text: str) -> str:
    """Wrap standalone text in <p> tags."""
    lines = text.split("\n")
    result = []

    for line in lines:
        stripped = line.strip()

        # Skip empty lines, HTML tags, or lines that are already formatted
        if not stripped:
            result.append("")
            continue

        if (
            stripped.startswith("<")
            or stripped.startswith("__CODE_BLOCK_")
            or stripped.startswith("__INLINE_CODE_")
        ):
            result.append(line)
            continue

        # Wrap plain text in paragraphs
        if not any(
            stripped.startswith(tag)
            for tag in [
                "<h",
                "<p",
                "<ul",
                "<ol",
                "<li",
                "<table",
                "<tr",
                "<td",
                "<th",
                "<hr",
                "<pre",
                "<code",
                "<strong",
                "<em",
                "<label",
                "</",
                "<thead",
                "<tbody",
            ]
        ):
            result.append(f"<p>{line}</p>")
        else:
            result.append(line)

    return "\n".join(result)


def markdown_to_html(text: str) -> str:
    """
    Convert markdown-formatted text to HTML.
    Preserves code blocks and inline code.

    Args:
        text: Markdown-formatted string

    Returns:
        HTML-formatted string
    """
    if not text:
        return text

    # Step 1: Extract code blocks to preserve them
    text, code_blocks = _extract_code_blocks(text)

    # Step 2: Extract inline code
    text, inline_codes = _extract_inline_code(text)

    # Step 3: Convert markdown elements
    text = _convert_headers(text)
    text = _convert_bold(text)
    text = _convert_italic(text)
    text = _convert_horizontal_rule(text)
    text = _convert_checkboxes(text)
    text = _convert_tables(text)
    text = _convert_ordered_lists(text)
    text = _convert_unordered_lists(text)

    # Step 4: Restore code elements
    text = _restore_inline_code(text, inline_codes)
    text = _restore_code_blocks(text, code_blocks)

    # Step 5: Replace \n with <br> for proper HTML line breaks
    # Only replace \n that are NOT between HTML tags (i.e., content line breaks)
    # First, replace double newlines with <br><br> (paragraph breaks)
    # Then replace single newlines with <br> (line breaks)
    # Pattern: \n that is NOT preceded by > or followed by <
    text = re.sub(r"(?<!>)\n\n(?!<)", "<br><br>", text)
    text = re.sub(r"(?<!>)\n(?!<)", "<br>", text)

    return text


def generate_reference_documentation(payload_structure: Dict[str, Any]) -> str:
    """
    Generate HTML documentation showing @{Reference.Id} relationships.

    Args:
        payload_structure: The payload dictionary containing nested objects

    Returns:
        HTML string with reference documentation
    """
    doc = "<h4>Object Reference Guide</h4>\n<ul>\n"

    # Check for product
    if payload_structure.get("type") == "Product" or "Name" in payload_structure:
        doc += "<li><code>@{Product.Id}</code> - References this Product's ID</li>\n"

    # Check for nested rate plans in various formats
    rate_plans = (
        payload_structure.get("productRatePlans")
        or payload_structure.get("ProductRatePlans")
        or []
    )

    if isinstance(rate_plans, list):
        for i, plan in enumerate(rate_plans):
            plan_name = plan.get("Name") or plan.get("name") or f"Rate Plan {i + 1}"
            doc += f"<li><code>@{{ProductRatePlan[{i}].Id}}</code> - '{plan_name}' Rate Plan ID</li>\n"

            # Check for nested charges
            charges = (
                plan.get("productRatePlanCharges")
                or plan.get("ProductRatePlanCharges")
                or []
            )

            if isinstance(charges, list):
                for j, charge in enumerate(charges):
                    charge_name = (
                        charge.get("Name") or charge.get("name") or f"Charge {j + 1}"
                    )
                    doc += f"<li><code>@{{ProductRatePlan[{i}].ProductRatePlanCharge[{j}].Id}}</code> - '{charge_name}' Charge ID</li>\n"

    doc += "</ul>"
    return doc


def format_payload_with_references(objects: List[Dict[str, Any]]) -> str:
    """
    Format a list of payload objects showing @{} references.

    Args:
        objects: List of object dictionaries with 'type' field

    Returns:
        HTML string showing objects with their reference IDs
    """
    doc = "<h4>Payload Objects with References</h4>\n<ul>\n"

    type_counts = {}

    for obj in objects:
        obj_type = obj.get("type", "Unknown")

        # Track count for array indexing
        if obj_type not in type_counts:
            type_counts[obj_type] = 0

        index = type_counts[obj_type]
        name = obj.get("Name") or obj.get("name") or "Unnamed"

        # Generate reference
        if index == 0 and type_counts.get(obj_type, 0) == 0:
            ref = f"@{{{obj_type}.Id}}"
        else:
            ref = f"@{{{obj_type}[{index}].Id}}"

        doc += f"<li><strong>{obj_type}</strong>: {name} - Reference: <code>{ref}</code></li>\n"

        type_counts[obj_type] = index + 1

    doc += "</ul>"
    return doc


def highlight_placeholders_in_json(json_str: str) -> str:
    """
    Highlight placeholder values in JSON strings with HTML styling.

    Transforms: "<<PLACEHOLDER:FieldName>>"
    Into styled HTML with orange color and bold font.

    Args:
        json_str: JSON string potentially containing placeholders

    Returns:
        HTML string with styled placeholders
    """
    import re

    # Pattern to match placeholders in JSON: "<<PLACEHOLDER:...>>"
    pattern = r'"(<<PLACEHOLDER:[^>]+>>)"'

    # Replace with styled span
    styled = re.sub(
        pattern,
        r'"<span style="color: #ff8c00; font-weight: bold; background-color: #fff3e0;">\1</span>"',
        json_str,
    )

    return styled


def generate_placeholder_warning_html(
    payloads_with_placeholders: List[Dict[str, Any]],
) -> str:
    """
    Generate a red warning table for payloads containing placeholders.

    Args:
        payloads_with_placeholders: List of payload dicts that have _placeholders field

    Returns:
        HTML string with styled warning table
    """
    if not payloads_with_placeholders:
        return ""

    # Build list items for each payload's placeholders
    items = []
    for p in payloads_with_placeholders:
        payload = p.get("payload", {})
        api_type = p.get("zuora_api_type", "")
        placeholders = p.get("_placeholders", [])

        if not placeholders:
            continue

        # Determine friendly name based on api_type
        if api_type == "charge_create":
            name = payload.get("Name", "Unnamed Charge")
            type_label = "Rate Plan Charge"
        elif api_type == "rate_plan_create":
            name = payload.get("Name", "Unnamed Rate Plan")
            type_label = "Rate Plan"
        elif api_type == "product_create":
            name = payload.get("Name", "Unnamed Product")
            type_label = "Product"
        else:
            name = payload.get("Name", "Unnamed")
            type_label = "Payload"

        # Format placeholder fields - combine multiple into one line
        if len(placeholders) == 1:
            fields_str = f"<code>{placeholders[0]}</code>"
            items.append(
                f'<li>{type_label} "{name}" has a placeholder for {fields_str}</li>'
            )
        else:
            fields_str = ", ".join(f"<code>{f}</code>" for f in placeholders)
            items.append(
                f'<li>{type_label} "{name}" has placeholders for {fields_str}</li>'
            )

    if not items:
        return ""

    items_html = "\n".join(items)

    return f"""<div style="overflow-x: auto; margin-bottom: 16px;">
<table style="width: 100%; border-collapse: collapse;">
<tr>
<td style="background-color: #fee2e2; border: 2px solid #dc2626; padding: 12px 16px; border-radius: 4px;">
<strong style="color: #991b1b;">⚠️ Missing Information in Payloads</strong>
<ul style="margin: 8px 0 0 0; padding-left: 20px; color: #7f1d1d;">
{items_html}
</ul>
</td>
</tr>
</table>
</div>
"""
