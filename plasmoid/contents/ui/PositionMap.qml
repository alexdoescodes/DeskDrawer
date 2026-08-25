import QtQuick

/*
 * Where each drawer entry sits on the canvas, keyed by item name.
 *
 * Positions are a property of the view, not of the drawer: the daemon neither
 * writes nor reads them, so this map is serialized into the widget's own
 * configuration. Everything here is pure arithmetic over a JS object, which
 * keeps it testable without a scene.
 */
QtObject {
    id: map

    property real tileWidth: 96
    property real tileHeight: 96
    property real canvasWidth: 0
    property real canvasHeight: 0

    // Emitted whenever the map changes in a way worth persisting. load() is
    // deliberately silent: restoring saved state must not trigger a re-save.
    signal updated()

    property var points: ({})

    function _limitX() {
        return Math.max(0, map.canvasWidth - map.tileWidth);
    }

    function _limitY() {
        return Math.max(0, map.canvasHeight - map.tileHeight);
    }

    function _clamp(value, limit) {
        return Math.min(Math.max(0, value), limit);
    }

    function has(name) {
        return Object.prototype.hasOwnProperty.call(map.points, name);
    }

    function positionFor(name) {
        return map.has(name) ? map.points[name] : null;
    }

    function place(name, x, y) {
        // Reassigned rather than mutated in place: a var property only
        // notifies its bindings when the reference itself changes, and the
        // delegates bind their position straight to this map.
        const next = {};
        const names = Object.keys(map.points);
        for (let i = 0; i < names.length; ++i) {
            next[names[i]] = map.points[names[i]];
        }
        next[name] = {
            x: map._clamp(x, map._limitX()),
            y: map._clamp(y, map._limitY())
        };
        map.points = next;
        map.updated();
    }

    // True when a tile at (x, y) would cover any part of an already placed one.
    function _occupied(x, y) {
        const names = Object.keys(map.points);
        for (let i = 0; i < names.length; ++i) {
            const point = map.points[names[i]];
            if (Math.abs(point.x - x) < map.tileWidth
                    && Math.abs(point.y - y) < map.tileHeight) {
                return true;
            }
        }
        return false;
    }

    // For entries that arrive without a drop point of their own - added by the
    // CLI or by the daemon - take the first free slot in reading order. Items
    // may overlap once the canvas is full; that is preferable to hiding one.
    function autoPlace(name) {
        if (map.has(name)) {
            return;
        }

        const columns = Math.max(1, Math.floor(map.canvasWidth / map.tileWidth));
        const rows = Math.max(1, Math.floor(map.canvasHeight / map.tileHeight));

        for (let row = 0; row < rows; ++row) {
            for (let column = 0; column < columns; ++column) {
                const x = column * map.tileWidth;
                const y = row * map.tileHeight;
                if (!map._occupied(x, y)) {
                    map.place(name, x, y);
                    return;
                }
            }
        }
        map.place(name, 0, 0);
    }

    // After a resize, pull everything back inside rather than letting tiles
    // strand themselves beyond the visible area.
    function clampAll() {
        const limitX = map._limitX();
        const limitY = map._limitY();
        const next = {};
        const names = Object.keys(map.points);
        for (let i = 0; i < names.length; ++i) {
            const point = map.points[names[i]];
            next[names[i]] = {
                x: map._clamp(point.x, limitX),
                y: map._clamp(point.y, limitY)
            };
        }
        map.points = next;
        map.updated();
    }

    // Drop positions for entries that have left the drawer, so the stored
    // configuration cannot grow without bound.
    function prune(names) {
        const keep = {};
        for (let i = 0; i < names.length; ++i) {
            if (map.has(names[i])) {
                keep[names[i]] = map.points[names[i]];
            }
        }
        map.points = keep;
        map.updated();
    }

    function serialize() {
        return JSON.stringify(map.points);
    }

    function load(json) {
        let parsed = {};
        try {
            parsed = JSON.parse(json || "{}");
        } catch (error) {
            parsed = {};
        }

        const restored = {};
        const names = Object.keys(parsed || {});
        for (let i = 0; i < names.length; ++i) {
            const point = parsed[names[i]];
            if (point && isFinite(point.x) && isFinite(point.y)) {
                restored[names[i]] = { x: Number(point.x), y: Number(point.y) };
            }
        }
        map.points = restored;
    }
}
