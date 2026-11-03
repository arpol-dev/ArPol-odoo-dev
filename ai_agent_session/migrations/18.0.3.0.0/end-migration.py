# -*- coding: utf-8 -*-
# 18.0.3.0.0 : Odoo ne suit plus les sessions. Suppression de la table de suivi (ai_agent_session),
# de son wizard de réponse et des colonnes remplacées sur l'action serveur (ai_agent_model et
# ai_agent_permission_mode, remplacées par ai_agent_model_id et ai_agent_permission). L'historique
# reste dans les notes du chatter ; les sessions encore ouvertes restent dans IArPol.
def migrate(cr, version):
    if not version:
        return
    cr.execute("DROP TABLE IF EXISTS ai_agent_session CASCADE")
    cr.execute("DROP TABLE IF EXISTS ai_agent_session_reply CASCADE")
    cr.execute("""
        DELETE FROM ir_model
         WHERE model IN ('ai.agent.session', 'ai.agent.session.reply')
    """)
    cr.execute("""
        ALTER TABLE ir_act_server
            DROP COLUMN IF EXISTS ai_agent_model,
            DROP COLUMN IF EXISTS ai_agent_permission_mode
    """)
