import { Component, onWillStart, useState } from "@odoo/owl";

import { Dropdown } from "@web/core/dropdown/dropdown";
import { useDropdownState } from "@web/core/dropdown/dropdown_hooks";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class AiAgentMenu extends Component {
    static components = { Dropdown };
    static props = [];
    static template = "mail_activity_ai_agent.AiAgentMenu";

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
        this.busService.subscribe("mail_activity_ai_agent/session_update", () => this.fetchData());
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
            error: "Erreur",
        }[status] ?? status;
    }

    onClickSession(session) {
        this.dropdown.close();
        // Une session "needs_attention" est déjà terminée côté serveur (tour unique, voir
        // mail_activity.py::_ai_agent_notify_needs_attention) : plus rien à rejoindre en live,
        // seul "running" a encore un remote_url valide.
        if (session.status === "running" && session.remote_url) {
            window.open(session.remote_url, "_blank");
            return;
        }
        if (session.res_model && session.res_id) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: session.res_model,
                res_id: session.res_id,
                views: [[false, "form"]],
                target: "current",
            });
            this.dropdown.close();
        }
    }

    async onDismiss(session, ev) {
        ev.stopPropagation();
        await this.orm.call("ai.agent.session", "action_dismiss", [[session.id]]);
        await this.fetchData();
    }
}

registry
    .category("systray")
    .add("mail_activity_ai_agent.AiAgentMenu", { Component: AiAgentMenu }, { sequence: 21 });
