# -*- coding: utf-8 -*-
# Le module s'appelait mail_activity_ai_agent jusqu'à la 1.x ; le renommage en base (ir_module_module,
# ir_model_data...) est fait avant la mise à jour, d'où les deux noms acceptés ci-dessous.
# La 2.0.0 supprime le lancement via mail.activity (type d'activité "AI Agent Session", champs
# ai_* sur mail.activity / mail.activity.type, wizard d'activité) au profit du bouton du chatter.
# À faire AVANT le chargement : mail_activity.activity_type_id est en ondelete='restrict', donc le
# type ne peut être supprimé tant qu'il reste des activités, et la valeur de sélection 'ai_agent'
# de la catégorie disparaît avec le code.
def migrate(cr, version):
    if not version:
        return
    # Sessions encore en cours liées à une activité : leur callback (activity_id=...) n'aura plus
    # de route. Les marquer annulées plutôt que de les laisser 'running' pour toujours (la
    # session distante, elle, doit être arrêtée à la main : pas d'appel réseau dans une migration).
    # Le schéma installé dépend de la version 1.x d'origine : source_activity_id n'existe que
    # depuis la gestion de l'annulation, activity_id depuis le départ.
    cr.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'ai_agent_session'
           AND column_name IN ('source_activity_id', 'activity_id')
    """)
    linked = ' OR '.join(f'{name} IS NOT NULL' for (name,) in cr.fetchall())
    if linked:
        cr.execute(f"""
            UPDATE ai_agent_session
               SET status = 'cancelled',
                   conclusion = 'Cancelled: activity-based AI Agent sessions were removed.'
             WHERE status IN ('running', 'needs_attention')
               AND ({linked})
        """)
    cr.execute("""
        DELETE FROM mail_activity
         WHERE activity_type_id IN (SELECT id FROM mail_activity_type WHERE category = 'ai_agent')
    """)
    cr.execute("DELETE FROM mail_activity_type WHERE category = 'ai_agent'")
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE module IN ('mail_activity_ai_agent', 'ai_agent_session')
           AND model = 'mail.activity.type'
    """)
