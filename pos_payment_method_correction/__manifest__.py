{
    'name': 'POS Payment Method Correction',
    'version': '18.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Correct the payment method of a closed POS session payment and propagate the cash balances',
    'author': 'ArPol',
    'website': 'https://arpol.fr',
    'license': 'LGPL-3',
    'depends': ['point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_payment_method_change_views.xml',
        'data/server_actions.xml',
    ],
    'installable': True,
}
