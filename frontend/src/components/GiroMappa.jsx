import React, { useEffect } from "react";
import { MapContainer, TileLayer, Marker, Polyline, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const numIcon = (n, color = "#4f46e5") => L.divIcon({
  className: "",
  html: `<div style="width:30px;height:30px;border-radius:50%;background:${color};color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)">${n}</div>`,
  iconSize: [30, 30], iconAnchor: [15, 15],
});

function FitBounds({ positions }) {
  const map = useMap();
  useEffect(() => {
    if (positions.length > 1) map.fitBounds(L.latLngBounds(positions), { padding: [30, 30] });
  }, [map, positions]);
  return null;
}

export const GiroMappa = ({ giro }) => {
  const sede = [giro.partenza.lat, giro.partenza.lon];
  const stops = giro.tappe.map(t => [t.lat, t.lon]);
  const line = giro.geometria && giro.geometria.length > 1
    ? giro.geometria
    : [sede, ...stops, sede];
  return (
    <div className="rounded-xl overflow-hidden border border-slate-200 h-[420px]" data-testid="giro-mappa">
      <MapContainer center={sede} zoom={12} style={{ height: "100%", width: "100%" }} scrollWheelZoom={false}>
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' />
        <Polyline positions={line} pathOptions={{ color: "#4f46e5", weight: 4, opacity: 0.75 }} />
        <Marker position={sede} icon={numIcon("L", "#0f172a")}>
          <Popup><b>Lavanderia</b><br />{giro.partenza.indirizzo}</Popup>
        </Marker>
        {giro.tappe.map(t => (
          <Marker key={t.posizione} position={[t.lat, t.lon]} icon={numIcon(t.posizione)}>
            <Popup><b>{t.posizione}. {t.cliente}</b><br />{t.indirizzo}<br />{t.tempo_tappa_min} min · {t.km_tappa} km</Popup>
          </Marker>
        ))}
        <FitBounds positions={[sede, ...stops]} />
      </MapContainer>
    </div>
  );
};
