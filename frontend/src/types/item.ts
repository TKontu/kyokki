export interface Item {
  id: string;
  product_name: string;
  category: string | null;
  expiry_date: string | null; // Dates are strings over the wire
  status: string;
  confidence_score: number | null;
  image_path: string;
  date_added: string;
  date_modified: string;
}
