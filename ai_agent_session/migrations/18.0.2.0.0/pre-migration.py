# -*- coding: utf-8 -*-
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
    cr.execute("""
        UPDATE ai_agent_session
           SET status = 'cancelled',
               conclusion = 'Cancelled: activity-based AI Agent sessions were removed.'
         WHERE status IN ('running', 'needs_attention')
           AND source_activity_id IS NOT NULL
    """)
    cr.execute("""
        DELETE FROM mail_activity
         WHERE activity_type_id IN (SELECT id FROM mail_activity_type WHERE category = 'ai_agent')
    """)
    cr.execute("DELETE FROM mail_activity_type WHERE category = 'ai_agent'")
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE module = 'mail_activity_ai_agent' AND model = 'mail.activity.type'
    """)
