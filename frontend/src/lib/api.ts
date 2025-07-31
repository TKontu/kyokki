const BASE_URL = "http://localhost:8000/api";

export async function fetchItems() {
  const response = await fetch(`${BASE_URL}/items`);
  if (!response.ok) {
    throw new Error("Failed to fetch items");
  }
  return response.json();
}

export async function analyzeImage(file: File) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${BASE_URL}/items/analyze`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error("Failed to analyze image");
  }
  return response.json();
}

export async function deleteItem(id: string) {
  const response = await fetch(`${BASE_URL}/items/${id}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error("Failed to delete item");
  }
  return response.json();
}