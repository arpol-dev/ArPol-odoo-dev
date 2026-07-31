odoo.define('us_website_image_zoom.website_image_zoom', function(require) {
'use strict';

var config = require('web.config');
var publicWidget = require('web.public.widget');
require("web.zoomodoo");
const { ComponentWrapper } = require('web.OwlCompatibility');
const { ImageViewerWrapper } = require("@us_website_image_zoom/js/components/website_image_viewer");


publicWidget.registry.WebsiteImageZoom = publicWidget.Widget.extend({
    selector: '#wrapwrap',

     /**
     * @override
     */
    start() {
        const def = this._super(...arguments);
        this._startZoom();
        return def;
    },
    destroy() {
        this._super.apply(this, arguments);
        this._cleanupZoom();
    },

    /**
     * @private
     */
    _startZoom: function () {
     const imagePages = document.querySelectorAll(".oe_us_website_image_zoom");

    if (!imagePages.length || config.device.mobile) {
        return;
    }

    this._cleanupZoom();
    this.zoomCleanup = [];

    imagePages.forEach(imagePage => {
    if (imagePage.dataset.websiteZoomClick) {
        const images = imagePage.querySelectorAll("img");
        images.forEach((image, index) => {
            const handler = () => {
                const dialog = new ComponentWrapper(this, ImageViewerWrapper, {
                    selectedImageIdx: [...images].indexOf(image),
                    images
                });
                dialog.mount(document.body);
            };
            image.addEventListener("click", handler);
            this.zoomCleanup.push(() => {
                image.removeEventListener("click", handler);
            });
        });
    }
    });
    },
    _cleanupZoom() {
        if (!this.zoomCleanup || !this.zoomCleanup.length) {
            return;
        }
        for (const cleanup of this.zoomCleanup) {
            cleanup();
        }
        this.zoomCleanup = undefined;
    },
    })
});