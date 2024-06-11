odoo.define('pos_receipt_upgrade.models', function (require) {
    'use strict';

    const models = require('point_of_sale.models');
    const { Order } = models;

    models.Order = Order.extend({
        export_for_printing: function() {
            const receipt = this._super.apply(this, arguments);

            if (this.pos.company) {
                console.log("Company data:", this.pos.company); // Log de débogage
                receipt.company.siret = this.pos.company.siret || '';
                receipt.company.street = this.pos.company.street || '';
                receipt.company.zip = this.pos.company.zip || '';
                receipt.company.city = this.pos.company.city || '';
            }

            return receipt;
        },
    });
});