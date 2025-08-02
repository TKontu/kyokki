"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchItems, deleteItem } from "@/lib/api";
import { Item } from "@/types/item";
import { differenceInDays, parseISO } from "date-fns";

function getExpiryColor(expiryDate: string | null): string {
  if (!expiryDate) return "text-gray-500";
  const daysUntilExpiry = differenceInDays(parseISO(expiryDate), new Date());
  if (daysUntilExpiry < 0) return "text-red-600 font-bold";
  if (daysUntilExpiry <= 3) return "text-yellow-600";
  return "text-green-600";
}

export function ItemList() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error } = useQuery<Item[]>({
    queryKey: ["items"],
    queryFn: fetchItems,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteItem,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });

  const sortedData = data?.sort((a, b) => {
    if (!a.expiry_date) return 1;
    if (!b.expiry_date) return -1;
    return differenceInDays(parseISO(a.expiry_date), parseISO(b.expiry_date));
  });

  const renderContent = () => {
    if (isLoading) {
      return <p className="p-4 text-gray-500">Loading items...</p>;
    }
    if (isError) {
      return <p className="p-4 text-red-500">Error: {error.message}</p>;
    }
    if (!sortedData || sortedData.length === 0) {
      return <p className="p-4 text-gray-500">No items found. Add one to get started!</p>;
    }
    return (
      <ul>
        {sortedData.map((item) => (
          <li key={item.id} className="flex items-center p-4 border-t">
            <div className="flex-grow">
              <p className="font-bold">{item.product_name}</p>
              <p className="text-sm text-gray-600">{item.category}</p>
              <p className={`text-sm ${getExpiryColor(item.expiry_date)}`}>
                Expires: {item.expiry_date ? new Date(item.expiry_date).toLocaleDateString() : "N/A"}
              </p>
            </div>
            <button
              onClick={() => deleteMutation.mutate(item.id)}
              className="px-3 py-1 text-sm text-white bg-red-500 rounded hover:bg-red-600 disabled:bg-gray-400"
              disabled={deleteMutation.isPending}
            >
              Delete
            </button>
          </li>
        ))}
      </ul>
    );
  };

  return (
    <div className="bg-white rounded-lg shadow-md">
      <h2 className="text-xl font-bold p-4">Current Items</h2>
      {renderContent()}
    </div>
  );
}
