/** @odoo-module **/

import { Component, onWillStart, useState, markup } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const LIMIT = 30;

export class PartnerHistoryList extends Component {
    static template = "mail_partner_history.PartnerHistoryList";
    static props = {
        partnerId: { type: Number },
        partnerName: { type: String },
    };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.user = useService("user");
        this.state = useState({
            messages: [],
            isLoaded: false,
            canLoadMore: false,
            offset: 0,
        });
        onWillStart(() => this._loadMessages());
    }

    async _loadMessages() {
        const result = await this.orm.call(
            "mail.message",
            "get_partner_history_messages",
            [this.props.partnerId],
            { limit: LIMIT, offset: this.state.offset }
        );
        this.state.messages = [...this.state.messages, ...result];
        this.state.canLoadMore = result.length === LIMIT;
        this.state.isLoaded = true;
    }

    async loadMore() {
        this.state.offset += LIMIT;
        await this._loadMessages();
    }

    get groupedMessages() {
        const groups = [];
        let currentLabel = null;

        for (const msg of this.state.messages) {
            const label = this._dateLabel(msg.date);
            if (label !== currentLabel) {
                currentLabel = label;
                groups.push({ dateLabel: label, messages: [] });
            }
            groups[groups.length - 1].messages.push(msg);
        }
        return groups;
    }

    _dateLabel(isoDate) {
        if (!isoDate) return "Date inconnue";
        const d = new Date(isoDate);
        const today = new Date();
        const yesterday = new Date(today);
        yesterday.setDate(today.getDate() - 1);

        if (d.toDateString() === today.toDateString()) return "Aujourd'hui";
        if (d.toDateString() === yesterday.toDateString()) return "Hier";
        return d.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
    }

    openDocument(msg) {
        if (!msg.model || !msg.res_id) return;
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: msg.model,
            res_id: msg.res_id,
            views: [[false, 'form']],
        });
    }

    getMarkupBody(body) {
        return markup(body || '');
    }

    getBubbleColor(msg) {
        if (msg.is_internal) return undefined;
        if (msg.author_id && msg.author_id[0] === this.user.partnerId) return 'green';
        return 'blue';
    }

    getAvatarUrl(authorId) {
        if (!authorId) return "/web/static/img/partner.png";
        return `/web/image/res.partner/${authorId}/avatar_128`;
    }

    getRelativeTime(isoDate) {
        if (!isoDate) return "";
        const diff = Date.now() - new Date(isoDate).getTime();
        const minutes = Math.floor(diff / 60000);
        if (minutes < 1) return "à l'instant";
        if (minutes < 60) return `il y a ${minutes} min`;
        const hours = Math.floor(minutes / 60);
        if (hours < 24) return `il y a ${hours}h`;
        const days = Math.floor(hours / 24);
        if (days < 30) return `il y a ${days}j`;
        const months = Math.floor(days / 30);
        return `il y a ${months} mois`;
    }
}
