const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api";

async function handleResponse(response: Response) {
  if (!response.ok) {
    const errorText = await response.text();
    console.error("API Error Response:", errorText);
    throw new Error(`Failed to fetch: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

export async function fetchItems() {
  const url = `${BASE_URL}/items`;
  console.log("Fetching items from:", url);
  try {
    const response = await fetch(url);
    return await handleResponse(response);
  } catch (error) {
    console.error("Network error while fetching items:", error);
    throw error;
  }
}

export async function analyzeImage(file: File) {
  const url = `${BASE_URL}/items/analyze`;
  console.log("Analyzing image by posting to:", url);
  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch(url, {
      method: "POST",
      body: formData,
    });
    return await handleResponse(response);
  } catch (error) {
    console.error("Network error while analyzing image:", error);
    throw error;
  }
}

export async function deleteItem(id: string) {
  const url = `${BASE_URL}/items/${id}`;
  console.log("Deleting item at:", url);
  try {
    const response = await fetch(url, {
      method: "DELETE",
    });
    return await handleResponse(response);
  } catch (error) {
    console.error("Network error while deleting item:", error);
    throw error;
  }
}