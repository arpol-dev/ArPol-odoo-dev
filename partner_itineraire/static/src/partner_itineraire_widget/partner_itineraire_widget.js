import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useRef, useEffect, onWillUnmount } from "@odoo/owl";

const IGN_PLAN_URL =
    "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0" +
    "&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal" +
    "&FORMAT=image/png&TILEMATRIXSET=PM" +
    "&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}";

const OSM_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";

const STATE_MESSAGES = {
    todo: {
        level: "info",
        text: "Aucun itinéraire calculé pour l'instant. Cliquez sur « Calculer l'itinéraire ».",
    },
    no_company_coords: {
        level: "warning",
        text: "L'adresse de la société courante n'est pas géolocalisée — impossible de définir le point de départ.",
    },
    no_partner_coords: {
        level: "warning",
        text: "L'adresse de ce contact n'est pas géolocalisée — impossible de définir l'arrivée.",
    },
    same_point: {
        level: "info",
        text: "Ce contact se trouve à la même adresse que la société : aucun itinéraire à afficher.",
    },
    error: {
        level: "danger",
        text: "Le calcul d'itinéraire a échoué. Voir le message d'erreur ci-dessus.",
    },
};

export class PartnerItineraireMap extends Component {
    setup() {
        this.mapRef = useRef("mapContainer");

        // Re-render map whenever the container appears in the DOM or
        // whenever the underlying route data changes. The first effect
        // is what handles the "user just switched to the Itinéraire tab"
        // case — the ref's element becomes truthy at that point.
        useEffect(
            (el) => {
                if (!el) {
                    this._destroyMap();
                    return;
                }
                this._initMap();
                this._renderRoute();
                this._observeResize(el);
                return () => {
                    this._destroyMap();
                };
            },
            () => [this.mapRef.el]
        );

        useEffect(
            () => {
                if (this.leafletMap) {
                    this._renderRoute();
                }
            },
            () => [
                this._readField(this.props.name),
                this._readField(this.props.bboxField),
                this._readField(this.props.startLatField),
                this._readField(this.props.startLonField),
                this._readField(this.props.endLatField),
                this._readField(this.props.endLonField),
            ]
        );

        onWillUnmount(() => this._destroyMap());
    }

    // ----- accessors -----------------------------------------------------

    _readField(name) {
        return name ? this.props.record.data[name] : null;
    }

    get computedState() {
        return this._readField(this.props.stateField) || "todo";
    }

    get placeholder() {
        return STATE_MESSAGES[this.computedState] || STATE_MESSAGES.todo;
    }

    get isComputed() {
        return this.computedState === "computed";
    }

    _parseJson(raw) {
        if (!raw) return null;
        try {
            return JSON.parse(raw);
        } catch (_e) {
            return null;
        }
    }

    // ----- Leaflet lifecycle --------------------------------------------

    _initMap() {
        if (this.leafletMap || !this.mapRef.el || typeof L === "undefined") {
            return;
        }
        this.leafletMap = L.map(this.mapRef.el, {
            zoomControl: true,
            attributionControl: true,
        });

        const ignLayer = L.tileLayer(IGN_PLAN_URL, {
            attribution: "© IGN-F/Géoportail",
            maxZoom: 18,
            minZoom: 0,
        });
        const osmLayer = L.tileLayer(OSM_URL, {
            attribution: "© OpenStreetMap contributors",
            maxZoom: 19,
        });

        ignLayer.addTo(this.leafletMap);
        L.control
            .layers({ "IGN Plan": ignLayer, OpenStreetMap: osmLayer })
            .addTo(this.leafletMap);

        // Default view (centre de la France) — sera remplacé par fitBounds
        // dès qu'un itinéraire est rendu.
        this.leafletMap.setView([46.6, 2.5], 5);
    }

    _renderRoute() {
        if (!this.leafletMap) return;

        if (this.routeGroup) {
            this.leafletMap.removeLayer(this.routeGroup);
            this.routeGroup = null;
        }

        if (!this.isComputed) return;

        const geometry = this._parseJson(this._readField(this.props.name));
        const bbox = this._parseJson(this._readField(this.props.bboxField));
        const startLat = this._readField(this.props.startLatField);
        const startLon = this._readField(this.props.startLonField);
        const endLat = this._readField(this.props.endLatField);
        const endLon = this._readField(this.props.endLonField);

        const group = L.featureGroup();

        if (geometry) {
            L.geoJSON(geometry, {
                style: { color: "#d9534f", weight: 5, opacity: 0.85 },
            }).addTo(group);
        }
        if (startLat && startLon) {
            L.circleMarker([startLat, startLon], {
                radius: 8,
                color: "#fff",
                weight: 2,
                fillColor: "#28a745",
                fillOpacity: 1,
            })
                .bindTooltip("Départ (société)")
                .addTo(group);
        }
        if (endLat && endLon) {
            L.circleMarker([endLat, endLon], {
                radius: 8,
                color: "#fff",
                weight: 2,
                fillColor: "#dc3545",
                fillOpacity: 1,
            })
                .bindTooltip("Arrivée (contact)")
                .addTo(group);
        }

        if (group.getLayers().length === 0) return;

        group.addTo(this.leafletMap);
        this.routeGroup = group;

        // bbox API = [minLon, minLat, maxLon, maxLat], Leaflet veut [[lat,lon],[lat,lon]]
        if (bbox && bbox.length === 4) {
            this.leafletMap.fitBounds(
                [
                    [bbox[1], bbox[0]],
                    [bbox[3], bbox[2]],
                ],
                { padding: [20, 20] }
            );
        } else {
            this.leafletMap.fitBounds(group.getBounds(), { padding: [20, 20] });
        }
    }

    _observeResize(el) {
        if (this.resizeObserver || !window.ResizeObserver) return;
        // Tabs in a Bootstrap notebook are display:none when inactive, so the
        // map container starts at 0×0. When the user clicks the Itinéraire tab,
        // the container grows. invalidateSize() alone isn't enough: fitBounds()
        // computed from a 0-pixel viewport yields a degenerate zoom level, so we
        // must also re-fit the route once the container has real dimensions.
        let lastUsableWidth = 0;
        this.resizeObserver = new ResizeObserver((entries) => {
            if (!this.leafletMap) return;
            this.leafletMap.invalidateSize();
            const w = entries[0].contentRect.width;
            if (lastUsableWidth < 50 && w >= 50 && this.routeGroup) {
                const bbox = this._parseJson(
                    this._readField(this.props.bboxField)
                );
                if (bbox && bbox.length === 4) {
                    this.leafletMap.fitBounds(
                        [
                            [bbox[1], bbox[0]],
                            [bbox[3], bbox[2]],
                        ],
                        { padding: [20, 20] }
                    );
                } else {
                    this.leafletMap.fitBounds(this.routeGroup.getBounds(), {
                        padding: [20, 20],
                    });
                }
            }
            lastUsableWidth = w;
        });
        this.resizeObserver.observe(el);
    }

    _destroyMap() {
        if (this.resizeObserver) {
            this.resizeObserver.disconnect();
            this.resizeObserver = null;
        }
        if (this.leafletMap) {
            this.leafletMap.remove();
            this.leafletMap = null;
            this.routeGroup = null;
        }
    }
}

PartnerItineraireMap.template = "partner_itineraire.PartnerItineraireMap";
PartnerItineraireMap.props = {
    ...standardFieldProps,
    bboxField: { type: String, optional: true },
    startLatField: { type: String, optional: true },
    startLonField: { type: String, optional: true },
    endLatField: { type: String, optional: true },
    endLonField: { type: String, optional: true },
    stateField: { type: String, optional: true },
};

export const partnerItineraireMapField = {
    component: PartnerItineraireMap,
    supportedTypes: ["text"],
    extractProps: ({ options }) => ({
        bboxField: options.bbox_field || "itineraire_bbox",
        startLatField: options.start_lat_field || "itineraire_start_lat",
        startLonField: options.start_lon_field || "itineraire_start_lon",
        endLatField: options.end_lat_field || "partner_latitude",
        endLonField: options.end_lon_field || "partner_longitude",
        stateField: options.state_field || "itineraire_state",
    }),
};

registry.category("fields").add("partner_itineraire_map", partnerItineraireMapField);
