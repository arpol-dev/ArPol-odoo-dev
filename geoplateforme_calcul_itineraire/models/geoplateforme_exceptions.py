# -*- coding: utf-8 -*-
"""Exceptions dédiées au connecteur Géoplateforme.

Toutes les exceptions héritent de :class:`odoo.exceptions.UserError` afin que,
lorsqu'elles remontent jusqu'à l'utilisateur final via un module consommateur,
Odoo affiche un message d'erreur propre dans l'UI plutôt qu'une trace
technique.

Hiérarchie :

    UserError (Odoo)
    └── GeoplateformeError                  (base — toute erreur du connecteur)
        ├── GeoplateformeNetworkError       (réseau : DNS, timeout, refus)
        ├── GeoplateformeAPIError           (HTTP non-2xx renvoyé par l'API)
        └── GeoplateformeInvalidResponseError (réponse non-JSON / structure inattendue)

Les consommateurs peuvent attraper :class:`GeoplateformeError` pour traiter
toutes les erreurs du connecteur d'un bloc, ou cibler une sous-classe pour un
traitement spécifique (retry sur ``GeoplateformeNetworkError`` par exemple).
"""

from odoo.exceptions import UserError


class GeoplateformeError(UserError):
    """Erreur de base du connecteur Géoplateforme."""


class GeoplateformeNetworkError(GeoplateformeError):
    """Erreur réseau bas-niveau : DNS, timeout, connexion refusée, etc.

    Levée lorsque la requête HTTP n'a pas pu aboutir (avant même de recevoir
    une réponse du serveur IGN).
    """


class GeoplateformeAPIError(GeoplateformeError):
    """L'API Géoplateforme a renvoyé un code HTTP non-2xx.

    Les attributs ``status_code`` et ``body`` sont accessibles pour permettre
    aux consommateurs de réagir finement (par ex. retry sur 503).
    """

    def __init__(self, message, status_code=None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class GeoplateformeInvalidResponseError(GeoplateformeError):
    """La réponse HTTP a été reçue mais n'est pas exploitable.

    Typiquement : corps non-JSON, ou JSON dont la structure ne contient pas
    les champs attendus.
    """
