import axios from "axios";

const api = axios.create({
  baseURL: "http://localhost:5000",
  headers: { "Content-Type": "application/json" },
});

export const searchColors = (payload) => api.post("/api/search", payload);
export const getProducts = (params) => api.get("/api/products", { params });
export const getProduct = (id) => api.get(`/api/products/${id}`);
export const getRecipe = (id) => api.get(`/api/products/${id}/recipe`);
export const getProductCost = (id) => api.get(`/api/cost/${id}`);
export const getRawMaterials = (params) => api.get("/api/raw-materials", { params });
export const getStocks = (params) => api.get("/api/stocks", { params });
export const getPigments = (params) => api.get("/api/pigments", { params });
export const getRalPantone = (params) => api.get("/api/ral-pantone", { params });
export const getLabResults = (params) => api.get("/api/lab-results", { params });
export const addLabResult = (data) => api.post("/api/lab-results", data);
export const deleteLabResult = (id) => api.delete(`/api/lab-results/${id}`);
export const getAlphaCodes = (params) => api.get("/api/alpha-codes", { params });

export default api;
