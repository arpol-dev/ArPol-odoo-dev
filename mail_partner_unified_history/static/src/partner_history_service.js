/** @odoo-module **/

import { registry } from "@web/core/registry";

export const partnerHistoryService = {
    dependencies: ["orm"],
    async start(env, { orm }) {
        let enabledSet = new Set();
        try {
            const models = await orm.call(
                "ir.model",
                "get_partner_history_enabled_models",
                [],
                {}
            );
            enabledSet = new Set(models);
        } catch {
            // En cas d'erreur réseau ou de droits : désactiver silencieusement
        }
        return {
            isEnabledForModel(modelName) {
                return enabledSet.has(modelName);
            },
        };
    },
};

registry.category("services").add("mail_partner_unified_history", partnerHistoryService);
