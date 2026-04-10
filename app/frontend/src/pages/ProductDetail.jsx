import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { getProduct, getProductCost, getLabResults, addLabResult } from "../api";

export default function ProductDetail() {
  const { id } = useParams();
  const [product, setProduct] = useState(null);
  const [cost, setCost] = useState(null);
  const [labResults, setLabResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [labForm, setLabForm] = useState({ polymer: "PE", L: "", a: "", b: "", measured_date: "", notes: "" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([
      getProduct(id),
      getProductCost(id).catch(() => ({ data: null })),
      getLabResults({ product_id: id }),
    ]).then(([p, c, l]) => {
      setProduct(p.data);
      setCost(c.data);
      setLabResults(l.data);
    }).finally(() => setLoading(false));
  }, [id]);

  const handleAddLab = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await addLabResult({ product_id: id, ...labForm, L: parseFloat(labForm.L), a: parseFloat(labForm.a), b: parseFloat(labForm.b) });
      const { data } = await getLabResults({ product_id: id });
      setLabResults(data);
      setLabForm({ polymer: "PE", L: "", a: "", b: "", measured_date: "", notes: "" });
    } catch (e) {
      alert(e.response?.data?.error || e.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="text-gray-400">Loading…</div>;
  if (!product) return <div className="text-red-500">Product not found.</div>;

  return (
    <div>
      <Link to="/products" className="text-indigo-600 hover:underline text-sm">← Back to Products</Link>
      <h1 className="text-2xl font-bold mt-2 mb-1">{product.id} — {product.name}</h1>
      <div className="text-sm text-gray-500 mb-4">SLF: {product.slf_no || "—"} &nbsp;|&nbsp; Price: ₹{product.selling_price}/kg &nbsp;|&nbsp; RAL: {product.ral_shade || "—"}</div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recipe */}
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="font-semibold mb-3">Recipe</h2>
          {product.recipe?.length > 0 ? (
            <table className="w-full text-sm">
              <thead className="bg-gray-100 text-xs text-gray-500 uppercase">
                <tr>
                  <th className="text-left px-3 py-1">RM ID</th>
                  <th className="text-left px-3 py-1">Material</th>
                  <th className="text-right px-3 py-1">Qty (kg)</th>
                </tr>
              </thead>
              <tbody>
                {product.recipe.map((r, i) => (
                  <tr key={i} className="border-t">
                    <td className="px-3 py-1 font-mono text-xs">{r.rawmaterialid}</td>
                    <td className="px-3 py-1">{r.rawmaterialname || "—"}</td>
                    <td className="px-3 py-1 text-right">{r.qtyinkg}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="text-gray-400 text-sm">No recipe found.</div>}
        </div>

        {/* Cost Estimate */}
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="font-semibold mb-3">Cost Estimate</h2>
          {cost ? (
            <>
              <div className="flex gap-6 mb-3 text-sm">
                <div><span className="text-gray-500">Batch qty:</span> <strong>{cost.total_batch_qty_kg} kg</strong></div>
                <div><span className="text-gray-500">Total cost:</span> <strong>₹{cost.total_cost}</strong></div>
                <div><span className="text-gray-500">Cost/kg:</span> <strong>₹{cost.cost_per_kg}</strong></div>
                <div><span className="text-gray-500">Selling:</span> <strong>₹{product.selling_price}</strong></div>
              </div>
              <table className="w-full text-xs">
                <thead className="bg-gray-100 text-gray-500 uppercase">
                  <tr>
                    <th className="text-left px-2 py-1">Material</th>
                    <th className="text-right px-2 py-1">Qty</th>
                    <th className="text-right px-2 py-1">Rate</th>
                    <th className="text-right px-2 py-1">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {cost.breakdown.map((b, i) => (
                    <tr key={i} className="border-t">
                      <td className="px-2 py-1">{b.name}</td>
                      <td className="px-2 py-1 text-right">{b.qty_kg}</td>
                      <td className="px-2 py-1 text-right">{b.price_per_kg != null ? `₹${b.price_per_kg}` : "—"}</td>
                      <td className="px-2 py-1 text-right">{b.cost != null ? `₹${b.cost}` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : <div className="text-gray-400 text-sm">No cost data.</div>}
        </div>

        {/* Alpha Codes */}
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="font-semibold mb-3">Alpha Codes</h2>
          <div className="flex flex-wrap gap-2">
            {(product.alphacode || []).map((c) => (
              <span key={c} className="text-xs bg-indigo-100 text-indigo-700 font-mono px-2 py-0.5 rounded">{c}</span>
            ))}
          </div>
        </div>

        {/* Spec */}
        {product.spec && (
          <div className="bg-white rounded-xl shadow p-5">
            <h2 className="font-semibold mb-3">Specifications</h2>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              {Object.entries(product.spec).filter(([, v]) => v != null).map(([k, v]) => (
                <div key={k} className="flex gap-2">
                  <dt className="text-gray-500 capitalize">{k.replace(/_/g, " ")}:</dt>
                  <dd className="font-medium">{String(v)}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
      </div>

      {/* Lab Results */}
      <div className="bg-white rounded-xl shadow p-5 mt-6">
        <h2 className="font-semibold mb-3">Measured LAB Results</h2>
        {labResults.length > 0 ? (
          <table className="w-full text-sm mb-4">
            <thead className="bg-gray-100 text-xs text-gray-500 uppercase">
              <tr>
                <th className="text-left px-3 py-1">Polymer</th>
                <th className="text-right px-3 py-1">L*</th>
                <th className="text-right px-3 py-1">a*</th>
                <th className="text-right px-3 py-1">b*</th>
                <th className="text-left px-3 py-1">Date</th>
                <th className="text-left px-3 py-1">Notes</th>
              </tr>
            </thead>
            <tbody>
              {labResults.map((r) => (
                <tr key={r.id} className="border-t">
                  <td className="px-3 py-1 font-mono">{r.polymer}</td>
                  <td className="px-3 py-1 text-right">{r.L}</td>
                  <td className="px-3 py-1 text-right">{r.a}</td>
                  <td className="px-3 py-1 text-right">{r.b}</td>
                  <td className="px-3 py-1 text-xs text-gray-400">{r.measured_date}</td>
                  <td className="px-3 py-1 text-xs text-gray-500">{r.notes || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="text-gray-400 text-sm mb-3">No lab results recorded yet.</div>}

        {/* Add lab result form */}
        <form onSubmit={handleAddLab} className="border-t pt-4 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 items-end">
          <div>
            <label className="text-xs text-gray-500 block mb-1">Polymer</label>
            <input value={labForm.polymer} onChange={(e) => setLabForm(f => ({ ...f, polymer: e.target.value }))}
              className="border rounded px-2 py-1 text-sm w-full" required />
          </div>
          {["L", "a", "b"].map((k) => (
            <div key={k}>
              <label className="text-xs text-gray-500 block mb-1">{k}*</label>
              <input type="number" step="0.01" value={labForm[k]} required
                onChange={(e) => setLabForm(f => ({ ...f, [k]: e.target.value }))}
                className="border rounded px-2 py-1 text-sm w-full" />
            </div>
          ))}
          <div>
            <label className="text-xs text-gray-500 block mb-1">Date</label>
            <input type="date" value={labForm.measured_date}
              onChange={(e) => setLabForm(f => ({ ...f, measured_date: e.target.value }))}
              className="border rounded px-2 py-1 text-sm w-full" />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Notes</label>
            <input value={labForm.notes} onChange={(e) => setLabForm(f => ({ ...f, notes: e.target.value }))}
              className="border rounded px-2 py-1 text-sm w-full" />
          </div>
          <div>
            <button type="submit" disabled={saving}
              className="bg-indigo-600 text-white px-3 py-1.5 rounded text-sm w-full hover:bg-indigo-700 disabled:opacity-50">
              {saving ? "…" : "Add"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
