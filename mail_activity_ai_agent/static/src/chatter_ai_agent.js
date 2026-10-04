import { Chatter } from "@mail/chatter/web_portal/chatter";

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        this.aiAgentAction = useService("action");
    },

    async launchAiAgent() {
        this.closeSearch();
        const launch = (thread) =>
            this.aiAgentAction.doAction("mail_activity_ai_agent.ai_agent_session_wizard_action", {
                additionalContext: { default_res_model: thread.model, default_res_id: thread.id },
                // Rafraîchit le chatter à la fermeture (rien de visible tant que la session
                // tourne, mais cohérent avec le bouton "Activities").
                onClose: () => this.load(thread, ["messages"]),
            });
        if (this.state.thread.id) {
            launch(this.state.thread);
        } else {
            // Enregistrement pas encore sauvegardé : même mécanique que scheduleActivity.
            this.onThreadCreated = launch;
            this.props.saveRecord?.();
        }
    },
});
