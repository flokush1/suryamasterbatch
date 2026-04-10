import { useState, useEffect } from "react";
import { getStocks, getRawMaterials } from "../api";

export default function Stocks() {
  const [stocks, setStocks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [showLowOnly, setShowLowOnly] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await getStocks({ q: q || undefined });
      setStocks(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [q]);

  const filtered = showLowOnly
    ? stocks.filter((s) => (s.available_stocks ?? 0) < 50)
    : stocks;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Raw Material Stocks</h1>

      <div className="flex gap-3 mb-4 flex-wrap items-center">
        <input
          placeholder="Search material…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="border rounded px-3 py-1.5 text-sm w-52 focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
        <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
          <input type="checkbox" checked={showLowOnly} onChange={(e) => setShowLowOnly(e.target.checked)}
            className="accent-indigo-600" />
          Show low stock (&lt;50 kg) only
        </label>
        <span className="text-sm text-gray-400 self-center">{filtered.length} entries</span>
      </div>

      {loading ? (
        <div className="text-gray-400 text-sm">Loading…</div>
      ) : (
        <div className="bg-white rounded-xl shadow overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-100 text-xs text-gray-500 uppercase">
              <tr>
                <th className="text-left px-4 py-2">RM ID</th>
                <th className="text-left px-4 py-2">Material</th>
                <th className="text-left px-4 py-2">Particulars</th>
                <th className="text-right px-4 py-2">Stock (kg)</th>
                <th className="text-left px-4 py-2">Last Updated</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s, i) => {
                const low = (s.available_stocks ?? 0) < 50;
                return (
                  <tr key={i} className={`border-t ${low ? "bg-red-50" : "hover:bg-gray-50"}`}>
                    <td className="px-4 py-2 font-mono text-xs text-gray-500">{s.rawmaterialid || "—"}</td>
                    <td className="px-4 py-2">{s.rawmaterialname || "—"}</td>
                    <td className="px-4 py-2 text-gray-500 text-xs">{s.particulars_name || "—"}</td>
                    <td className={`px-4 py-2 text-right font-semibold ${low ? "text-red-600" : "text-green-700"}`}>
                      {s.available_stocks?.toLocaleString() ?? "—"}
                    </td>
                    <td className="px-4 py-2 text-xs text-gray-400">{s.last_updated || "—"}</td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr><td colSpan={5} className="text-center text-gray-400 py-8">No stock data found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
