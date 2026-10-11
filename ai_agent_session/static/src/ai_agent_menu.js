import { Component, onWillStart, useState } from "@odoo/owl";

import { Dropdown } from "@web/core/dropdown/dropdown";
import { useDropdownState } from "@web/core/dropdown/dropdown_hooks";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class AiAgentMenu extends Component {
    static components = { Dropdown };
    static props = [];
    static template = "ai_agent_session.AiAgentMenu";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.busService = useService("bus_service");
        this.dropdown = useDropdownState();
        this.state = useState({ counter: 0, sessions: [] });

        onWillStart(() => this.fetchData());
        // Rafraîchit dès qu'une session change de statut côté serveur (voir
        // ai_agent_session.py::_notify_systray), pas seulement à l'ouverture du menu. Le canal
        // bus du partenaire courant est déjà rejoint par défaut par le webclient (mail) — pas
        // besoin de l'ajouter nous-mêmes.
        this.busService.subscribe("ai_agent_session/session_update", () => this.fetchData());
    }

    async fetchData() {
        const data = await this.orm.call("ai.agent.session", "get_systray_data", []);
        this.state.counter = data.counter;
        this.state.sessions = data.sessions;
    }

    statusLabel(status) {
        return {
            running: "En cours",
            needs_attention: "Attend votre réponse",
            done: "Terminée",
            cancelled: "Annulée",
            error: "Erreur",
        }[status] ?? status;
    }

    onClickSession(session) {
        this.dropdown.close();
        // Session vivante (en cours ou en attente de réponse) : ouvre sa page dans IAssistant, pour
        // la suivre ou y répondre directement. Sinon (terminée, erreur...) : l'enregistrement
        // d'origine. Le lien vers l'enregistrement reste accessible pour les sessions vivantes via
        // le bouton dédié.
        if (session.session_url) {
            window.open(session.session_url, "_blank");
            return;
        }
        this.onOpenRecord(session);
    }

    onOpenRecord(session, ev) {
        ev?.stopPropagation();
        this.dropdown.close();
        if (session.res_model && session.res_id) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: session.res_model,
                res_id: session.res_id,
                views: [[false, "form"]],
                target: "current",
            });
        }
    }

    onReply(session, ev) {
        ev.stopPropagation();
        this.dropdown.close();
        this.action.doAction("ai_agent_session.ai_agent_session_reply_action", {
            additionalContext: { default_session_id: session.id },
            onClose: () => this.fetchData(),
        });
    }

    async onDismiss(session, ev) {
        ev.stopPropagation();
        await this.orm.call("ai.agent.session", "action_dismiss", [[session.id]]);
        await this.fetchData();
    }
}

registry
    .category("systray")
    .add("ai_agent_session.AiAgentMenu", { Component: AiAgentMenu }, { sequence: 21 });
