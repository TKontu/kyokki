"use client";

import { ImageUpload } from "@/components/ImageUpload";
import { ItemList } from "@/components/ItemList";

export default function Home() {
  return (
    <div>
      <h1 className="text-3xl font-bold mb-6">Fridge Logger</h1>
      <ImageUpload />
      <ItemList />
    </div>
  );
}
