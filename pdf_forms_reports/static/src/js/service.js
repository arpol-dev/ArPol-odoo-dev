/** @odoo-module **/

import { registry } from "@web/core/registry";
import { MyMakeActionManager } from "./action_service";

registry.category("services").add("action", MyMakeActionManager, {
    force: true,
});
