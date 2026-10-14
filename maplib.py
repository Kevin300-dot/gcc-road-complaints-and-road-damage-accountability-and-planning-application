"""
Builds a self-contained OpenStreetMap (Leaflet) page for the Kandanchavadi map.

Everything on the map comes from data:
  * the base map is OpenStreetMap, so every road, lane and landmark in Kandanchavadi is drawn
    by OSM itself (nothing is hand-drawn here);
  * the red outline is the boundary traced in Google My Maps (data/kandanchavadi_boundary.kml);
  * every dot is a real complaint at its real GPS position.

The returned string is a full HTML document, shown in Streamlit with components.html().
Leaflet and the tiles are fetched by the viewer's browser, so the page needs internet access.
All text that can come from a citizen (description, road name) is HTML-escaped here.
"""
import html
import json
import os

PRIORITY_COLORS = {"Critical": "#b91c1c", "High": "#d97706", "Medium": "#2563eb", "Low": "#4b5563"}

LEAFLET_VERSION = "1.9.4"


def _safe_json(obj) -> str:
    """JSON for embedding inside a <script> tag: stops '</script>' or '<!--' in data from breaking out."""
    return (json.dumps(obj)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _complaint_popup(c: dict, photo_base_url: str) -> str:
    esc = html.escape
    parts = [
        f"<b>{esc(str(c.get('complaint_id', '')))}</b>",
        f"{esc(str(c.get('road_name') or ''))}",
        f"{esc(str(c.get('damage_type_label') or ''))}",
        f"Severity: {esc(str(c.get('severity') or '-'))} &middot; Status: {esc(str(c.get('status') or '-'))}",
    ]
    if c.get("date"):
        parts.append(f"Reported {esc(str(c['date']))}")
    if c.get("text"):
        parts.append(f"<i>{esc(str(c['text'])[:140])}</i>")
    photo = c.get("photo")
    if photo and photo_base_url:
        name = os.path.basename(str(photo))
        src = f"{photo_base_url.rstrip('/')}/photo/{html.escape(name, quote=True)}"
        parts.append(
            f"<img src=\"{src}\" style=\"width:200px;max-width:100%;border-radius:6px;margin-top:4px\" "
            f"loading=\"lazy\" onerror=\"this.style.display='none'\">"
        )
    parts.append(f"<span style='color:#666'>{c['latitude']:.6f}, {c['longitude']:.6f}</span>")
    return "<br>".join(parts)


def build_map_html(
    boundary_geojson: dict,
    complaints: list = None,
    hotspots: list = None,
    photo_base_url: str = "",
    height_px: int = 620,
    pin: dict = None,
    click_to_pick: bool = False,
    show_hotspot_rings: bool = True,
) -> str:
    complaints = complaints or []
    hotspots = hotspots or []
    esc = html.escape

    pts = []
    for c in complaints:
        if c.get("latitude") is None or c.get("longitude") is None:
            continue
        pts.append({
            "lat": float(c["latitude"]), "lon": float(c["longitude"]),
            "color": PRIORITY_COLORS.get(c.get("priority"), "#6b7280"),
            "popup": _complaint_popup(c, photo_base_url),
        })

    rings = []
    if show_hotspot_rings:
        for h in hotspots:
            rings.append({
                "lat": float(h["latitude"]), "lon": float(h["longitude"]),
                "radius": max(float(h.get("radius_m") or 0) + 12.0, 18.0),
                "color": PRIORITY_COLORS.get(h.get("priority"), "#6b7280"),
                "tip": f"{esc(str(h.get('label', '')))} &middot; {h.get('total_complaints', '')} report(s) &middot; {esc(str(h.get('priority', '')))}",
            })

    data = {
        "boundary": boundary_geojson,
        "points": pts,
        "rings": rings,
        "pin": pin,
        "pick": bool(click_to_pick),
    }

    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@{LEAFLET_VERSION}/dist/leaflet.css">
<style>
 html, body {{ margin:0; padding:0; }}
 #map {{ height:{int(height_px)}px; width:100%; border-radius:10px; border:1px solid #d8e2df; }}
 .legend {{ background:#fff; padding:8px 10px; border-radius:8px; font:12px/1.5 'Segoe UI',Arial,sans-serif; box-shadow:0 1px 6px rgba(0,0,0,.25); }}
 .legend i {{ display:inline-block; width:11px; height:11px; border-radius:50%; margin-right:6px; vertical-align:middle; }}
 .legend .line {{ display:inline-block; width:18px; height:0; border-top:3px solid #d62828; margin-right:6px; vertical-align:middle; }}
 #pickbox {{ font:13px 'Segoe UI',Arial,sans-serif; margin-top:6px; color:#20322f; }}
 #pickbox code {{ background:#eef3f1; padding:2px 6px; border-radius:5px; user-select:all; }}
 #err {{ font:14px 'Segoe UI',Arial,sans-serif; color:#b91c1c; padding:20px; }}
</style></head>
<body>
<div id="map"></div>
<div id="pickbox"></div>
<script src="https://unpkg.com/leaflet@{LEAFLET_VERSION}/dist/leaflet.js"></script>
<script>
(function() {{
  var DATA = {_safe_json(data)};
  if (typeof L === 'undefined') {{
    document.getElementById('map').innerHTML = "<div id='err'>The map could not load. It needs an internet connection to fetch OpenStreetMap.</div>";
    return;
  }}
  var map = L.map('map', {{ zoomControl: true, maxBoundsViscosity: 0.8 }});
  L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }}).addTo(map);

  var boundary = L.geoJSON(DATA.boundary, {{ style: {{ color: '#d62828', weight: 3, fillColor: '#d62828', fillOpacity: 0.05 }} }}).addTo(map);
  var bb = boundary.getBounds();
  map.fitBounds(bb.pad(0.05));
  map.setMaxBounds(bb.pad(0.6));
  map.setMinZoom(Math.max(map.getBoundsZoom(bb.pad(0.6)), 13));
  L.control.scale({{ imperial: false }}).addTo(map);

  DATA.rings.forEach(function(r) {{
    L.circle([r.lat, r.lon], {{ radius: r.radius, color: r.color, weight: 2, dashArray: '5 4', fillColor: r.color, fillOpacity: 0.08 }})
      .bindTooltip(r.tip).addTo(map);
  }});
  DATA.points.forEach(function(p) {{
    L.circleMarker([p.lat, p.lon], {{ radius: 6, color: '#ffffff', weight: 1.5, fillColor: p.color, fillOpacity: 0.95 }})
      .bindPopup(p.popup, {{ maxWidth: 230 }}).addTo(map);
  }});

  var pinMarker = null;
  function setPin(lat, lon, label) {{
    if (pinMarker) {{ map.removeLayer(pinMarker); }}
    pinMarker = L.circleMarker([lat, lon], {{ radius: 10, color: '#111827', weight: 3, fillColor: '#facc15', fillOpacity: 1 }})
      .bindTooltip(label || 'Selected location', {{ permanent: true, direction: 'top' }}).addTo(map);
  }}
  if (DATA.pin) {{ setPin(DATA.pin.lat, DATA.pin.lon, DATA.pin.label); }}

  if (DATA.pick) {{
    var box = document.getElementById('pickbox');
    box.innerHTML = 'Click the map to read off coordinates, then paste them into the location box.';
    map.on('click', function(e) {{
      var txt = e.latlng.lat.toFixed(6) + ', ' + e.latlng.lng.toFixed(6);
      setPin(e.latlng.lat, e.latlng.lng, 'Clicked point');
      box.innerHTML = 'Clicked point: <code>' + txt + '</code> &mdash; copy it into the location box above.';
    }});
  }}

  var legend = L.control({{ position: 'bottomright' }});
  legend.onAdd = function() {{
    var d = L.DomUtil.create('div', 'legend');
    d.innerHTML = "<div><span class='line'></span>Kandanchavadi boundary</div>" +
      "<div><i style='background:#b91c1c'></i>Critical</div><div><i style='background:#d97706'></i>High</div>" +
      "<div><i style='background:#2563eb'></i>Medium</div><div><i style='background:#4b5563'></i>Low</div>";
    return d;
  }};
  legend.addTo(map);
}})();
</script>
</body></html>"""
