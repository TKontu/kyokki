"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { analyzeImage } from "@/lib/api";

export function ImageUpload() {
  const [file, setFile] = useState<File | null>(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: analyzeImage,
    onSuccess: () => {
      // The websocket will trigger the query invalidation,
      // so we don't strictly need to do it here, but it can make
      // the UI feel more responsive if the websocket has latency.
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (file) {
      mutation.mutate(file);
      setFile(null); // Clear the file input after submission
    }
  };

  return (
    <div className="p-4 mb-4 bg-white rounded-lg shadow-md">
      <h2 className="text-xl font-bold mb-2">Add New Item</h2>
      <form onSubmit={handleSubmit}>
        <input
          type="file"
          onChange={(e) => setFile(e.target.files ? e.target.files[0] : null)}
          className="mb-2"
          accept="image/*"
        />
        <button
          type="submit"
          disabled={!file || mutation.isPending}
          className="px-4 py-2 text-white bg-blue-600 rounded hover:bg-blue-700 disabled:bg-gray-400"
        >
          {mutation.isPending ? "Analyzing..." : "Analyze Image"}
        </button>
      </form>
      {mutation.isError && (
        <p className="text-red-500 mt-2">Error: {mutation.error.message}</p>
      )}
    </div>
  );
}
