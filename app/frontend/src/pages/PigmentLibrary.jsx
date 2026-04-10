import { useState, useEffect } from "react";
import { getPigments } from "../api";

const COMPLIANCE_OPTS = ["", "NON-R", "ROHS1", "ROHS2", "REACH"];

function LabBar({ value, min, max, color }) {
  const pct = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
  return (
    <div className="flex items-center gap-2 text-xs">
      <div className="w-20 bg-gray-200 rounded h-2 flex-shrink-0">
        <div className="h-2 rounded" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className="w-10 text-right font-mono">{value?.toFixed(1)}</span>
    </div>
  );
}

export default function PigmentLibrary() {
  const [pigments, setPigments] = useState([]);
  const [compliance, setCompliance] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await getPigments({ compliance: compliance || undefined });
      setPigments(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [compliance]);

  const filtered = pigments.filter((p) =>
    !q || p.rawmaterialname?.toLowerCase().includes(q.toLowerCase())
  );

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Pigment Library</h1>
      <p className="text-sm text-gray-500 mb-4">
        Pigments with Full Tone and Tint Tone L*a*b* values. Used as input for the Kubelka-Munk mixing model.
      </p>

      <div className="flex gap-3 mb-4 flex-wrap">
        <input
          placeholder="Search pigment name…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="border rounded px-3 py-1.5 text-sm w-52 focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
        <select value={compliance} onChange={(e) => setCompliance(e.target.value)}
          className="border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400">
          {COMPLIANCE_OPTS.map((c) => <option key={c} value={c}>{c || "All Compliance"}</option>)}
        </select>
        <span className="text-sm text-gray-400 self-center">{filtered.length} pigments with LAB data</span>
      </div>

      {loading ? (
        <div className="text-gray-400 text-sm">Loading…</div>
      ) : (
        <div className="bg-white rounded-xl shadow overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-100 text-xs text-gray-600 uppercase">
              <tr>
                <th className="text-left px-4 py-2">ID</th>
                <th className="text-left px-4 py-2">Name</th>
                <th className="text-left px-4 py-2">CI Name</th>
                <th className="text-left px-4 py-2">Chemistry</th>
                <th className="text-left px-4 py-2">Compliance</th>
                <th className="text-left px-4 py-2">Full Tone Swatch</th>
                <th className="text-left px-4 py-2">Full Tone L/a/b</th>
                <th className="text-left px-4 py-2">Tint Tone Swatch</th>
                <th className="text-left px-4 py-2">Tint Tone L/a/b</th>
                <th className="text-center px-4 py-2">Heat (°C)</th>
                <th className="text-center px-4 py-2">LF Tone/Tint</th>
                <th className="text-center px-4 py-2">WF Tone/Tint</th>
                <th className="text-right px-4 py-2">Price (₹/kg)</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p) => (
                <tr key={p.rawmaterialid} className="border-t hover:bg-gray-50">
                  <td className="px-4 py-2 font-mono text-xs text-gray-500">{p.rawmaterialid}</td>
                  <td className="px-4 py-2 font-medium">{p.rawmaterialname}</td>
                  <td className="px-4 py-2 text-xs font-mono text-gray-600">{p.ci_name || "—"}</td>
                  <td className="px-4 py-2 text-xs text-gray-600">{p.chemistry || "—"}</td>
                  <td className="px-4 py-2">
                    <span className="text-xs bg-gray-100 px-2 py-0.5 rounded">{p.compliance}</span>
                  </td>
                  <td className="px-4 py-2">
                    {p.full_tone_hex ? (
                      <div className="w-8 h-8 rounded border"
                        style={{ backgroundColor: p.full_tone_hex }} title={p.full_tone_hex} />
                    ) : "—"}
                  </td>
                  <td className="px-4 py-2">
                    {p.lab ? (
                      <div className="space-y-0.5">
                        <LabBar value={p.lab.full_tone.L} min={0} max={110} color="#888" />
                        <LabBar value={p.lab.full_tone.a} min={-128} max={128} color="#e53e3e" />
                        <LabBar value={p.lab.full_tone.b} min={-128} max={128} color="#3182ce" />
                      </div>
                    ) : "—"}
                  </td>
                  <td className="px-4 py-2">
                    {p.tint_tone_hex ? (
                      <div className="w-8 h-8 rounded border"
                        style={{ backgroundColor: p.tint_tone_hex }} title={p.tint_tone_hex} />
                    ) : "—"}
                  </td>
                  <td className="px-4 py-2">
                    {p.lab ? (
                      <div className="space-y-0.5">
                        <LabBar value={p.lab.tint_tone.L} min={0} max={110} color="#888" />
                        <LabBar value={p.lab.tint_tone.a} min={-128} max={128} color="#e53e3e" />
                        <LabBar value={p.lab.tint_tone.b} min={-128} max={128} color="#3182ce" />
                      </div>
                    ) : "—"}
                  </td>
                  <td className="px-4 py-2 text-center text-xs font-semibold">
                    {p.heat_resistance ? (
                      <span className={`px-1.5 py-0.5 rounded ${p.heat_resistance >= 280 ? "bg-green-100 text-green-800" : p.heat_resistance >= 240 ? "bg-yellow-100 text-yellow-800" : "bg-orange-100 text-orange-800"}`}>
                        {p.heat_resistance}°
                      </span>
                    ) : "—"}
                  </td>
                  <td className="px-4 py-2 text-center text-xs">
                    {p.light_fastness_tone != null
                      ? `${p.light_fastness_tone}/${p.light_fastness_tint ?? "—"}`
                      : "—"}
                  </td>
                  <td className="px-4 py-2 text-center text-xs">
                    {p.weather_fastness_tone != null
                      ? `${p.weather_fastness_tone}/${p.weather_fastness_tint ?? "—"}`
                      : "—"}
                  </td>
                  <td className="px-4 py-2 text-right">{p.current_price ?? "—"}</td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={8} className="text-center text-gray-400 py-8">
                    No pigments with LAB data. Run the data importer first.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
