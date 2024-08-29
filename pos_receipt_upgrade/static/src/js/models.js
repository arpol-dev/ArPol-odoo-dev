odoo.define('pos_receipt_upgrade.models', function (require) {
    'use strict';

    var {Order} = require("point_of_sale.models");
    var Registries = require("point_of_sale.Registries");

    const AddCompanyFields = (Order) =>
        class FrApplicableOrder extends Order {
            export_for_printing() {
                var result = super.export_for_printing(...arguments);
                debugger;
                console.log("Company data:", this.pos.company); // Log de débogage
                
                result.company.siret = this.pos.company.siret;
                result.company.street = this.pos.company.street;
                result.company.zip = this.pos.company.zip;
                result.company.city = this.pos.company.city;
                return result;
            }
        };

    Registries.Model.extend(Order, AddCompanyFields);
});