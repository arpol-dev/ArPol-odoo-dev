odoo.define('pos_receipt_upgrade.models', function (require) {
    'use strict';

    var {Order} = require("point_of_sale.models");
    var Registries = require("point_of_sale.Registries");

    const AddCompanyFields = (Order) =>
        class FrApplicableOrder extends Order {
            export_for_printing() {
                var result = super.export_for_printing(...arguments);
                var company = this.pos.company;
                if (result.company && company) {
                    result.company.siret = company.siret;
                    result.company.street = company.street;
                    result.company.zip = company.zip;
                    result.company.city = company.city;
                }
                return result;
            }
        };

    Registries.Model.extend(Order, AddCompanyFields);
});