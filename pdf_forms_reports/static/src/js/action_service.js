/** @odoo-module **/

import { makeActionManager } from "@web/webclient/actions/action_service";

export function MyMakeActionManager(env) {
    const actionManager = makeActionManager(env);

    const originalExecuteReportAction = actionManager._executeReportAction;

    actionManager._executeReportAction = async function (action, options) {
        if (action.report_type === "pdf_form") {
            return _triggerDownload(action, options, "pdf");
        }
        return originalExecuteReportAction.call(this, action, options);
    };
    return actionManager;
};