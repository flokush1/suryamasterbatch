import { useState, useEffect } from "react";
import { getProducts } from "../api";
import { Link } from "react-router-dom";

const POLYMERS = ["", "PE", "PP", "ABS", "SAN", "OTHER"];

export default function Products() {
  const [products, setProducts] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({ name: "", polymer: "" });
  const [loading, setLoading] = useState(false);
  const PER_PAGE = 50;

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await getProducts({ ...filters, page, per_page: PER_PAGE });
      setProducts(data.products);
      setTotal(data.total);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filters, page]);
  const set = (k, v) => { setFilters((f) => ({ ...f, [k]: v })); setPage(1); };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Products</h1>

      <div className="flex gap-3 mb-4 flex-wrap">
        <input
          placeholder="Search by name…"
          value={filters.name}
          onChange={(e) => set("name", e.target.value)}
          className="border rounded px-3 py-1.5 text-sm w-48 focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
        <select
          value={filters.polymer}
          onChange={(e) => set("polymer", e.target.value)}
          className="border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
        >
          {POLYMERS.map((p) => <option key={p} value={p}>{p || "All Polymers"}</option>)}
        </select>
        <span className="text-sm text-gray-500 self-center">{total} products</span>
      </div>

      {loading ? (
        <div className="text-gray-400 text-sm">Loading…</div>
      ) : (
        <>
          <div className="bg-white rounded-xl shadow overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-100 text-gray-600 text-xs uppercase">
                <tr>
                  <th className="text-left px-4 py-2">ID</th>
                  <th className="text-left px-4 py-2">Name</th>
                  <th className="text-left px-4 py-2">SLF No.</th>
                  <th className="text-right px-4 py-2">Price (₹/kg)</th>
                  <th className="text-left px-4 py-2">RAL</th>
                  <th className="text-left px-4 py-2">Alpha Codes</th>
                  <th className="text-left px-4 py-2">Updated</th>
                </tr>
              </thead>
              <tbody>
                {products.map((p) => (
                  <tr key={p.id} className="border-t hover:bg-gray-50">
                    <td className="px-4 py-2 font-mono font-medium">
                      <Link to={`/products/${p.id}`} className="text-indigo-600 hover:underline">{p.id}</Link>
                    </td>
                    <td className="px-4 py-2">{p.name}</td>
                    <td className="px-4 py-2 text-gray-500">{p.slf_no || "—"}</td>
                    <td className="px-4 py-2 text-right">{p.selling_price?.toFixed(2) || "—"}</td>
                    <td className="px-4 py-2 text-gray-500 text-xs">{p.ral_shade || "—"}</td>
                    <td className="px-4 py-2 text-xs text-gray-400">{(p.alphacode || []).slice(0, 3).join(", ")}{(p.alphacode || []).length > 3 ? " …" : ""}</td>
                    <td className="px-4 py-2 text-xs text-gray-400">{p.date_updated || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex gap-2 mt-4 items-center">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}
              className="px-3 py-1 rounded border text-sm disabled:opacity-40 hover:bg-gray-100">← Prev</button>
            <span className="text-sm text-gray-500">Page {page} of {Math.ceil(total / PER_PAGE)}</span>
            <button disabled={page >= Math.ceil(total / PER_PAGE)} onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1 rounded border text-sm disabled:opacity-40 hover:bg-gray-100">Next →</button>
          </div>
        </>
      )}
    </div>
  );
}
