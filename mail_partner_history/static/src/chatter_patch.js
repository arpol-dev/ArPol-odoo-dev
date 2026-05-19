/** @odoo-module **/

import { Chatter } from "@mail/chatter/web_portal/chatter";
import { PartnerHistoryList } from "./partner_history_list";
import { onWillStart } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

Object.assign(Chatter.components, { PartnerHistoryList });

patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        this._partnerHistoryService = useService("mail_partner_history");
        Object.assign(this.state, {
            activeTab: "discussion",
            showHistoryTab: false,
            historyPartnerId: false,
            historyPartnerName: "",
            historyModelName: "",
        });
        onWillStart(async () => {
            if (!this.props.threadId) return;
            if (!this._partnerHistoryService.isEnabledForModel(this.props.threadModel)) return;
            await this._resolvePartnerHistory();
        });
    },

    async _resolvePartnerHistory() {
        const { threadModel, threadId } = this.props;
        try {
            const [modelRecord] = await this.orm.searchRead(
                "ir.model", [["model", "=", threadModel]], ["name"], { limit: 1 }
            );
            const modelName = modelRecord?.name || threadModel;

            if (threadModel === "res.partner") {
                const [record] = await this.orm.read("res.partner", [threadId], ["display_name"]);
                if (!record) return;
                Object.assign(this.state, {
                    showHistoryTab: true,
                    historyPartnerId: threadId,
                    historyPartnerName: record.display_name || "",
                    historyModelName: modelName,
                });
            } else {
                const [record] = await this.orm.read(threadModel, [threadId], ["partner_id"]);
                if (!record?.partner_id) return;
                const [partnerId, partnerName] = record.partner_id;
                Object.assign(this.state, {
                    showHistoryTab: true,
                    historyPartnerId: partnerId,
                    historyPartnerName: partnerName || "",
                    historyModelName: modelName,
                });
            }
        } catch {
            // Silencieux : pas d'onglet si erreur de lecture
        }
    },

    get historyTabLabel() {
        const model = this.state.historyModelName;
        return model ? _t`History ${model}` : _t("History");
    },

    switchTab(tab) {
        this.state.activeTab = tab;
    },
});
