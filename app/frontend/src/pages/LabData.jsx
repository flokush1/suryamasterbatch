import { useState, useEffect } from "react";
import { getLabResults, addLabResult, deleteLabResult } from "../api";

export default function LabData() {
  const [results, setResults] = useState([]);
  const [filter, setFilter] = useState({ product_id: "", polymer: "" });
  const [form, setForm] = useState({ product_id: "", polymer: "PE", L: "", a: "", b: "", measured_date: "", notes: "" });
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const params = {};
      if (filter.product_id) params.product_id = filter.product_id;
      if (filter.polymer) params.polymer = filter.polymer;
      const { data } = await getLabResults(params);
      setResults(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filter]);

  const handleAdd = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await addLabResult({ ...form, L: parseFloat(form.L), a: parseFloat(form.a), b: parseFloat(form.b) });
      load();
      setForm({ product_id: "", polymer: "PE", L: "", a: "", b: "", measured_date: "", notes: "" });
    } catch (err) {
      alert(err.response?.data?.error || err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this lab result?")) return;
    await deleteLabResult(id);
    load();
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-2">Lab Data</h1>
      <p className="text-sm text-gray-500 mb-4">
        Record measured LAB values from the spectrophotometer after each batch trial.
        This data feeds the learning model to improve cross-polymer predictions over time.
      </p>

      {/* Add form */}
      <div className="bg-white rounded-xl shadow p-5 mb-6">
        <h2 className="font-semibold mb-3">Record New Measurement</h2>
        <form onSubmit={handleAdd} className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3 items-end">
          <div className="col-span-2">
            <label className="text-xs text-gray-500 block mb-1">Product ID <span className="text-red-500">*</span></label>
            <input required value={form.product_id} onChange={(e) => setForm(f => ({ ...f, product_id: e.target.value }))}
              placeholder="e.g. 30016"
              className="border rounded px-2 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-400" />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Polymer</label>
            <input required value={form.polymer} onChange={(e) => setForm(f => ({ ...f, polymer: e.target.value }))}
              className="border rounded px-2 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-400" />
          </div>
          {["L", "a", "b"].map((k) => (
            <div key={k}>
              <label className="text-xs text-gray-500 block mb-1">{k}* <span className="text-red-500">*</span></label>
              <input type="number" step="0.01" required value={form[k]}
                onChange={(e) => setForm(f => ({ ...f, [k]: e.target.value }))}
                className="border rounded px-2 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-400" />
            </div>
          ))}
          <div>
            <label className="text-xs text-gray-500 block mb-1">Date</label>
            <input type="date" value={form.measured_date}
              onChange={(e) => setForm(f => ({ ...f, measured_date: e.target.value }))}
              className="border rounded px-2 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-400" />
          </div>
          <div className="col-span-2">
            <label className="text-xs text-gray-500 block mb-1">Notes</label>
            <input value={form.notes} onChange={(e) => setForm(f => ({ ...f, notes: e.target.value }))}
              placeholder="Batch #, observations…"
              className="border rounded px-2 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-400" />
          </div>
          <div>
            <button type="submit" disabled={saving}
              className="bg-indigo-600 text-white px-4 py-1.5 rounded text-sm w-full hover:bg-indigo-700 disabled:opacity-50">
              {saving ? "Saving…" : "Add"}
            </button>
          </div>
        </form>
      </div>

      {/* Filter */}
      <div className="flex gap-3 mb-3 flex-wrap">
        <input placeholder="Filter by Product ID…" value={filter.product_id}
          onChange={(e) => setFilter(f => ({ ...f, product_id: e.target.value }))}
          className="border rounded px-3 py-1.5 text-sm w-44 focus:outline-none focus:ring-2 focus:ring-indigo-400" />
        <input placeholder="Filter by Polymer…" value={filter.polymer}
          onChange={(e) => setFilter(f => ({ ...f, polymer: e.target.value }))}
          className="border rounded px-3 py-1.5 text-sm w-36 focus:outline-none focus:ring-2 focus:ring-indigo-400" />
        <span className="text-sm text-gray-400 self-center">{results.length} records</span>
      </div>

      {/* Table */}
      {loading ? <div className="text-gray-400 text-sm">Loading…</div> : (
        <div className="bg-white rounded-xl shadow overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-100 text-xs text-gray-500 uppercase">
              <tr>
                <th className="text-left px-4 py-2">Product ID</th>
                <th className="text-left px-4 py-2">Polymer</th>
                <th className="text-right px-4 py-2">L*</th>
                <th className="text-right px-4 py-2">a*</th>
                <th className="text-right px-4 py-2">b*</th>
                <th className="text-left px-4 py-2">Date</th>
                <th className="text-left px-4 py-2">Notes</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={r.id} className="border-t hover:bg-gray-50">
                  <td className="px-4 py-2 font-mono font-medium text-indigo-600">{r.product_id}</td>
                  <td className="px-4 py-2">{r.polymer}</td>
                  <td className="px-4 py-2 text-right">{r.L}</td>
                  <td className="px-4 py-2 text-right">{r.a}</td>
                  <td className="px-4 py-2 text-right">{r.b}</td>
                  <td className="px-4 py-2 text-xs text-gray-400">{r.measured_date || "—"}</td>
                  <td className="px-4 py-2 text-xs text-gray-500">{r.notes || "—"}</td>
                  <td className="px-4 py-2">
                    <button onClick={() => handleDelete(r.id)}
                      className="text-xs text-red-500 hover:underline">Delete</button>
                  </td>
                </tr>
              ))}
              {results.length === 0 && (
                <tr><td colSpan={8} className="text-center text-gray-400 py-8">No lab results yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
