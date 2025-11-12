/** @odoo-module **/

import { registry } from "@web/core/registry";
import { download } from "@web/core/network/download";

/**
 * Custom report handler for PDF Form reports
 * Downloads directly from /report/pdf_form/ route without going through /report/download
 */
async function handlePdfFormReport(action, options, env) {
    if (action.report_type !== "pdf_form") {
        return false; // Not our report type, let other handlers deal with it
    }

    // Build report URL using our custom controller
    let url = `/report/pdf_form/${action.report_name}`;
    const actionContext = action.context || {};

    if (actionContext.active_ids && actionContext.active_ids.length > 0) {
        // Add record IDs to URL
        url += `/${actionContext.active_ids.join(",")}`;
    }

    console.log("[PDF Form] Downloading from URL:", url);
    console.log("[PDF Form] Action:", action);

    // Block UI during download
    env.services.ui.block();

    try {
        // Direct download from our custom route using GET
        await download({
            url: url,
            data: {},
        });
    } finally {
        env.services.ui.unblock();
    }

    return true; // We handled it
}

// Register the handler in the report handlers registry
registry.category("ir.actions.report handlers").add("pdf_form_handler", handlePdfFormReport);
